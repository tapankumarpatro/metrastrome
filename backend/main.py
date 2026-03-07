"""
Meta-Brainstorming Backend — AutoGen Group Chat Server

FastAPI + WebSocket server that hosts an AutoGen SelectorGroupChat.
Each agent variant is an AssistantAgent; the human user sends messages
via WebSocket. Agent responses stream back in real-time.

Usage:
    python main.py                                    # all agents, port 8000
    python main.py --agents agent-architect,agent-builder   # specific variants
    python main.py --port 8080                         # custom port
"""

import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path
from typing import Optional

import aiohttp
import edge_tts
from tts_providers import generate_tts as _provider_tts, get_tts_info

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import SelectorGroupChat, RoundRobinGroupChat
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

from pydantic import BaseModel
import agents.base_agent as agent_module
from agents.base_agent import AgentConfig, reload_agents, get_config_path
import conversation_store as convstore
import memory_store as memstore
import file_utils

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick")
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
MUSETALK_URL = os.getenv("MUSETALK_URL", "http://localhost:8001")
USE_VIDEO_CALL = os.getenv("USE_VIDEO_CALL", "false").lower() == "true"

# Agent image paths (for MuseTalk avatar preparation) — derived from config
IMAGES_DIR = Path(__file__).parent.parent / "frontend" / "public" / "images"
UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
USER_REFERENCE_PHOTO = IMAGES_DIR / "user-reference.jpg"
AGENT_IMAGE_MAP = {
    agent_id: str(IMAGES_DIR / cfg.image)
    for agent_id, cfg in agent_module.AGENT_REGISTRY.items()
    if cfg.image
}

app = FastAPI(title="Meta-Brainstorming API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── User reference photo endpoints ────────────────────────────────────

class UploadPhotoRequest(BaseModel):
    photo: str  # base64 data URI, e.g. "data:image/jpeg;base64,..."

@app.post("/user/photo")
async def upload_user_photo(req: UploadPhotoRequest):
    """Save the user's reference photo (base64 data URI → file)."""
    try:
        # Parse the data URI
        data_uri = req.photo
        if "," in data_uri:
            header, b64_data = data_uri.split(",", 1)
        else:
            b64_data = data_uri

        image_bytes = base64.b64decode(b64_data)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        with open(USER_REFERENCE_PHOTO, "wb") as f:
            f.write(image_bytes)
        logger.info(f"User reference photo saved: {USER_REFERENCE_PHOTO} ({len(image_bytes)} bytes)")
        return {"ok": True, "path": str(USER_REFERENCE_PHOTO)}
    except Exception as e:
        logger.error(f"Failed to save user photo: {e}")
        return {"error": str(e)}

@app.get("/user/photo")
async def get_user_photo():
    """Check if user reference photo exists."""
    exists = USER_REFERENCE_PHOTO.exists()
    return {"exists": exists, "path": "/images/user-reference.jpg" if exists else ""}

@app.delete("/user/photo")
async def delete_user_photo():
    """Delete the user's reference photo."""
    if USER_REFERENCE_PHOTO.exists():
        USER_REFERENCE_PHOTO.unlink()
        logger.info("User reference photo deleted")
    return {"ok": True}


# ── Chat file upload endpoint ─────────────────────────────────────────

# Serve uploaded files as static assets
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# In-memory store for uploaded file metadata (keyed by file_id)
_uploaded_files: dict[str, dict] = {}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


@app.post("/chat/upload")
async def upload_chat_file(file: UploadFile = File(...)):
    """Upload a file for sharing in chat. Returns file_id, URL, and extracted text."""
    if not file.filename:
        return {"error": "No file provided"}

    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        return {"error": f"File too large ({len(data) // 1024 // 1024} MB). Max {MAX_UPLOAD_SIZE // 1024 // 1024} MB."}

    # Generate unique filename
    import uuid
    ext = Path(file.filename).suffix
    file_id = uuid.uuid4().hex[:12]
    safe_name = f"{file_id}{ext}"
    save_path = UPLOADS_DIR / safe_name

    with open(save_path, "wb") as f:
        f.write(data)

    # Extract text content
    text_content = file_utils.extract_text_from_bytes(data, file.filename)
    is_image = file_utils.is_image_file(file.filename)
    mime = file_utils.get_mime_type(file.filename)

    file_meta = {
        "file_id": file_id,
        "original_name": file.filename,
        "safe_name": safe_name,
        "url": f"/uploads/{safe_name}",
        "size": len(data),
        "mime": mime,
        "is_image": is_image,
        "text_content": text_content,
    }
    _uploaded_files[file_id] = file_meta

    logger.info(f"[Upload] Saved {file.filename} → {safe_name} ({len(data)} bytes, text: {len(text_content)} chars)")

    return {
        "ok": True,
        "file_id": file_id,
        "url": f"/uploads/{safe_name}",
        "original_name": file.filename,
        "size": len(data),
        "is_image": is_image,
        "mime": mime,
        "has_text": bool(text_content),
    }


# ── System capabilities ───────────────────────────────────────────────

@app.get("/system/capabilities")
async def system_capabilities():
    """Return system capabilities so the frontend knows what's available."""
    from check_gpu import get_capability_summary
    gpu_info = get_capability_summary()
    from livekit_service import get_livekit_info
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
    return {
        "use_video_call": USE_VIDEO_CALL,
        "gpu": gpu_info,
        "tts": get_tts_info(),
        "stt": {
            "server_side": bool(deepgram_key),
            "provider": "deepgram" if deepgram_key else "browser",
        },
        "livekit": get_livekit_info(),
    }


@app.post("/livekit/token")
async def livekit_token(room: str, participant: str):
    """Generate a LiveKit access token for joining a room."""
    from livekit_service import generate_token, is_livekit_configured
    if not is_livekit_configured():
        return {"error": "LiveKit not configured", "token": None}
    token = generate_token(room, participant)
    if not token:
        return {"error": "Token generation failed", "token": None}
    return {"token": token, "url": os.getenv("LIVEKIT_URL", "")}


# ── User Perception (Emotion Detection) ──────────────────────────────

class PerceptionRequest(BaseModel):
    image: str  # base64-encoded JPEG (with or without data URI prefix)

@app.post("/perception/analyze")
async def analyze_perception(req: PerceptionRequest):
    """Analyze a webcam frame for user emotional state."""
    import perception
    result = await perception.analyze_frame(req.image)
    return result


# ── Conversation history endpoints ────────────────────────────────────

class AsyncChatRequest(BaseModel):
    agent_id: str
    message: str
    user_name: str = ""

@app.post("/chat/agent")
async def async_chat_with_agent(req: AsyncChatRequest):
    """Send a single message to a specific agent and get a reply (non-realtime).
    Used for the social feed / 1-on-1 chat outside meetings."""
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY not set"}

    agent_cfg = agent_module.AGENT_REGISTRY.get(req.agent_id)
    if not agent_cfg:
        return {"error": f"Unknown agent: {req.agent_id}"}

    # Build context from past conversations with this agent
    past_context = convstore.get_conversation_context_for_agent(req.agent_id, max_messages=15)
    user_name = req.user_name or "User"

    system_msg = agent_cfg.system_prompt
    if past_context:
        system_msg += (
            f"\n\nThe user's name is {user_name}."
            "\n\nYou have memories from past conversations. Use them naturally."
            f"\n\n{past_context}"
        )
    else:
        system_msg += f"\n\nThe user's name is {user_name}."

    system_msg += (
        "\n\nThis is a casual 1-on-1 chat outside of a brainstorming meeting. "
        "Be conversational, warm, and concise. You can ask follow-up questions, "
        "share your perspective, or bring up interesting topics from past discussions."
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": req.message},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 500,
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return {"error": f"LLM error: {resp.status}"}
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]

        # Persist the exchange
        chat_session_id = f"dm-{req.agent_id}-{int(asyncio.get_event_loop().time())}"
        convstore.create_session(chat_session_id, [req.agent_id], user_name)
        convstore.add_message(chat_session_id, "user", req.message, user_name)
        convstore.add_message(chat_session_id, req.agent_id, reply, agent_cfg.variant)

        return {
            "agent_id": req.agent_id,
            "variant": agent_cfg.variant,
            "reply": reply,
        }
    except Exception as e:
        logger.error(f"Async chat error: {e}")
        return {"error": str(e)}


@app.get("/conversations")
async def list_conversations(limit: int = 20):
    """List recent conversation sessions."""
    sessions = convstore.get_past_sessions(limit=limit)
    return {"sessions": sessions}

@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    """Get all messages for a specific session."""
    messages = convstore.get_session_messages(session_id)
    return {"session_id": session_id, "messages": messages}

@app.get("/conversations/agent/{agent_id}")
async def get_agent_conversations(agent_id: str, limit: int = 30):
    """Get recent messages from sessions involving a specific agent."""
    messages = convstore.get_recent_messages(agent_id=agent_id, limit=limit)
    return {"agent_id": agent_id, "messages": messages}


# ── Meetings (persistent group chat sessions) ─────────────────────────

@app.get("/meetings")
async def list_meetings(limit: int = 30):
    """List past meetings with preview info for the Messages page."""
    meetings = convstore.get_meetings(limit=limit)
    result = []
    for m in meetings:
        # Skip empty sessions (no messages)
        if m.get("message_count", 0) == 0:
            continue
        agents_list = json.loads(m.get("agents", "[]")) if isinstance(m.get("agents"), str) else m.get("agents", [])
        # Resolve agent display info
        agent_infos = []
        for aid in agents_list:
            cfg = agent_module.AGENT_REGISTRY.get(aid)
            if cfg:
                agent_infos.append({
                    "id": cfg.identity,
                    "variant": cfg.variant,
                    "emoji": cfg.emoji,
                    "image": f"/images/{cfg.image}" if cfg.image and not cfg.image.startswith("/") else (cfg.image or ""),
                })
        result.append({
            "id": m["id"],
            "title": m.get("title") or f"Meeting with {', '.join(a['variant'] for a in agent_infos[:3])}",
            "created_at": m["created_at"],
            "last_active": m.get("last_active", m["created_at"]),
            "agents": agent_infos,
            "agent_ids": agents_list,
            "user_name": m.get("user_name", ""),
            "message_count": m.get("message_count", 0),
            "last_message": (m.get("last_message") or "")[:120],
            "summary": m.get("summary", ""),
        })
    return {"meetings": result}


@app.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    """Get meeting details and all messages for rejoin."""
    meeting = convstore.get_meeting(meeting_id)
    if not meeting:
        return {"error": "Meeting not found"}
    messages = convstore.get_session_messages(meeting_id, limit=500)
    agents_list = json.loads(meeting.get("agents", "[]")) if isinstance(meeting.get("agents"), str) else meeting.get("agents", [])
    return {
        "meeting": {
            "id": meeting["id"],
            "title": meeting.get("title", ""),
            "created_at": meeting["created_at"],
            "last_active": meeting.get("last_active", meeting["created_at"]),
            "agent_ids": agents_list,
            "user_name": meeting.get("user_name", ""),
        },
        "messages": messages,
    }


@app.delete("/meetings/{meeting_id}")
async def delete_meeting_endpoint(meeting_id: str):
    """Delete a meeting and all its messages."""
    ok = convstore.delete_meeting(meeting_id)
    return {"ok": ok}


def build_model_client() -> OpenAIChatCompletionClient:
    """Create an OpenAI-compatible client pointed at OpenRouter."""
    return OpenAIChatCompletionClient(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": False,
            "family": "unknown",
        },
    )


def build_agents(
    agent_configs: list[AgentConfig],
    model_client: OpenAIChatCompletionClient,
) -> list[AssistantAgent]:
    """Create AutoGen AssistantAgents from our AgentConfig definitions."""
    agents = []
    for cfg in agent_configs:
        agent = AssistantAgent(
            name=cfg.agent_name,
            description=cfg.description,
            model_client=model_client,
            system_message=cfg.system_prompt,
        )
        agents.append(agent)
        logger.info(f"Created agent: {cfg.agent_name} ({cfg.variant})")
    return agents


def _selector_prompt(owner: str = "the user") -> str:
    return f"""You are managing a brainstorming group chat called "The Multiverse of {owner}".
Every participant is a variant of the same person ({owner}) who took a different life path.

{{roles}}

Current conversation:
{{history}}

Based on the conversation so far, select the agent from {{participants}} who would have
the most relevant and interesting perspective to contribute next. Prefer agents who
haven't spoken recently and whose expertise is most relevant to the current topic.
Only select one agent."""


async def generate_tts(text: str, voice: str = "en-US-AndrewMultilingualNeural") -> bytes:
    """Generate MP3 audio from text using the configured TTS provider.
    Provider is set via TTS_PROVIDER env var (edge/cartesia/elevenlabs/deepgram)."""
    return await _provider_tts(text, voice)


# ── MuseTalk helpers ──────────────────────────────────────────────────

async def musetalk_health() -> bool:
    """Check if the MuseTalk service is reachable."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{MUSETALK_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                return r.status == 200
    except Exception:
        return False


async def musetalk_prepare(agent_id: str) -> bool:
    """Prepare an agent's avatar on the MuseTalk service (one-time)."""
    image_path = AGENT_IMAGE_MAP.get(agent_id)
    if not image_path:
        logger.warning(f"No image path for agent {agent_id}")
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MUSETALK_URL}/prepare",
                json={"agent_id": agent_id, "image_path": image_path},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                result = await r.json()
                logger.info(f"MuseTalk prepare {agent_id}: {result}")
                return r.status == 200
    except Exception as e:
        logger.warning(f"MuseTalk prepare failed for {agent_id}: {e}")
        return False


async def musetalk_generate_video(agent_id: str, audio_bytes: bytes) -> Optional[bytes]:
    """Send audio to MuseTalk and get back a lip-synced MP4 video."""
    try:
        form = aiohttp.FormData()
        form.add_field("agent_id", agent_id)
        form.add_field("audio", audio_bytes, filename="audio.mp3", content_type="audio/mpeg")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MUSETALK_URL}/generate_video",
                data=form,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as r:
                if r.status == 200:
                    video_bytes = await r.read()
                    frame_count = r.headers.get("X-Frame-Count", "?")
                    gen_time = r.headers.get("X-Generation-Time", "?")
                    logger.info(f"MuseTalk video: {frame_count} frames, {gen_time}s, {len(video_bytes)/1024:.0f}KB")
                    return video_bytes
                else:
                    body = await r.text()
                    logger.warning(f"MuseTalk generate_video failed: {r.status} {body}")
                    return None
    except Exception as e:
        logger.warning(f"MuseTalk generate_video error: {e}")
        return None


async def musetalk_prepare_agents(agent_ids: list[str]):
    """Prepare all agent avatars on the MuseTalk service (fire-and-forget)."""
    if not USE_VIDEO_CALL:
        return
    if not await musetalk_health():
        logger.warning("MuseTalk service not reachable, skipping avatar preparation")
        return
    for aid in agent_ids:
        await musetalk_prepare(aid)


# ── Conversation Orchestrator ────────────────────────────────────────
# 3-phase conversation engine for natural multi-agent dialogue.
# Phase 1: Plan — decide who speaks, how many, what style
# Phase 2: Primary — selected agents respond (with [pass] option)
# Phase 3: Follow-up — agents react to each other's points

from dataclasses import dataclass as _dataclass, field as _field

# Response style instructions injected per-agent based on conversation plan
RESPONSE_STYLES = {
    "lead": (
        "\n\n[RESPONSE GUIDANCE]: You are the lead responder — the topic is squarely "
        "in your expertise. Give a thorough, substantive answer (3-8 sentences). "
        "Share specific examples from your experience. Own this response."
    ),
    "contribute": (
        "\n\n[RESPONSE GUIDANCE]: Another variant is the lead on this topic, but you "
        "have a relevant perspective. Give a focused 2-4 sentence response. Add a "
        "different angle, agree/disagree, or share a quick example."
    ),
    "react": (
        "\n\n[RESPONSE GUIDANCE]: You're reacting to what other variants just said. "
        "Keep it brief — 1-2 sentences. Agree, push back, ask a pointed question, "
        "or build on their point. Think of it like a quick interjection in a real call."
    ),
    "followup": (
        "\n\n[RESPONSE GUIDANCE]: You're following up on the discussion between variants. "
        "If you have something meaningful to add — a counter-point, a 'yes and...', "
        "or a concrete example — say it in 1-3 sentences. If not, respond with [pass]."
    ),
}


@_dataclass
class ConversationPlan:
    """Blueprint for how a conversation round should play out."""
    primary_speakers: list  # list of (AgentConfig, style) tuples
    allow_followups: bool = False
    max_followup_rounds: int = 0
    topic_type: str = "normal"  # narrow | normal | broad | controversial


class ChatSession:
    """Manages one brainstorming session with natural conversation flow.

    Key design decisions:
    - 3-phase conversation: plan → primary responses → follow-up reactions
    - Variable number of responders (1-N) based on topic relevance
    - Agents can [pass] if they have nothing to add
    - Agents can address each other, not just the user
    - Response length varies by role: lead (detailed), contribute (normal), react (brief)
    - Conversations are persisted to SQLite + ChromaDB for memory
    """

    def __init__(self, agent_configs: list[AgentConfig], user_name: str = "",
                 enable_video: bool = False, meeting_id: str = ""):
        self.model_client = build_model_client()
        self.agent_configs = agent_configs
        self.conversation_history: list[dict] = []  # manual context window
        self.user_name = user_name
        self.enable_video = enable_video
        self._title_set = False

        agent_ids = [cfg.identity for cfg in agent_configs]

        if meeting_id:
            # Rejoin existing meeting — load history
            self.session_id = meeting_id
            existing = convstore.get_meeting(meeting_id)
            if existing:
                self._title_set = bool(existing.get("title"))
                # Restore conversation_history from stored messages
                msgs = convstore.get_session_messages(meeting_id, limit=50)
                for m in msgs:
                    self.conversation_history.append({
                        "role": m.get("variant") or m.get("role", "user"),
                        "text": m.get("content", ""),
                    })
                # Trim to last 20
                if len(self.conversation_history) > 20:
                    self.conversation_history = self.conversation_history[-20:]
                logger.info(f"Rejoined meeting: {meeting_id} ({len(msgs)} messages loaded)")
            else:
                # meeting_id provided but not found — create new with that ID
                convstore.create_session(meeting_id, agent_ids, user_name)
                logger.info(f"Created new meeting with provided ID: {meeting_id}")
        else:
            # Create a new persistent session
            import uuid
            self.session_id = f"session-{uuid.uuid4().hex[:12]}"
            convstore.create_session(self.session_id, agent_ids, user_name)
            logger.info(f"Created persistent session: {self.session_id}")

        # Build participant list string for system prompts
        self.participant_names = [cfg.variant for cfg in agent_configs]
        self.participant_list_str = ", ".join(self.participant_names)

        # Build agents with injected participant awareness + memory
        self.agents = self._build_agents()
        self.team = None
        self._build_team()

    def _build_agents(self) -> list[AssistantAgent]:
        """Create agents with system prompts that include participant awareness + vector-retrieved memory."""
        agents = []
        self._agent_system_prompts = {}  # Store for direct OpenRouter streaming
        participant_clause = (
            f"\n\nPARTICIPANTS IN THIS CALL: {self.participant_list_str}. "
            "Only these variants are present. Do NOT mention or reference any "
            "variant who is not in this list."
        )

        memory_preamble = (
            "\n\nIMPORTANT MEMORY INSTRUCTIONS: You have access to memories from "
            "past conversations with this user. Use them naturally — reference past "
            "discussions, follow up on ideas, and show that you remember the user. "
            "Do NOT repeat past points verbatim; instead, build on them. "
            "If the user raises a topic you discussed before, acknowledge it. "
            "You may occasionally bring up relevant past topics proactively."
        )

        user_clause = ""
        if self.user_name:
            user_clause = f"\n\nThe user's name is {self.user_name}. Address them by name occasionally."

        for cfg in self.agent_configs:
            # 1. Agent's personal notes
            notes_ctx = memstore.build_agent_notes_context(cfg.identity)

            # 2. PERSONAL MEMORY — role-specific topics routed to this agent's expertise
            personal_ctx = memstore.build_agent_memory_context(
                agent_id=cfg.identity,
                query=f"conversations with {self.user_name or 'user'}",
                n_results=5,
            )

            # 3. SHARED MEMORY — full raw conversation history (all agents)
            shared_ctx = memstore.build_shared_memory_context(
                query=f"conversations with {self.user_name or 'user'}",
                n_results=5,
            )

            memory_section = ""
            parts = [p for p in [notes_ctx, personal_ctx, shared_ctx] if p]
            if parts:
                memory_section = "\n\n" + "\n\n".join(parts)
                logger.info(f"Injected {len(memory_section)} chars of dual-layer memory for {cfg.identity}")

            # Rebuild system prompt with user's name for personalization
            base_prompt = cfg.system_prompt
            if self.user_name:
                base_prompt = agent_module.rebuild_prompt_for_owner(cfg, self.user_name)

            system_msg = (
                base_prompt
                + participant_clause
                + user_clause
                + (memory_preamble + memory_section if memory_section else "")
            )

            self._agent_system_prompts[cfg.identity] = system_msg

            agent = AssistantAgent(
                name=cfg.agent_name,
                description=cfg.description,
                model_client=self.model_client,
                system_message=system_msg,
            )
            agents.append(agent)
            logger.info(f"Created agent: {cfg.agent_name} ({cfg.variant})")
        return agents

    def _keyword_selector(self, messages) -> str | None:
        """Fast, no-LLM speaker selection based on keyword matching.
        ALWAYS returns an agent name — never None (avoids slow LLM fallback).
        Also sends an agent_typing event via _active_ws if available."""
        import random

        # Determine who has already spoken this round
        already_spoke = set()
        for msg in messages:
            src = getattr(msg, "source", "")
            if src and src != "user":
                already_spoke.add(src)

        # Available agents (haven't spoken yet)
        available = [c for c in self.agent_configs if c.agent_name not in already_spoke]
        if not available:
            available = list(self.agent_configs)  # all spoke, allow repeat

        # Get the last user message text for keyword scoring
        last_text = ""
        for msg in reversed(messages):
            content = getattr(msg, "content", "") or ""
            source = getattr(msg, "source", "")
            if source == "user" or not source:
                last_text = content.lower()
                break

        # Score each available agent by keyword overlap
        scored = []
        for cfg in available:
            keywords = set()
            for e in cfg.expertise:
                keywords.update(e.lower().split())
            keywords.update(cfg.personality.lower().replace(",", " ").split())
            score = sum(1 for kw in keywords if kw in last_text and len(kw) > 3)
            scored.append((cfg.agent_name, score))

        # Sort by score descending, pick top or random from top ties
        scored.sort(key=lambda x: -x[1])
        if scored[0][1] > 0:
            # Pick the best match
            picked = scored[0][0]
        else:
            # No keyword match — pick randomly from available
            picked = random.choice(available).agent_name

        logger.info(f"[Selector] Picked: {picked} (from {len(available)} available, already_spoke={already_spoke})")

        # Send typing indicator via the active WebSocket (if set)
        if hasattr(self, '_active_ws') and self._active_ws:
            cfg = next((c for c in self.agent_configs if c.agent_name == picked), None)
            if cfg:
                asyncio.get_event_loop().create_task(
                    self._active_ws.send_json({
                        "type": "agent_typing",
                        "agent_id": cfg.identity,
                        "variant": cfg.variant,
                    })
                )
        return picked

    def _build_team(self):
        """Build (or rebuild) the AutoGen team.
        Note: The team is kept for compatibility but conversation flow is now
        managed by the 3-phase orchestrator in handle_message()."""
        n_agents = len(self.agents)
        # Cap at N+1 to prevent runaway — actual orchestration is in handle_message
        termination = MaxMessageTermination(max_messages=n_agents + 1)

        if n_agents >= 2:
            self.team = SelectorGroupChat(
                self.agents,
                model_client=self.model_client,
                termination_condition=termination,
                selector_prompt=_selector_prompt(self.user_name or "the user"),
                allow_repeated_speaker=True,
                selector_func=self._keyword_selector,
            )
        else:
            self.team = RoundRobinGroupChat(
                self.agents,
                termination_condition=termination,
            )
        logger.info(
            f"Team built: {n_agents} agent(s), orchestrator-managed conversation flow"
        )

    def _score_all_agents(self, user_message: str) -> list[tuple]:
        """Score all agents by relevance to the user message.

        Returns list of (AgentConfig, score) sorted by score descending.
        Scoring factors (weighted):
          1. Expertise relevance (0.40) — keyword overlap with user message
          2. Recency penalty   (0.25) — penalize agents who spoke recently
          3. Diversity bonus    (0.20) — reward underrepresented agents
          4. Reactivity bonus   (0.15) — can build on prior replies?
        """
        import random

        last_text = user_message.lower()

        # Count how recently each agent spoke
        recency_map = {}
        for i, entry in enumerate(reversed(self.conversation_history)):
            role = entry.get("role", "")
            if role != "user" and role not in recency_map:
                recency_map[role] = i + 1

        # Count total speaking turns per agent
        turn_counts = {}
        for entry in self.conversation_history:
            role = entry.get("role", "")
            if role != "user":
                turn_counts[role] = turn_counts.get(role, 0) + 1
        max_turns = max(turn_counts.values()) if turn_counts else 1

        # Prior agent text for reactivity
        prior_text = " ".join([
            entry.get("text", "")
            for entry in self.conversation_history[-3:]
            if entry.get("role", "") != "user"
        ]).lower()

        scored = []
        for cfg in self.agent_configs:
            keywords = set()
            for e in cfg.expertise:
                keywords.update(e.lower().split())
            keywords.update(cfg.personality.lower().replace(",", " ").split())
            keyword_hits = sum(1 for kw in keywords if kw in last_text and len(kw) > 3)
            relevance = min(keyword_hits / 3.0, 1.0)

            recency_dist = recency_map.get(cfg.variant, len(self.conversation_history) + 5)
            recency_score = min(recency_dist / 6.0, 1.0)

            agent_turns = turn_counts.get(cfg.variant, 0)
            diversity = 1.0 - (agent_turns / (max_turns + 1))

            react_hits = sum(1 for kw in keywords if kw in prior_text and len(kw) > 3) if prior_text else 0
            reactivity = min(react_hits / 2.0, 1.0)

            total = (
                0.40 * relevance
                + 0.25 * recency_score
                + 0.20 * diversity
                + 0.15 * reactivity
            )
            total += random.uniform(0, 0.05)

            scored.append((cfg, total, relevance))
            logger.debug(
                f"[Selector] {cfg.variant}: rel={relevance:.2f} rec={recency_score:.2f} "
                f"div={diversity:.2f} react={reactivity:.2f} → {total:.3f}"
            )

        scored.sort(key=lambda x: -x[1])
        return scored

    def _plan_conversation(self, user_message: str) -> ConversationPlan:
        """Phase 1: Decide who speaks, how many, and what style — zero LLM calls.

        Uses keyword/expertise scoring to determine topic breadth:
        - Narrow topic (1 expert) → 1 lead speaker, maybe 1 reactor
        - Normal topic (2-3 experts) → 2-3 speakers with varied styles
        - Broad topic (4+ experts) → 3-4 speakers + follow-up round
        """
        scored = self._score_all_agents(user_message)
        n_agents = len(self.agent_configs)

        # Classify agents by relevance tier
        high = [(cfg, s, r) for cfg, s, r in scored if r >= 0.33]  # 1+ strong keyword hits
        medium = [(cfg, s, r) for cfg, s, r in scored if 0.01 < r < 0.33]

        # Short messages (greetings, "yes", "ok") → just 1-2 agents
        is_short = len(user_message.split()) <= 4

        if is_short:
            # Brief input — 1 agent responds conversationally
            speakers = [(scored[0][0], "contribute")]
            if n_agents >= 3 and scored[1][1] > 0.3:
                speakers.append((scored[1][0], "react"))
            return ConversationPlan(
                primary_speakers=speakers,
                allow_followups=False,
                topic_type="narrow",
            )

        if len(high) >= 3:
            # Broad or controversial topic — multiple experts have strong opinions
            speakers = [(high[0][0], "lead")]
            for cfg, s, r in high[1:min(4, len(high))]:
                speakers.append((cfg, "contribute"))
            return ConversationPlan(
                primary_speakers=speakers,
                allow_followups=True,
                max_followup_rounds=2,
                topic_type="broad",
            )

        if len(high) == 2:
            # Two strong experts — good debate potential
            speakers = [
                (high[0][0], "lead"),
                (high[1][0], "contribute"),
            ]
            # Add a reactor if there's a medium-relevance agent
            if medium and n_agents >= 3:
                speakers.append((medium[0][0], "react"))
            return ConversationPlan(
                primary_speakers=speakers,
                allow_followups=True,
                max_followup_rounds=1,
                topic_type="normal",
            )

        if len(high) == 1:
            # Narrow topic — one clear expert
            speakers = [(high[0][0], "lead")]
            # Add a contributor from remaining agents (different perspective)
            remaining = [s for s in scored if s[0] != high[0][0]]
            if remaining and n_agents >= 2:
                speakers.append((remaining[0][0], "react"))
            return ConversationPlan(
                primary_speakers=speakers,
                allow_followups=False,
                max_followup_rounds=0,
                topic_type="narrow",
            )

        # No strong keyword match — distribute based on composite score
        n_speakers = min(n_agents, 3)
        speakers = [(scored[0][0], "lead")]
        for i in range(1, n_speakers):
            speakers.append((scored[i][0], "contribute"))
        return ConversationPlan(
            primary_speakers=speakers,
            allow_followups=n_speakers >= 2,
            max_followup_rounds=1 if n_speakers >= 2 else 0,
            topic_type="normal",
        )

    def _build_llm_messages(self, agent_cfg: AgentConfig, context: str,
                            prior_replies: list, style: str = "contribute") -> list[dict]:
        """Build OpenRouter-compatible messages array for an agent.

        Args:
            agent_cfg: Agent to build messages for
            context: User message with conversation history
            prior_replies: List of dicts with 'variant' and 'content' from earlier responses
            style: One of 'lead', 'contribute', 'react', 'followup' — controls response guidance
        """
        import perception
        system_msg = self._agent_system_prompts.get(agent_cfg.identity, agent_cfg.system_prompt)
        # Inject user emotional state (Raven-inspired perception)
        emotion_ctx = perception.get_emotion_context()
        if emotion_ctx:
            system_msg += emotion_ctx
        # Inject response style guidance
        style_guidance = RESPONSE_STYLES.get(style, RESPONSE_STYLES["contribute"])
        system_msg += style_guidance

        user_content = context
        if prior_replies:
            replies_text = "\n".join([
                f"{r['variant']}: \"{r['content']}\"" for r in prior_replies
            ])
            if style == "followup":
                user_content = (
                    context
                    + f"\n\n[Discussion so far this round]\n{replies_text}"
                    + "\n\n[You're jumping back into the conversation. React to what was said, "
                    "add a follow-up thought, or respond with [pass] if you have nothing to add.]"
                )
            elif style == "react":
                user_content = (
                    context
                    + f"\n\n[Other variants just said]\n{replies_text}"
                    + "\n\n[Quick — react to what was said. Agree, disagree, or build on it. "
                    "If you truly have nothing to add, respond with [pass].]"
                )
            else:
                user_content = (
                    context
                    + f"\n\n[Other variants already responded]\n{replies_text}"
                    + "\n\n[Now it's your turn. You can respond to the user, react to what "
                    "other variants said, or offer a different perspective.]"
                )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]

    async def _stream_agent_response(self, websocket: WebSocket, agent_cfg: AgentConfig, llm_messages: list[dict]) -> str:
        """Stream a single agent's LLM response with interleaved text + audio.

        Tavus-inspired pipeline:
          - Tokens stream from OpenRouter in real-time
          - Sentence boundaries detected on-the-fly
          - Text sent IMMEDIATELY when sentence complete (~800ms to first text)
          - TTS fired concurrently in background
          - Audio sent in-order as TTS completes (can overlap with LLM still generating)
        """
        import time as _time
        t0 = _time.time()

        await websocket.send_json({
            "type": "agent_stream_start",
            "agent_id": agent_cfg.identity,
            "agent_name": agent_cfg.agent_name,
            "variant": agent_cfg.variant,
        })

        buffer = ""
        full_text = ""
        chunk_index = 0
        tts_tasks = []  # list of (chunk_index, asyncio.Task)
        next_audio_send = 0
        voice = agent_cfg.voice or "en-US-AndrewMultilingualNeural"

        async for token in _stream_llm_tokens(llm_messages):
            buffer += token
            full_text += token

            # Try to extract a complete sentence
            result = _try_extract_sentence(buffer)
            if result:
                sentence, buffer = result

                # Send text IMMEDIATELY — user sees text sub-second
                await websocket.send_json({
                    "type": "agent_message_chunk",
                    "agent_id": agent_cfg.identity,
                    "agent_name": agent_cfg.agent_name,
                    "variant": agent_cfg.variant,
                    "content": sentence,
                    "audio": "",
                    "format": "mp3",
                    "chunk_index": chunk_index,
                    "is_last": False,
                })

                if chunk_index == 0:
                    latency = _time.time() - t0
                    logger.info(f"[TokenStream] {agent_cfg.variant} first text in {latency:.2f}s")

                # Fire TTS in background
                task = asyncio.ensure_future(generate_tts(sentence, voice))
                tts_tasks.append((chunk_index, task))
                chunk_index += 1

            # Check if any pending TTS is done — send audio in-order
            while next_audio_send < len(tts_tasks):
                idx, task = tts_tasks[next_audio_send]
                if task.done():
                    try:
                        audio_bytes = task.result()
                        if audio_bytes:
                            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                            await websocket.send_json({
                                "type": "agent_audio_chunk",
                                "agent_id": agent_cfg.identity,
                                "audio": audio_b64,
                                "format": "mp3",
                                "chunk_index": idx,
                            })
                    except Exception as e:
                        logger.warning(f"[TokenStream] TTS error chunk {idx}: {e}")
                    next_audio_send += 1
                else:
                    break

        # Send remaining buffer as last text chunk
        if buffer.strip():
            await websocket.send_json({
                "type": "agent_message_chunk",
                "agent_id": agent_cfg.identity,
                "agent_name": agent_cfg.agent_name,
                "variant": agent_cfg.variant,
                "content": buffer.strip(),
                "audio": "",
                "format": "mp3",
                "chunk_index": chunk_index,
                "is_last": True,
            })
            task = asyncio.ensure_future(generate_tts(buffer.strip(), voice))
            tts_tasks.append((chunk_index, task))
            chunk_index += 1

        # Send remaining audio in order (most are likely already done)
        for i in range(next_audio_send, len(tts_tasks)):
            idx, task = tts_tasks[i]
            try:
                audio_bytes = await task
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    await websocket.send_json({
                        "type": "agent_audio_chunk",
                        "agent_id": agent_cfg.identity,
                        "audio": audio_b64,
                        "format": "mp3",
                        "chunk_index": idx,
                    })
            except Exception as e:
                logger.warning(f"[TokenStream] TTS error chunk {idx}: {e}")

        # Signal streaming end
        await websocket.send_json({
            "type": "agent_stream_end",
            "agent_id": agent_cfg.identity,
            "variant": agent_cfg.variant,
            "full_content": full_text,
        })

        total = _time.time() - t0
        logger.info(f"[TokenStream] {agent_cfg.variant} done: {chunk_index} chunks, {len(full_text)} chars in {total:.1f}s")
        return full_text

    async def _fallback_generate(self, agent_cfg: AgentConfig, llm_messages: list[dict]) -> str:
        """Non-streaming LLM call as fallback when streaming fails."""
        try:
            from autogen_core.models import UserMessage as CoreUserMessage, SystemMessage as CoreSystemMessage
            msgs = []
            for m in llm_messages:
                if m["role"] == "system":
                    msgs.append(CoreSystemMessage(content=m["content"]))
                else:
                    msgs.append(CoreUserMessage(content=m["content"], source="user"))
            result = await self.model_client.create(msgs)
            return result.content if hasattr(result, "content") else str(result)
        except Exception as e:
            logger.error(f"Fallback generate failed: {e}")
            return "I apologize, but I'm having trouble responding right now."

    def _is_pass(self, text: str) -> bool:
        """Check if an agent's response is a [pass] — they chose not to speak."""
        stripped = text.strip().lower()
        return stripped in ("[pass]", "pass", "[no comment]", "no comment") or len(stripped) < 3

    async def _run_agent_turn(self, websocket: WebSocket, agent_cfg: AgentConfig,
                               context: str, prior_replies: list, style: str) -> dict | None:
        """Run a single agent's turn: typing → LLM stream → text+audio.
        Returns reply dict or None if agent passed."""
        # Send typing indicator
        await websocket.send_json({
            "type": "agent_typing",
            "agent_id": agent_cfg.identity,
            "variant": agent_cfg.variant,
        })

        # Build messages with style-specific instructions
        llm_messages = self._build_llm_messages(agent_cfg, context, prior_replies, style)

        try:
            full_text = await self._stream_agent_response(websocket, agent_cfg, llm_messages)
        except Exception as e:
            logger.error(f"Streaming failed for {agent_cfg.variant}, falling back: {e}")
            try:
                full_text = await self._fallback_generate(agent_cfg, llm_messages)
                await _stream_text_and_audio(
                    websocket, full_text, agent_cfg.voice,
                    agent_cfg.identity, agent_cfg.agent_name, agent_cfg.variant,
                )
            except Exception as e2:
                logger.error(f"Fallback also failed for {agent_cfg.variant}: {e2}")
                await websocket.send_json({"type": "error", "content": str(e2)})
                return None

        # Check if agent passed (chose not to speak)
        if self._is_pass(full_text):
            logger.info(f"[Orchestrator] {agent_cfg.variant} passed (style={style})")
            await websocket.send_json({
                "type": "agent_skipped",
                "agent_id": agent_cfg.identity,
                "variant": agent_cfg.variant,
            })
            return None

        return {
            "variant": agent_cfg.variant,
            "content": full_text,
            "agent_id": agent_cfg.identity,
        }

    async def handle_message(self, user_message: str, websocket: WebSocket):
        """3-phase conversation engine for natural multi-agent dialogue.

        Phase 1: PLAN — decide who speaks, how many, what style (rule-based, ~0ms)
        Phase 2: PRIMARY — selected agents respond with role-appropriate styles
        Phase 3: FOLLOW-UP — agents react to each other's points (optional)

        Key behaviors:
        - Variable number of responders (1-4) based on topic analysis
        - Agents can [pass] if they have nothing to add
        - Lead agents give detailed responses; reactors keep it brief
        - Follow-up rounds let agents have agent-to-agent conversation
        """
        import time as _time
        t0 = _time.time()
        logger.info(f"[handle_message] Processing: {user_message[:60]}...")

        self._active_ws = websocket
        context = self._build_context(user_message)

        # ── Phase 1: Plan the conversation ──
        plan = self._plan_conversation(user_message)
        speaker_names = [cfg.variant for cfg, _ in plan.primary_speakers]
        logger.info(
            f"[Orchestrator] Plan: {plan.topic_type} topic, "
            f"{len(plan.primary_speakers)} speakers ({', '.join(speaker_names)}), "
            f"followups={'yes' if plan.allow_followups else 'no'}"
        )

        agent_replies = []

        # ── Phase 2: Primary responses ──
        for agent_cfg, style in plan.primary_speakers:
            reply = await self._run_agent_turn(
                websocket, agent_cfg, context, agent_replies, style
            )
            if reply:
                elapsed = _time.time() - t0
                logger.info(f"[Orchestrator] {agent_cfg.variant} replied ({style}) in {elapsed:.1f}s")
                agent_replies.append(reply)

        # ── Phase 3: Follow-up rounds ──
        if plan.allow_followups and plan.max_followup_rounds > 0 and len(agent_replies) >= 2:
            # Agents who already spoke can jump back in to react to each other
            primary_ids = {cfg.identity for cfg, _ in plan.primary_speakers}

            for fround in range(plan.max_followup_rounds):
                # Pick the agent whose expertise is most relevant to what was just said
                combined_text = " ".join(r["content"] for r in agent_replies[-3:])
                scored = self._score_all_agents(combined_text)

                # Find an agent who spoke in primary and has something to react to
                followup_agent = None
                for cfg, score, rel in scored:
                    if cfg.identity in primary_ids and rel > 0.1:
                        # Check they're not the last speaker (avoid repeating)
                        if agent_replies and agent_replies[-1]["agent_id"] != cfg.identity:
                            followup_agent = cfg
                            break

                if not followup_agent:
                    # Try any agent who hasn't dominated the conversation
                    spoke_count = {}
                    for r in agent_replies:
                        spoke_count[r["agent_id"]] = spoke_count.get(r["agent_id"], 0) + 1
                    for cfg, score, rel in scored:
                        if spoke_count.get(cfg.identity, 0) < 2 and \
                           (not agent_replies or agent_replies[-1]["agent_id"] != cfg.identity):
                            followup_agent = cfg
                            break

                if not followup_agent:
                    logger.info(f"[Orchestrator] No suitable follow-up agent for round {fround+1}")
                    break

                reply = await self._run_agent_turn(
                    websocket, followup_agent, context, agent_replies, "followup"
                )
                if reply:
                    logger.info(f"[Orchestrator] Follow-up {fround+1}: {followup_agent.variant}")
                    agent_replies.append(reply)
                else:
                    # Agent passed — no more follow-ups needed
                    logger.info(f"[Orchestrator] {followup_agent.variant} passed follow-up, ending round")
                    break

        total = _time.time() - t0
        logger.info(
            f"[handle_message] Complete: {len(agent_replies)} replies in {total:.1f}s "
            f"(plan: {plan.topic_type}, {len(plan.primary_speakers)} primary)"
        )

        # Update manual conversation history
        self.conversation_history.append({"role": "user", "text": user_message})
        for reply in agent_replies:
            self.conversation_history.append({
                "role": reply["variant"],
                "text": reply["content"],
            })
        if len(self.conversation_history) > 30:
            self.conversation_history = self.conversation_history[-30:]

        # Persist to SQLite
        convstore.add_message(self.session_id, "user", user_message, self.user_name or "User")
        for reply in agent_replies:
            convstore.add_message(
                self.session_id,
                reply.get("agent_id", reply["variant"]),
                reply["content"],
                reply["variant"],
            )

        # Persist to ChromaDB vector store for semantic retrieval
        if agent_replies:
            memstore.store_group_round(
                session_id=self.session_id,
                user_message=user_message,
                agent_replies=agent_replies,
                user_name=self.user_name,
            )

            # Generate and store agent notes (background, non-blocking)
            asyncio.create_task(
                self._generate_agent_notes(user_message, agent_replies)
            )

    async def _generate_agent_notes(self, user_message: str, agent_replies: list[dict]):
        """Background task: ask the LLM to generate brief notes about the conversation
        for each agent, then store them in ChromaDB for future sessions."""
        for reply in agent_replies:
            agent_id = reply.get("agent_id", "")
            variant = reply.get("variant", "")
            content = reply.get("content", "")
            if not agent_id:
                continue

            note_prompt = (
                f"You are {variant}. Summarize this exchange in 1-2 sentences as a note "
                f"about the user ({self.user_name or 'User'}) for your future reference. "
                f"Focus on what the user cares about, what was discussed, and any commitments made.\n\n"
                f"User said: {user_message[:300]}\n"
                f"You replied: {content[:300]}\n\n"
                f"Write ONLY the note, nothing else:"
            )

            try:
                from autogen_core.models import UserMessage as CoreUserMessage
                result = await self.model_client.create([CoreUserMessage(content=note_prompt, source="user")])
                note_text = result.content.strip() if hasattr(result, "content") else str(result)
                if note_text and len(note_text) > 10:
                    memstore.store_agent_note(agent_id, variant, note_text)
                    # Also save to SQLite for backward compat
                    convstore.save_agent_notes(agent_id, note_text)
            except Exception as e:
                logger.error(f"[Memory] Failed to generate note for {variant}: {e}")

    def _build_context(self, user_message: str) -> str:
        """Build a prompt that includes recent conversation history + dual-layer vector memories."""
        parts = []

        # SHARED MEMORY — full raw conversation context from all agents
        shared_ctx = memstore.build_shared_memory_context(
            query=user_message,
            n_results=3,
        )
        if shared_ctx:
            parts.append(shared_ctx)

        # Add recent in-session conversation history
        if self.conversation_history:
            history_lines = []
            for entry in self.conversation_history[-10:]:
                history_lines.append(f"{entry['role']}: {entry['text']}")
            history_str = "\n".join(history_lines)
            parts.append(f"[Previous conversation in this session]\n{history_str}")

        parts.append(f"[Latest message from the user]\n{user_message}")

        return "\n\n".join(parts)


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks for streaming TTS.
    Groups very short sentences together to avoid too many tiny audio chunks."""
    import re
    # Split on sentence-ending punctuation followed by whitespace
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    if not raw:
        return [text] if text.strip() else []

    # Merge very short fragments (< 40 chars) with the next sentence
    merged = []
    buf = ""
    for s in raw:
        buf = (buf + " " + s).strip() if buf else s
        if len(buf) >= 40:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] = merged[-1] + " " + buf
        else:
            merged.append(buf)
    return merged


async def _stream_text_and_audio(
    websocket: WebSocket,
    full_text: str,
    voice: str,
    agent_id: str,
    agent_name: str,
    variant_name: str,
):
    """Stream agent response with PARALLEL TTS generation.

    Pipeline (Tavus-inspired):
      1. Split text into sentences
      2. Fire off TTS for ALL sentences concurrently
      3. Send each chunk in order as its TTS completes
      4. Since all TTS runs in parallel, total time ≈ max(single sentence TTS)
         instead of sum(all sentence TTS) — typically 3-5x faster.
    """
    import time as _time

    sentences = _split_into_sentences(full_text)
    if not sentences:
        await websocket.send_json({
            "type": "agent_message",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "variant": variant_name,
            "content": full_text,
        })
        return

    # Signal that streaming is starting
    await websocket.send_json({
        "type": "agent_stream_start",
        "agent_id": agent_id,
        "agent_name": agent_name,
        "variant": variant_name,
        "total_sentences": len(sentences),
    })

    t0 = _time.time()

    # ── PARALLEL TTS: fire all sentence TTS concurrently ──
    async def _tts_for_sentence(sentence: str) -> str:
        """Generate TTS for one sentence, return base64 audio."""
        try:
            audio_bytes = await generate_tts(sentence, voice)
            return base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
        except Exception as e:
            logger.warning(f"[ParallelTTS] Failed for '{sentence[:30]}...': {e}")
            return ""

    # Launch all TTS tasks at once
    tts_futures = [asyncio.ensure_future(_tts_for_sentence(s)) for s in sentences]

    first_chunk_logged = False
    for i, (sentence, future) in enumerate(zip(sentences, tts_futures)):
        # Await this sentence's TTS (others are generating concurrently)
        audio_b64 = await future

        if not first_chunk_logged:
            first_latency = _time.time() - t0
            logger.info(f"[ParallelTTS] {variant_name} first chunk ready in {first_latency:.2f}s")
            first_chunk_logged = True

        # Send text + audio together
        await websocket.send_json({
            "type": "agent_message_chunk",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "variant": variant_name,
            "content": sentence,
            "audio": audio_b64,
            "format": "mp3",
            "chunk_index": i,
            "is_last": i == len(sentences) - 1,
        })
        elapsed = _time.time() - t0
        logger.debug(f"[ParallelTTS] {variant_name} chunk {i+1}/{len(sentences)} sent ({elapsed:.1f}s)")

    # Signal streaming complete
    await websocket.send_json({
        "type": "agent_stream_end",
        "agent_id": agent_id,
        "variant": variant_name,
        "full_content": full_text,
    })
    total = _time.time() - t0
    logger.info(f"[ParallelTTS] {variant_name} streamed {len(sentences)} chunks in {total:.1f}s (was ~{total * len(sentences):.1f}s sequential)")


async def _generate_and_send_audio(
    websocket: WebSocket,
    text: str,
    voice: str,
    agent_id: str,
    variant_name: str,
    enable_video: bool = False,
):
    """Legacy fallback: generate full TTS audio and send it over WebSocket."""
    try:
        audio_bytes = await generate_tts(text, voice)
        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            await websocket.send_json({
                "type": "agent_audio",
                "agent_id": agent_id,
                "variant": variant_name,
                "audio": audio_b64,
                "format": "mp3",
            })

            if enable_video:
                asyncio.create_task(
                    _generate_and_send_video(
                        websocket, agent_id, variant_name, audio_bytes
                    )
                )
    except Exception as e:
        logger.warning(f"TTS/audio failed for {agent_id}: {e}")


async def _generate_and_send_video(
    websocket: WebSocket,
    agent_id: str,
    variant_name: str,
    audio_bytes: bytes,
):
    """Background task: send TTS audio to MuseTalk, get MP4 video back."""
    try:
        video_bytes = await musetalk_generate_video(agent_id, audio_bytes)
        if video_bytes:
            video_b64 = base64.b64encode(video_bytes).decode("utf-8")
            logger.info(
                f"Sending video to frontend for {agent_id}: "
                f"{len(video_bytes)/1024:.0f}KB MP4"
            )
            await websocket.send_json({
                "type": "agent_video",
                "agent_id": agent_id,
                "variant": variant_name,
                "video": video_b64,  # base64 MP4
                "format": "mp4",
            })
    except Exception as e:
        logger.warning(f"Video generation failed for {agent_id}: {e}")


# ── Token-level LLM Streaming (Tavus-inspired pipeline) ──────────────

import re as _re


def _try_extract_sentence(buffer: str) -> tuple | None:
    """Try to extract a complete sentence from the token buffer.
    Returns (sentence, remainder) or None if no complete sentence yet.
    Requires sentence to be ≥30 chars to avoid splitting on abbreviations like 'Dr.'"""
    match = _re.search(r'[.!?]\s', buffer)
    if match:
        end = match.start() + 1  # Include the punctuation
        sentence = buffer[:end].strip()
        remainder = buffer[end:].lstrip()
        if len(sentence) >= 30:
            return sentence, remainder
    return None


async def _stream_llm_tokens(messages: list[dict]):
    """Async generator: yield tokens from OpenRouter's streaming API (SSE).
    Uses aiohttp for non-blocking streaming HTTP."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "stream": True,
    }

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"OpenRouter streaming failed: {resp.status} {body[:200]}")
            while True:
                line = await resp.content.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str or not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# ── Global session (created on first WebSocket connect) ──────────────

active_session: Optional[ChatSession] = None
enabled_agent_ids: list[str] = []


@app.get("/health")
async def health():
    return {"status": "ok", "agents": enabled_agent_ids}


@app.get("/memory/stats")
async def memory_stats():
    """Show per-agent vector memory stats."""
    all_stats = memstore.get_all_memory_stats()
    agent_stats = []
    for aid in enabled_agent_ids:
        agent_stats.append(memstore.get_agent_memory_stats(aid))
    return {"global": all_stats, "agents": agent_stats}


@app.get("/agents")
async def list_agents():
    """Return full agent config for frontend consumption."""
    return [
        {
            "id": cfg.identity,
            "variant": cfg.variant,
            "description": cfg.description,
            "tagline": cfg.tagline,
            "emoji": cfg.emoji,
            "color": cfg.color,
            "personality": cfg.personality,
            "backstory": cfg.backstory,
            "image": f"/images/{cfg.image.split('/')[-1]}" if cfg.image else "",
            "expertise": cfg.expertise,
        }
        for cfg in agent_module.AGENT_REGISTRY.values()
    ]


# ── Pydantic models for agent CRUD ─────────────────────────────────────

class GenerateAgentRequest(BaseModel):
    name: str                           # e.g. "Elon Musk" or "The Hacker"
    agent_type: str = "variant"         # "variant" (of me) or "real_figure"
    context: str = ""                   # optional extra context from user
    user_name: str = ""                 # the user's real name (from About Me)

class AddAgentRequest(BaseModel):
    id: str
    agent_name: str
    variant: str
    tagline: str = ""
    emoji: str = "🤖"
    color: str = "zinc"
    personality: str = ""
    backstory: str = ""
    expertise: list[str] = []
    description: str = ""
    voice: str = "en-US-AndrewMultilingualNeural"
    image: str = ""
    image_prompt: str = ""
    projects: list[dict] = []


def build_agent_generator_prompt(user_name: str = "") -> str:
    """Build the system prompt for the AI agent designer, personalized with user_name."""
    owner = user_name or "the user"
    return f"""You are an expert AI character designer for a brainstorming app called "The Multiverse of {owner}".

Your job: Given a name and type, generate a complete, vivid agent profile in JSON format.

RULES:
- If type is "variant": The agent is a variant of "{owner}" from a parallel universe who took a different career path. The name describes their archetype (e.g. "The Hacker", "The Chef", "The Philosopher").
- If type is "real_figure": The agent is inspired by a real public figure (e.g. "Elon Musk", "Steve Jobs", "Marie Curie"). Create a character that captures their known expertise, personality, and speaking style. Use their real name as the variant.
- Generate a unique slug id (lowercase, hyphenated, prefixed with "{owner.lower().replace(' ','-')}-" for variants or the person's last name for real figures).
- Pick a fitting emoji and color from: amber, violet, blue, emerald, rose, cyan, orange, pink, red, green, purple, yellow, teal, indigo.
- Write a compelling 2-3 sentence backstory.
- Write a short punchy tagline (one sentence).
- List 4-6 areas of expertise.
- Write a 1-sentence description for the AI selector.
- Generate 2-3 realistic project entries with name, role, period, description, technologies, outcome, and lesson.
- personality should be a comma-separated list of 3-4 traits.
- IMPORTANT: Also generate an "image_prompt" field — a detailed photography-style prompt for generating a portrait photo of this character. The prompt should describe a professional headshot/portrait photograph: describe their appearance, clothing, setting, lighting, and mood. Always start with "Professional portrait photograph of" and end with "shot on Sony A7III, 85mm lens, shallow depth of field, studio lighting". For real figures, describe them as they're commonly recognized. For variants, invent a fitting appearance.

Respond with ONLY valid JSON (no markdown, no explanation). Use this exact structure:
{{
  "id": "...",
  "agent_name": "...",
  "variant": "...",
  "tagline": "...",
  "emoji": "...",
  "color": "...",
  "personality": "...",
  "backstory": "...",
  "expertise": ["..."],
  "description": "...",
  "voice": "en-US-AndrewMultilingualNeural",
  "image": "",
  "image_prompt": "Professional portrait photograph of ...",
  "projects": [
    {{
      "name": "...",
      "role": "...",
      "period": "...",
      "description": "...",
      "technologies": ["..."],
      "outcome": "...",
      "lesson": "..."
    }}
  ]
}}"""


async def generate_image_nano_banana(image_prompt: str, agent_id: str, progress_cb=None, use_reference: bool = False) -> str:
    """Call Nano Banana 2 to generate a portrait image. Returns the local filename or empty string.
    progress_cb: optional async callback(message: str) for progress updates.
    use_reference: if True and user-reference.jpg exists, pass it as image_input."""
    if not KIE_API_KEY:
        logger.warning("KIE_API_KEY not set, skipping image generation")
        return ""

    async def _progress(msg: str):
        if progress_cb:
            await progress_cb(msg)

    # Build image_input from reference photo if available
    image_input = []
    if use_reference and USER_REFERENCE_PHOTO.exists():
        try:
            with open(USER_REFERENCE_PHOTO, "rb") as f:
                ref_bytes = f.read()
            ref_b64 = base64.b64encode(ref_bytes).decode("utf-8")
            image_input = [f"data:image/jpeg;base64,{ref_b64}"]
            await _progress("Using your reference photo for character likeness...")
            logger.info(f"Reference photo loaded ({len(ref_bytes)} bytes)")
        except Exception as e:
            logger.warning(f"Failed to load reference photo: {e}")

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Create generation task
            await _progress("Submitting portrait to image generator...")
            logger.info(f"Creating image task for agent {agent_id}...")

            task_input = {
                "prompt": image_prompt,
                "aspect_ratio": "1:1",
                "google_search": False,
                "resolution": "1K",
                "output_format": "jpg",
            }
            if image_input:
                task_input["image_input"] = image_input

            async with session.post(
                "https://api.kie.ai/api/v1/jobs/createTask",
                headers={
                    "Authorization": f"Bearer {KIE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "nano-banana-2",
                    "input": task_input,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Kie.ai createTask error {resp.status}: {body}")
                    return ""
                data = await resp.json()
                if data.get("code") != 200:
                    logger.error(f"Kie.ai createTask failed: {data}")
                    return ""
                task_id = data["data"]["taskId"]
                logger.info(f"Kie.ai task created: {task_id}")

            # Step 2: Poll for result (max ~120s, poll every 5s)
            await _progress("Waiting for portrait to render...")
            for attempt in range(24):
                await asyncio.sleep(5)
                await _progress(f"Rendering portrait... ({(attempt+1)*5}s elapsed)")
                async with session.get(
                    f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={task_id}",
                    headers={"Authorization": f"Bearer {KIE_API_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as poll_resp:
                    if poll_resp.status != 200:
                        continue
                    poll_data = await poll_resp.json()
                    state = poll_data.get("data", {}).get("state", "")

                    if state == "success":
                        result_json = json.loads(poll_data["data"].get("resultJson", "{}"))
                        urls = result_json.get("resultUrls", [])
                        if urls:
                            image_url = urls[0]
                            logger.info(f"Image ready: {image_url}")

                            # Step 3: Download image to frontend/public/images/
                            await _progress("Downloading portrait image...")
                            filename = f"{agent_id}.jpg"
                            save_path = IMAGES_DIR / filename
                            IMAGES_DIR.mkdir(parents=True, exist_ok=True)

                            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as img_resp:
                                if img_resp.status == 200:
                                    with open(save_path, "wb") as f:
                                        f.write(await img_resp.read())
                                    logger.info(f"Image saved: {save_path}")
                                    return filename
                        return ""

                    elif state == "fail":
                        fail_msg = poll_data.get("data", {}).get("failMsg", "unknown")
                        logger.error(f"Kie.ai image generation failed: {fail_msg}")
                        return ""

                    # state == "waiting" — keep polling
                    logger.debug(f"Kie.ai poll attempt {attempt+1}: state={state}")

            logger.warning(f"Kie.ai image generation timed out for {agent_id}")
            return ""

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return ""


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/agents/generate")
async def generate_agent_config(req: GenerateAgentRequest):
    """Use the LLM to generate a full agent config + portrait image.
    Returns a Server-Sent Events stream with progress updates."""
    if not OPENROUTER_API_KEY:
        return StreamingResponse(
            iter([_sse_event("error", {"error": "OPENROUTER_API_KEY not set"})]),
            media_type="text/event-stream",
        )

    user_name = req.user_name or "User"
    prompt = build_agent_generator_prompt(user_name)
    user_msg = f"Name: {req.name}\nType: {req.agent_type}"
    if req.context:
        user_msg += f"\nAdditional context: {req.context}"

    async def event_generator():
        content = ""
        try:
            # ── Step 1: LLM generates agent config + image_prompt ──
            yield _sse_event("progress", {
                "step": "llm",
                "message": f"Designing {req.name}'s character profile...",
            })

            # Retry up to 2 times with increasing timeout (generation can be slow)
            llm_timeout = 180
            last_err = ""
            for attempt in range(2):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": OPENROUTER_MODEL,
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": user_msg},
                                ],
                                "temperature": 0.8,
                                "max_tokens": 2500,
                            },
                            timeout=aiohttp.ClientTimeout(total=llm_timeout),
                        ) as resp:
                            if resp.status != 200:
                                body = await resp.text()
                                last_err = f"LLM API error: {resp.status}"
                                logger.error(f"OpenRouter error {resp.status}: {body}")
                                if attempt == 0:
                                    yield _sse_event("progress", {"step": "retry", "message": f"LLM returned {resp.status}, retrying..."})
                                    llm_timeout = 240
                                    continue
                                yield _sse_event("error", {"error": last_err})
                                return

                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            break  # success
                except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as te:
                    last_err = f"LLM call timed out after {llm_timeout}s"
                    logger.warning(f"Agent generation attempt {attempt+1} failed: {type(te).__name__}")
                    if attempt == 0:
                        yield _sse_event("progress", {"step": "retry", "message": "LLM timed out, retrying with longer timeout..."})
                        llm_timeout = 300
                        continue
                    yield _sse_event("error", {"error": last_err})
                    return
            else:
                yield _sse_event("error", {"error": last_err or "LLM generation failed after retries"})
                return

            # Strip markdown fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            agent_config = json.loads(content)

            # Sanitize: ensure critical string fields aren't booleans or missing
            if not isinstance(agent_config.get("variant"), str) or not agent_config["variant"]:
                agent_config["variant"] = req.name
            if not isinstance(agent_config.get("agent_name"), str) or not agent_config["agent_name"]:
                agent_config["agent_name"] = req.name.replace(" ", "")
            if not isinstance(agent_config.get("id"), str) or not agent_config["id"]:
                slug = req.name.lower().replace(" ", "-")
                agent_config["id"] = f"{(req.user_name or 'agent').lower().replace(' ', '-')}-{slug}"
            for field in ("tagline", "emoji", "color", "personality", "backstory", "description", "voice"):
                if not isinstance(agent_config.get(field), str):
                    agent_config[field] = ""
            if not isinstance(agent_config.get("expertise"), list):
                agent_config["expertise"] = []
            if not isinstance(agent_config.get("projects"), list):
                agent_config["projects"] = []

            yield _sse_event("progress", {
                "step": "llm_done",
                "message": f"Character profile ready! Meet \"{agent_config.get('variant', req.name)}\"",
            })

            # ── Step 2: Generate image via Nano Banana 2 ──
            # Clear any LLM-generated image field (it's supposed to be empty)
            agent_config["image"] = ""
            image_prompt = agent_config.get("image_prompt", "")
            agent_id = agent_config.get("id", "unknown-agent")

            if image_prompt and KIE_API_KEY:
                yield _sse_event("progress", {
                    "step": "image_start",
                    "message": "Generating portrait photo...",
                })

                async def image_progress(msg: str):
                    pass  # We yield from the outer generator below

                # We can't yield from inside a callback, so we inline progress here
                # by calling generate_image_nano_banana with a queue-based callback
                progress_queue: asyncio.Queue = asyncio.Queue()

                async def queue_progress(msg: str):
                    await progress_queue.put(msg)

                # Run image generation in background task
                # Use reference photo for "variant" agents (parallel universe versions of the user)
                is_variant = req.agent_type == "variant"
                image_task = asyncio.create_task(
                    generate_image_nano_banana(image_prompt, agent_id, progress_cb=queue_progress, use_reference=is_variant)
                )

                # Yield progress events while image generates
                while not image_task.done():
                    try:
                        msg = await asyncio.wait_for(progress_queue.get(), timeout=2.0)
                        yield _sse_event("progress", {
                            "step": "image_progress",
                            "message": msg,
                        })
                    except asyncio.TimeoutError:
                        # No progress update yet, send keepalive
                        pass

                # Drain any remaining messages
                while not progress_queue.empty():
                    msg = await progress_queue.get()
                    yield _sse_event("progress", {
                        "step": "image_progress",
                        "message": msg,
                    })

                filename = image_task.result()
                if filename:
                    agent_config["image"] = filename
                    logger.info(f"Agent {agent_id} portrait: {filename}")
                    yield _sse_event("progress", {
                        "step": "image_done",
                        "message": "Portrait photo saved!",
                    })
                else:
                    yield _sse_event("progress", {
                        "step": "image_skip",
                        "message": "Portrait generation skipped or failed — using emoji instead",
                    })
            else:
                skip_reason = "No API key for image generation" if not KIE_API_KEY else "No image prompt"
                yield _sse_event("progress", {
                    "step": "image_skip",
                    "message": f"{skip_reason} — using emoji avatar",
                })

            # Keep image_prompt in SSE result for frontend regeneration, but strip from saved config
            saved_image_prompt = agent_config.get("image_prompt", "")

            # ── Step 3: Done ──
            yield _sse_event("progress", {
                "step": "complete",
                "message": "Agent is ready! Review and add to your team.",
            })
            # Send result with image_prompt for frontend use
            yield _sse_event("result", {"agent": agent_config})

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}\nContent: {content}")
            yield _sse_event("error", {"error": "LLM returned invalid JSON, please try again"})
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Agent generation failed: {type(e).__name__}: {e}\n{tb}")
            err_msg = str(e) or f"{type(e).__name__} during agent generation"
            yield _sse_event("error", {"error": err_msg})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class UploadAgentImageRequest(BaseModel):
    agent_id: str
    photo: str  # base64 data URI

@app.post("/agents/upload-image")
async def upload_agent_image(req: UploadAgentImageRequest):
    """Upload a custom image for an agent (before or after adding to team)."""
    try:
        data_uri = req.photo
        if "," in data_uri:
            header, b64_data = data_uri.split(",", 1)
        else:
            b64_data = data_uri

        image_bytes = base64.b64decode(b64_data)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{req.agent_id}.jpg"
        save_path = IMAGES_DIR / filename
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"Agent image uploaded: {save_path} ({len(image_bytes)} bytes)")
        return {"ok": True, "image": filename}
    except Exception as e:
        logger.error(f"Failed to upload agent image: {e}")
        return {"error": str(e)}


class RegenerateImageRequest(BaseModel):
    agent_id: str
    image_prompt: str
    agent_type: str = "variant"  # "variant" or "real_figure"

@app.post("/agents/regenerate-image")
async def regenerate_agent_image(req: RegenerateImageRequest):
    """Regenerate an agent's portrait image using the image prompt."""
    if not KIE_API_KEY:
        return {"error": "Image generation API key not configured"}

    try:
        is_variant = req.agent_type == "variant"
        filename = await generate_image_nano_banana(
            req.image_prompt, req.agent_id,
            use_reference=is_variant,
        )
        if filename:
            return {"ok": True, "image": filename}
        return {"error": "Image generation failed"}
    except Exception as e:
        logger.error(f"Failed to regenerate image: {e}")
        return {"error": str(e)}


@app.post("/agents")
async def add_agent(req: AddAgentRequest):
    """Add a new agent to agents.config.json and reload the registry."""
    config_path = get_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Check for duplicate id
    existing_ids = [a["id"] for a in config.get("agents", [])]
    if req.id in existing_ids:
        return {"error": f"Agent with id '{req.id}' already exists"}

    new_agent = req.model_dump()
    # Strip image_prompt — not needed in persistent config
    new_agent.pop("image_prompt", None)
    config["agents"].append(new_agent)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    reload_agents()
    # Reload topic router with updated agent list
    memstore.load_agent_topics(config["agents"])
    logger.info(f"Added agent: {req.id} ({req.variant})")
    return {"ok": True, "id": req.id, "total_agents": len(agent_module.AGENT_REGISTRY)}


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Remove an agent from agents.config.json and reload the registry."""
    config_path = get_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    original_count = len(config.get("agents", []))
    config["agents"] = [a for a in config.get("agents", []) if a.get("id") != agent_id]

    if len(config["agents"]) == original_count:
        return {"error": f"Agent '{agent_id}' not found"}

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    reload_agents()
    # Reload topic router with updated agent list
    memstore.load_agent_topics(config["agents"])
    logger.info(f"Removed agent: {agent_id}")
    return {"ok": True, "id": agent_id, "total_agents": len(agent_module.AGENT_REGISTRY)}


# ── Server-side STT via Deepgram ─────────────────────────────────────

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")


@app.websocket("/ws/stt")
async def websocket_stt(websocket: WebSocket):
    """Real-time speech-to-text via Deepgram streaming API.

    Protocol:
      Client → Server: binary audio chunks (WebM/Opus from MediaRecorder)
      Server → Client: JSON transcripts {"type":"transcript","text":"...","is_final":bool,"speech_final":bool}
    """
    await websocket.accept()

    if not DEEPGRAM_API_KEY:
        await websocket.send_json({"type": "error", "message": "Server-side STT not configured (DEEPGRAM_API_KEY missing)"})
        await websocket.close()
        return

    deepgram_url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-2&language=en&smart_format=true"
        "&interim_results=true&endpointing=300&vad_events=true"
        "&encoding=linear16&sample_rate=16000&channels=1"
    )
    dg_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    dg_ws = None
    try:
        session = aiohttp.ClientSession()
        dg_ws = await session.ws_connect(deepgram_url, headers=dg_headers)
        logger.info("[STT] Connected to Deepgram streaming API")

        async def forward_audio():
            """Client → Deepgram: forward audio chunks."""
            try:
                while True:
                    msg = await websocket.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    if "bytes" in msg:
                        await dg_ws.send_bytes(msg["bytes"])
                    elif "text" in msg:
                        data = json.loads(msg["text"])
                        if data.get("type") == "stop":
                            await dg_ws.send_str(json.dumps({"type": "CloseStream"}))
                            break
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning(f"[STT] Audio forward error: {e}")
            finally:
                try:
                    await dg_ws.send_str(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass

        async def forward_transcripts():
            """Deepgram → Client: forward transcription results."""
            try:
                async for msg in dg_ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "Results":
                            channel = data.get("channel", {})
                            alts = channel.get("alternatives", [{}])
                            if alts and alts[0].get("transcript"):
                                transcript = alts[0]["transcript"]
                                is_final = data.get("is_final", False)
                                speech_final = data.get("speech_final", False)
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": transcript,
                                    "is_final": is_final,
                                    "speech_final": speech_final,
                                })
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            except Exception as e:
                logger.warning(f"[STT] Transcript forward error: {e}")

        await asyncio.gather(forward_audio(), forward_transcripts(), return_exceptions=True)

    except Exception as e:
        logger.error(f"[STT] Deepgram connection failed: {e}")
        try:
            await websocket.send_json({"type": "error", "message": f"STT connection failed: {e}"})
        except Exception:
            pass
    finally:
        if dg_ws and not dg_ws.closed:
            await dg_ws.close()
        await session.close()
        logger.info("[STT] Session closed")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for the brainstorming group chat."""
    global active_session

    await websocket.accept()
    logger.info("WebSocket client connected")

    # Parse agent selection from query params (e.g. ?agents=agent-architect,agent-builder)
    agents_param = websocket.query_params.get("agents", "")
    if agents_param:
        requested_ids = [a.strip() for a in agents_param.split(",") if a.strip()]
    else:
        requested_ids = enabled_agent_ids or list(agent_module.AGENT_REGISTRY.keys())

    # Resolve agent configs
    agent_configs = []
    for aid in requested_ids:
        if aid in agent_module.AGENT_REGISTRY:
            agent_configs.append(agent_module.AGENT_REGISTRY[aid])
        else:
            logger.warning(f"Unknown agent: {aid}")

    if not agent_configs:
        await websocket.send_json({"type": "error", "content": "No valid agents"})
        await websocket.close()
        return

    # Parse optional params from query string
    user_name = websocket.query_params.get("user", "")
    meeting_id = websocket.query_params.get("meeting_id", "")

    # Create or rejoin session
    session = ChatSession(
        agent_configs, user_name=user_name,
        enable_video=USE_VIDEO_CALL,
        meeting_id=meeting_id,
    )

    # ── LiveKit WebRTC room (if configured) ──
    import livekit_room as lk_room
    lk_manager = None
    lk_stt_active = False

    if lk_room.is_configured():
        async def on_livekit_transcript(transcript: str):
            """Called when user speech is transcribed via LiveKit → Deepgram."""
            nonlocal session
            # Send transcript to frontend for display
            await websocket.send_json({
                "type": "user_transcript",
                "content": transcript,
            })
            # Process as a regular user message
            await session.handle_message(transcript, websocket)
            # Auto-generate meeting title
            if not session._title_set and transcript:
                title = transcript[:80].strip()
                if len(transcript) > 80:
                    title += "..."
                convstore.update_session_title(session.session_id, title)
                session._title_set = True
            await websocket.send_json({"type": "round_complete"})

        lk_manager = lk_room.RoomManager(
            room_name=session.session_id,
            on_user_transcript=on_livekit_transcript,
        )
        lk_stt_active = await lk_manager.connect()
        if lk_stt_active:
            logger.info(f"[LiveKit] WebRTC room active for meeting {session.session_id}")

    # Send confirmation with agent list + meeting_id
    await websocket.send_json({
        "type": "session_start",
        "meeting_id": session.session_id,
        "livekit": {
            "enabled": lk_stt_active,
            "url": os.getenv("LIVEKIT_URL", "") if lk_stt_active else None,
            "room": session.session_id if lk_stt_active else None,
        },
        "agents": [
            {"id": cfg.identity, "variant": cfg.variant, "tagline": cfg.tagline}
            for cfg in agent_configs
        ],
    })

    # If rejoining, send past messages so frontend can display them
    if meeting_id:
        history_msgs = convstore.get_session_messages(meeting_id, limit=200)
        if history_msgs:
            await websocket.send_json({
                "type": "chat_history",
                "meeting_id": meeting_id,
                "messages": history_msgs,
            })

    # Prepare MuseTalk avatars in background
    asyncio.create_task(
        musetalk_prepare_agents([cfg.identity for cfg in agent_configs])
    )

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "chat":
                user_text = msg.get("content", "").strip()
                attachments = msg.get("attachments", [])

                # Build augmented message with file content for agents
                agent_text = user_text
                attachment_context = ""
                for att in attachments:
                    file_id = att.get("file_id", "")
                    file_meta = _uploaded_files.get(file_id, {})
                    fname = att.get("name", file_meta.get("original_name", "file"))
                    text_content = file_meta.get("text_content", "")

                    if text_content:
                        attachment_context += (
                            f"\n\n--- SHARED FILE: {fname} ---\n"
                            f"{text_content[:10000]}\n"
                            f"--- END FILE ---"
                        )
                    elif file_meta.get("is_image"):
                        attachment_context += f"\n\n[User shared an image: {fname}]"
                    else:
                        attachment_context += f"\n\n[User shared a file: {fname}]"

                if attachment_context:
                    agent_text = (user_text or "Please review the attached file(s).") + attachment_context

                if not agent_text:
                    continue

                # Acknowledge receipt (include attachments for frontend display)
                await websocket.send_json({
                    "type": "user_message",
                    "content": user_text,
                    "attachments": attachments,
                })

                # Run group chat — agents will respond
                await session.handle_message(agent_text, websocket)

                # Auto-generate meeting title from first user message
                if not session._title_set and user_text:
                    title = user_text[:80].strip()
                    if len(user_text) > 80:
                        title += "..."
                    convstore.update_session_title(session.session_id, title)
                    session._title_set = True

                # Store file interactions in memory for agents that reviewed them
                if attachments and hasattr(session, 'session_id'):
                    for att in attachments:
                        file_id = att.get("file_id", "")
                        file_meta = _uploaded_files.get(file_id, {})
                        if file_meta:
                            # File memory will be stored per-agent in handle_message's
                            # store_exchange calls — the augmented text includes file content
                            logger.info(f"[Chat] File '{file_meta.get('original_name')}' shared with agents")

                # Signal that the round of responses is complete
                await websocket.send_json({"type": "round_complete"})

            elif msg.get("type") == "reset":
                await session.reset()
                await websocket.send_json({"type": "session_reset"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up LiveKit room if active
        if lk_manager and lk_manager.connected:
            await lk_manager.disconnect()


def main():
    """Parse CLI args and start the FastAPI server."""
    global enabled_agent_ids

    import argparse

    parser = argparse.ArgumentParser(description="Meta-Brainstorming Backend")
    parser.add_argument(
        "--agents",
        type=str,
        default="",
        help="Comma-separated agent IDs (default: all)",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    if args.agents:
        enabled_agent_ids = [a.strip() for a in args.agents.split(",")]
    else:
        enabled_agent_ids = list(agent_module.AGENT_REGISTRY.keys())

    valid = [a for a in enabled_agent_ids if a in agent_module.AGENT_REGISTRY]
    if not valid:
        logger.error(
            f"No valid agents. Available: {', '.join(agent_module.AGENT_REGISTRY.keys())}"
        )
        sys.exit(1)

    enabled_agent_ids = valid
    logger.info(
        f"Starting server with {len(enabled_agent_ids)} agent(s): "
        f"{', '.join(enabled_agent_ids)}"
    )
    logger.info(f"Model: {OPENROUTER_MODEL}")

    # Load topic router for dual-layer memory (expertise-based routing)
    try:
        config_path = get_config_path()
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
        memstore.load_agent_topics(raw_config.get("agents", []))
    except Exception as e:
        logger.warning(f"Topic router init skipped: {e}")

    # Backfill existing SQLite conversations into ChromaDB vector store
    try:
        n = memstore.backfill_from_sqlite()
        if n > 0:
            logger.info(f"Backfilled {n} past exchanges into ChromaDB")
    except Exception as e:
        logger.warning(f"ChromaDB backfill skipped: {e}")

    # Auto-start MuseTalk service if video calls are enabled
    if USE_VIDEO_CALL:
        import musetalk_launcher
        logger.info("[Startup] USE_VIDEO_CALL=true — auto-starting MuseTalk service...")
        started = musetalk_launcher.start_service()
        if started:
            logger.info("[Startup] MuseTalk subprocess launched, will become healthy in background")
        else:
            logger.warning("[Startup] MuseTalk failed to start — video will be unavailable")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

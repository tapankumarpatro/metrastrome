"""
Meta-Brainstorming Backend — AutoGen Group Chat Server

FastAPI + WebSocket server that hosts an AutoGen SelectorGroupChat.
Each Tapan variant is an AssistantAgent; the human user sends messages
via WebSocket. Agent responses stream back in real-time.

Usage:
    python main.py                                    # all agents, port 8000
    python main.py --agents tapan-architect,tapan-builder  # specific variants
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

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick")
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
MUSETALK_URL = os.getenv("MUSETALK_URL", "http://localhost:8001")
MUSETALK_ENABLED = os.getenv("MUSETALK_ENABLED", "false").lower() == "true"

# Agent image paths (for MuseTalk avatar preparation) — derived from config
IMAGES_DIR = Path(__file__).parent.parent / "frontend" / "public" / "images"
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


SELECTOR_PROMPT = """You are managing a brainstorming group chat called "The Multiverse of Tapan".
Every participant is a variant of the same person (Tapan) who took a different life path.

{roles}

Current conversation:
{history}

Based on the conversation so far, select the agent from {participants} who would have
the most relevant and interesting perspective to contribute next. Prefer agents who
haven't spoken recently and whose expertise is most relevant to the current topic.
Only select one agent."""


async def generate_tts(text: str, voice: str = "en-US-AndrewMultilingualNeural") -> bytes:
    """Generate MP3 audio from text using Edge TTS."""
    communicate = edge_tts.Communicate(text, voice)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


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
    if not MUSETALK_ENABLED:
        return
    if not await musetalk_health():
        logger.warning("MuseTalk service not reachable, skipping avatar preparation")
        return
    for aid in agent_ids:
        await musetalk_prepare(aid)


class ChatSession:
    """Manages one brainstorming session.

    Key design decisions:
    - Each user message triggers a FRESH team run with limited responses.
    - max_messages = min(len(agents), 3) + 1  →  only 1-3 agents reply per turn.
    - Team is rebuilt (reset) after every round to prevent history pile-up.
    - A lightweight conversation_history list is maintained manually so
      agents have context of previous exchanges without AutoGen's internal
      state growing unbounded.
    - Conversations are persisted to SQLite via conversation_store.
    - Past conversation context is injected into agent system prompts so
      they "remember" previous sessions.
    """

    MAX_AGENT_REPLIES_PER_TURN = 2  # At most 2 agents speak per user message (fast turns)

    def __init__(self, agent_configs: list[AgentConfig], user_name: str = "", enable_video: bool = False):
        self.model_client = build_model_client()
        self.agent_configs = agent_configs
        self.conversation_history: list[dict] = []  # manual context window
        self.user_name = user_name
        self.enable_video = enable_video

        # Create a persistent session
        import uuid
        self.session_id = f"session-{uuid.uuid4().hex[:12]}"
        agent_ids = [cfg.identity for cfg in agent_configs]
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
            # Retrieve persistent notes for this agent from ChromaDB
            notes_ctx = memstore.build_agent_notes_context(cfg.identity)

            # Retrieve recent relevant memories from ChromaDB vector store
            memory_ctx = memstore.build_memory_context(
                query=f"conversations with {self.user_name or 'user'}",
                agent_id=cfg.identity,
                n_results=8,
            )

            memory_section = ""
            if notes_ctx or memory_ctx:
                parts = [p for p in [notes_ctx, memory_ctx] if p]
                memory_section = "\n\n" + "\n\n".join(parts)
                logger.info(f"Injected {len(memory_section)} chars of vector memory for {cfg.identity}")

            system_msg = (
                cfg.system_prompt
                + participant_clause
                + user_clause
                + (memory_preamble + memory_section if memory_section else "")
            )

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
        """Build (or rebuild) the team with a per-round message cap."""
        n_agents = len(self.agents)
        replies = min(n_agents, self.MAX_AGENT_REPLIES_PER_TURN)
        # +1 for the user message that kicks off the round
        termination = MaxMessageTermination(max_messages=replies + 1)

        if n_agents >= 2:
            self.team = SelectorGroupChat(
                self.agents,
                model_client=self.model_client,
                termination_condition=termination,
                selector_prompt=SELECTOR_PROMPT,
                allow_repeated_speaker=False,
                selector_func=self._keyword_selector,
            )
        else:
            self.team = RoundRobinGroupChat(
                self.agents,
                termination_condition=termination,
            )
        logger.info(
            f"Team built: {n_agents} agent(s), max {replies} replies per turn (fast selector)"
        )

    async def handle_message(self, user_message: str, websocket: WebSocket):
        """Process one user message: get agent replies, send text + audio."""
        import time as _time
        t0 = _time.time()
        logger.info(f"[handle_message] Processing: {user_message[:60]}...")

        # Store websocket ref so the selector can send typing events
        self._active_ws = websocket

        # Prepend recent conversation history to the user message so agents
        # have context, but the team itself starts fresh each round.
        context = self._build_context(user_message)

        # Rebuild team to reset internal state (prevents message accumulation)
        self._build_team()

        agent_replies = []
        try:
            stream = self.team.run_stream(task=context)
            async for event in stream:
                # TaskResult — skip
                if hasattr(event, "messages"):
                    continue

                source = getattr(event, "source", "unknown")
                content = getattr(event, "content", "")

                if not content or source == "user":
                    continue

                # Find the matching agent config
                agent_cfg = next(
                    (c for c in self.agent_configs if c.agent_name == source),
                    None,
                )

                agent_id = agent_cfg.identity if agent_cfg else source
                variant_name = agent_cfg.variant if agent_cfg else source

                # Send text message immediately — don't block on TTS
                await websocket.send_json({
                    "type": "agent_message",
                    "agent_id": agent_id,
                    "agent_name": source,
                    "variant": variant_name,
                    "content": content,
                })
                logger.debug(f"[{source}] {content[:80]}...")

                # Fire TTS + optional video as background task (non-blocking)
                voice = agent_cfg.voice if agent_cfg else "en-US-AndrewMultilingualNeural"
                asyncio.create_task(
                    _generate_and_send_audio(
                        websocket, content, voice, agent_id, variant_name,
                        enable_video=self.enable_video
                    )
                )

                elapsed = _time.time() - t0
                logger.info(f"[handle_message] Agent {variant_name} replied in {elapsed:.1f}s")
                agent_replies.append({"variant": variant_name, "content": content, "agent_id": agent_id})

        except Exception as e:
            logger.error(f"Error in group chat: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "content": str(e)})

        total = _time.time() - t0
        logger.info(f"[handle_message] Complete: {len(agent_replies)} replies in {total:.1f}s")

        # Update manual conversation history (keep last 10 exchanges)
        self.conversation_history.append({"role": "user", "text": user_message})
        for reply in agent_replies:
            self.conversation_history.append({
                "role": reply["variant"],
                "text": reply["content"],
            })
        # Trim to last 10 entries to prevent context bloat
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

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
        """Build a prompt that includes recent conversation history + vector-retrieved memories."""
        parts = []

        # Retrieve relevant memories from ChromaDB based on the current message
        memory_ctx = memstore.build_memory_context(
            query=user_message,
            n_results=3,
        )
        if memory_ctx:
            parts.append(memory_ctx)

        # Add recent in-session conversation history
        if self.conversation_history:
            history_lines = []
            for entry in self.conversation_history[-10:]:
                history_lines.append(f"{entry['role']}: {entry['text']}")
            history_str = "\n".join(history_lines)
            parts.append(f"[Previous conversation in this session]\n{history_str}")

        parts.append(f"[Latest message from the user]\n{user_message}")

        return "\n\n".join(parts)


async def _generate_and_send_audio(
    websocket: WebSocket,
    text: str,
    voice: str,
    agent_id: str,
    variant_name: str,
    enable_video: bool = False,
):
    """Background task: generate TTS audio and send it over WebSocket.
    Also triggers MuseTalk video if enable_video is True."""
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

            # Fire off MuseTalk video generation if user enabled video mode
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


# ── Global session (created on first WebSocket connect) ──────────────

active_session: Optional[ChatSession] = None
enabled_agent_ids: list[str] = []


@app.get("/health")
async def health():
    return {"status": "ok", "agents": enabled_agent_ids}


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
            "image": f"/images/{cfg.image}" if cfg.image else "",
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
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"OpenRouter error {resp.status}: {body}")
                        yield _sse_event("error", {"error": f"LLM API error: {resp.status}"})
                        return

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]

            # Strip markdown fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            agent_config = json.loads(content)

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
                    agent_config["image"] = f"/images/{filename}"
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

            # Remove image_prompt from the config (not needed in agents.config.json)
            agent_config.pop("image_prompt", None)

            # ── Step 3: Done ──
            yield _sse_event("progress", {
                "step": "complete",
                "message": "Agent is ready! Review and add to your team.",
            })
            yield _sse_event("result", {"agent": agent_config})

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}\nContent: {content}")
            yield _sse_event("error", {"error": "LLM returned invalid JSON, please try again"})
        except Exception as e:
            logger.error(f"Agent generation failed: {e}")
            yield _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    config["agents"].append(new_agent)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    reload_agents()
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
    logger.info(f"Removed agent: {agent_id}")
    return {"ok": True, "id": agent_id, "total_agents": len(agent_module.AGENT_REGISTRY)}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for the brainstorming group chat."""
    global active_session

    await websocket.accept()
    logger.info("WebSocket client connected")

    # Parse agent selection from query params (e.g. ?agents=tapan-architect,tapan-builder)
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
    video_requested = websocket.query_params.get("video", "0") == "1"

    # Create a fresh session for this connection (with persistent memory)
    session = ChatSession(agent_configs, user_name=user_name, enable_video=video_requested and MUSETALK_ENABLED)

    # Send confirmation with agent list
    await websocket.send_json({
        "type": "session_start",
        "agents": [
            {"id": cfg.identity, "variant": cfg.variant, "tagline": cfg.tagline}
            for cfg in agent_configs
        ],
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
                if not user_text:
                    continue

                # Acknowledge receipt
                await websocket.send_json({
                    "type": "user_message",
                    "content": user_text,
                })

                # Run group chat — agents will respond
                await session.handle_message(user_text, websocket)

                # Signal that the round of responses is complete
                await websocket.send_json({"type": "round_complete"})

            elif msg.get("type") == "reset":
                await session.reset()
                await websocket.send_json({"type": "session_reset"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


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

    # Backfill existing SQLite conversations into ChromaDB vector store
    try:
        n = memstore.backfill_from_sqlite()
        if n > 0:
            logger.info(f"Backfilled {n} past exchanges into ChromaDB")
    except Exception as e:
        logger.warning(f"ChromaDB backfill skipped: {e}")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

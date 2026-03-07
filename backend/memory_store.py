"""
Dual-layer vector memory using ChromaDB.

Two memory tiers:
  1. SHARED MEMORY (global "conversations" collection)
     - ALL raw conversations stored here — every user↔agent exchange
     - Every agent can search this for full conversation context

  2. PERSONAL MEMORY (per-agent "agent_{id}" collections)
     - Topic-routed: exchanges are analyzed and routed to agents whose
       EXPERTISE matches the conversation topic
     - E.g. design talk → The Artist's personal memory
            system architecture → The Architect's personal memory
     - The speaking agent ALWAYS gets the exchange in their personal memory
     - Other agents whose expertise matches ALSO get a copy

  3. PERSONAL NOTES (per-agent "notes_{id}" collections)
     - LLM-generated summaries about the user, per agent

This means an agent's system prompt gets:
  - Their personal role-specific memories (design convos for Artist, etc.)
  - Shared global context (full raw conversation history)
  - Their personal notes about the user
"""

import json
import math
import re
import time
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from loguru import logger

# ── ChromaDB client (persistent, local storage) ─────────────────────
CHROMA_DIR = Path(__file__).parent / "chroma_data"
CHROMA_DIR.mkdir(exist_ok=True)

_client: Optional[chromadb.ClientAPI] = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info(f"ChromaDB initialized at {CHROMA_DIR}")
    return _client


def _sanitize_collection_name(name: str) -> str:
    """ChromaDB collection names must be 3-63 chars, alphanumeric + underscores/hyphens."""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    clean = clean.strip("_-") or "default"
    return clean[:63]


def _get_agent_collection(agent_id: str):
    """Get or create this agent's PERSONAL (role-based) vector store."""
    client = _get_client()
    name = _sanitize_collection_name(f"agent_{agent_id}")
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def _get_agent_notes_collection(agent_id: str):
    """Get or create this agent's PERSONAL notes collection."""
    client = _get_client()
    name = _sanitize_collection_name(f"notes_{agent_id}")
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def _get_global_collection():
    """SHARED MEMORY: stores ALL raw conversations — every agent can access."""
    client = _get_client()
    return client.get_or_create_collection(
        name="conversations",
        metadata={"hnsw:space": "cosine"},
    )


# ── Topic Router: match exchange content to agent expertise ──────────

# Maps agent_id → set of lowercase keywords from their expertise + description
_agent_topic_map: dict[str, set[str]] = {}


def load_agent_topics(agents_config: list[dict]):
    """Load agent expertise keywords from agents.config.json data.
    Called once at startup from main.py after loading agent configs."""
    global _agent_topic_map
    _agent_topic_map.clear()

    for agent in agents_config:
        agent_id = agent.get("id", "")
        if not agent_id:
            continue

        keywords = set()
        # Add all expertise items (lowercased, split multi-word into individual words too)
        for exp in agent.get("expertise", []):
            keywords.add(exp.lower())
            for word in exp.lower().split():
                if len(word) > 3:  # skip tiny words like "and", "for"
                    keywords.add(word)

        # Add key terms from description
        desc = agent.get("description", "").lower()
        for word in desc.split():
            clean = re.sub(r"[^a-z0-9]", "", word)
            if len(clean) > 4:  # only meaningful words
                keywords.add(clean)

        # Add personality keywords
        personality = agent.get("personality", "").lower()
        for word in personality.split(","):
            clean = word.strip()
            if clean:
                keywords.add(clean)

        # Add technologies from projects
        for proj in agent.get("projects", []):
            for tech in proj.get("technologies", []):
                keywords.add(tech.lower())
                for word in tech.lower().split():
                    if len(word) > 3:
                        keywords.add(word)

        _agent_topic_map[agent_id] = keywords
        logger.debug(f"[TopicRouter] {agent_id}: {len(keywords)} keywords")

    logger.info(f"[TopicRouter] Loaded topic maps for {len(_agent_topic_map)} agents")


def _route_to_agents(text: str, speaking_agent_id: str = "") -> list[str]:
    """Determine which agents' personal memories should receive this exchange.
    Returns list of agent_ids. The speaking agent ALWAYS gets it.
    Other agents get it if ≥2 of their expertise keywords appear in the text."""
    if not _agent_topic_map:
        # Fallback: just the speaking agent
        return [speaking_agent_id] if speaking_agent_id else []

    text_lower = text.lower()
    routed = set()

    # Speaking agent always gets their own exchange
    if speaking_agent_id:
        routed.add(speaking_agent_id)

    # Score each agent by keyword matches
    for agent_id, keywords in _agent_topic_map.items():
        if agent_id == speaking_agent_id:
            continue  # already included

        match_count = 0
        for kw in keywords:
            if kw in text_lower:
                match_count += 1
                if match_count >= 2:  # threshold: at least 2 keyword matches
                    routed.add(agent_id)
                    break

    return list(routed)


# ── Store conversation exchanges ─────────────────────────────────────

def store_exchange(
    session_id: str,
    agent_id: str,
    agent_variant: str,
    user_message: str,
    agent_reply: str,
    user_name: str = "",
):
    """Store an exchange in:
    1. SHARED MEMORY (global) — always, raw content
    2. PERSONAL MEMORY — speaking agent + any agents whose expertise matches the topic
    """
    doc_text = f"User ({user_name or 'User'}): {user_message}\n{agent_variant}: {agent_reply}"
    ts = time.time()
    base_id = f"{session_id}_{agent_id}_{int(ts * 1000)}"

    metadata = {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_variant": agent_variant,
        "user_name": user_name,
        "timestamp": ts,
        "user_message": user_message[:500],
        "agent_reply": agent_reply[:500],
    }

    try:
        # 1. SHARED MEMORY — always store everything
        global_col = _get_global_collection()
        global_col.add(documents=[doc_text], metadatas=[metadata], ids=[f"g_{base_id}"])

        # 2. PERSONAL MEMORY — route by topic to relevant agents
        routed_agents = _route_to_agents(
            text=f"{user_message} {agent_reply}",
            speaking_agent_id=agent_id,
        )

        for target_id in routed_agents:
            agent_col = _get_agent_collection(target_id)
            personal_id = f"{base_id}_for_{target_id}" if target_id != agent_id else base_id
            agent_col.add(documents=[doc_text], metadatas=[metadata], ids=[personal_id])

        routed_str = ", ".join(routed_agents)
        logger.debug(f"[Memory] Stored in global + personal[{routed_str}] ({len(doc_text)} chars)")
    except Exception as e:
        logger.error(f"[Memory] Failed to store exchange for {agent_id}: {e}")


def store_group_round(
    session_id: str,
    user_message: str,
    agent_replies: list[dict],
    user_name: str = "",
):
    """Store all exchanges from a conversation round.
    Each goes to shared memory + topic-routed personal memories."""
    for reply in agent_replies:
        store_exchange(
            session_id=session_id,
            agent_id=reply.get("agent_id", ""),
            agent_variant=reply.get("variant", ""),
            user_message=user_message,
            agent_reply=reply.get("content", ""),
            user_name=user_name,
        )


def store_file_interaction(
    session_id: str,
    agent_id: str,
    agent_variant: str,
    filename: str,
    file_summary: str,
    user_message: str,
    agent_reply: str,
    user_name: str = "",
):
    """Store a file review interaction in both shared + personal memory.
    The file content summary is included so agents can recall what they reviewed.
    These get higher importance (0.8) so file reviews persist longer in memory."""
    doc_text = (
        f"[FILE SHARED: {filename}]\n"
        f"User ({user_name or 'User'}) shared a file for review: {filename}\n"
        f"File summary: {file_summary[:2000]}\n"
        f"User's request: {user_message}\n"
        f"{agent_variant}'s analysis: {agent_reply}"
    )
    ts = time.time()
    base_id = f"{session_id}_file_{agent_id}_{int(ts * 1000)}"

    metadata = {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_variant": agent_variant,
        "user_name": user_name,
        "timestamp": ts,
        "user_message": user_message[:500],
        "agent_reply": agent_reply[:500],
        "filename": filename,
        "importance": 0.8,  # file reviews are high-importance memories
        "type": "file_review",
    }

    try:
        # Shared memory
        global_col = _get_global_collection()
        global_col.add(documents=[doc_text], metadatas=[metadata], ids=[f"g_{base_id}"])

        # Personal memory — route to relevant agents
        routed_agents = _route_to_agents(
            text=f"{user_message} {file_summary} {agent_reply}",
            speaking_agent_id=agent_id,
        )
        for target_id in routed_agents:
            agent_col = _get_agent_collection(target_id)
            pid = f"{base_id}_for_{target_id}" if target_id != agent_id else base_id
            agent_col.add(documents=[doc_text], metadatas=[metadata], ids=[pid])

        logger.info(f"[Memory] Stored file interaction '{filename}' for {agent_variant} + {len(routed_agents)} routed agents")
    except Exception as e:
        logger.error(f"[Memory] Failed to store file interaction: {e}")


# ── Recency-weighted memory retrieval (mem0-inspired) ────────────────
#
# Instead of pure cosine-similarity ranking, we use a composite score:
#   score = (W_SIM * similarity) + (W_REC * recency_decay) + (W_IMP * importance)
# This gives recent memories higher priority while keeping old important
# ones accessible — like how humans remember.

W_SIM = 0.40   # semantic similarity weight
W_REC = 0.35   # recency decay weight
W_IMP = 0.25   # importance weight (currently uniform; can be LLM-scored later)
LAMBDA_DECAY = 0.05  # decay rate: exp(-λ * days).  ~50% at 14 days, ~18% at 30 days


def _recency_decay(timestamp: float) -> float:
    """Exponential decay based on age.  Returns 0.0–1.0 (1.0 = just stored)."""
    if not timestamp:
        return 0.0
    days_old = max(0, (time.time() - timestamp) / 86400)
    return math.exp(-LAMBDA_DECAY * days_old)


def _composite_score(distance: float, timestamp: float, importance: float = 0.5) -> float:
    """Compute mem0-style composite score.  Higher = better.
    distance: ChromaDB cosine distance (0 = identical, 2 = opposite).
    importance: 0.0–1.0 (default 0.5; can be set per-memory later)."""
    # Convert cosine distance → similarity (0–1 range)
    similarity = max(0.0, 1.0 - distance / 2.0)
    recency = _recency_decay(timestamp)
    return (W_SIM * similarity) + (W_REC * recency) + (W_IMP * importance)


def _query_collection(collection, query: str, n_results: int = 5) -> list[dict]:
    """Semantic query with recency-weighted re-ranking.
    Fetches 3× candidates from ChromaDB, re-scores with composite formula,
    then returns the top n_results."""
    count = collection.count()
    if count == 0:
        return []

    # Fetch more candidates to allow recency re-ranking to surface recent items
    fetch_n = min(count, n_results * 3)

    try:
        results = collection.query(
            query_texts=[query],
            n_results=fetch_n,
        )
    except Exception as e:
        logger.error(f"[Memory] Query failed: {e}")
        return []

    memories = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            ts = meta.get("timestamp", 0)
            importance = meta.get("importance", 0.5)
            score = _composite_score(dist, ts, importance)
            memories.append({
                "document": doc,
                "user_message": meta.get("user_message", ""),
                "agent_reply": meta.get("agent_reply", ""),
                "agent_variant": meta.get("agent_variant", ""),
                "agent_id": meta.get("agent_id", ""),
                "timestamp": ts,
                "distance": dist,
                "score": score,
            })

    # Sort by composite score (descending — higher is better)
    memories.sort(key=lambda m: m["score"], reverse=True)
    return memories[:n_results]


def retrieve_agent_memories(agent_id: str, query: str, n_results: int = 5) -> list[dict]:
    """Retrieve from this agent's PERSONAL (role-based) vector store."""
    col = _get_agent_collection(agent_id)
    return _query_collection(col, query, n_results)


def retrieve_global_memories(query: str, n_results: int = 5) -> list[dict]:
    """Retrieve from SHARED MEMORY (all raw conversations)."""
    col = _get_global_collection()
    return _query_collection(col, query, n_results)


def retrieve_memories(query: str, agent_id: str = "", n_results: int = 5, **kwargs) -> list[dict]:
    """Backward-compatible. agent_id → personal, else → global."""
    if agent_id:
        return retrieve_agent_memories(agent_id, query, n_results)
    return retrieve_global_memories(query, n_results)


# ── Format helpers ───────────────────────────────────────────────────

def _format_age(timestamp: float) -> str:
    """Format a timestamp as relative age string."""
    if not timestamp:
        return "unknown"
    age_hours = (time.time() - timestamp) / 3600
    if age_hours < 1:
        return f"{int(age_hours * 60)}m ago"
    elif age_hours < 24:
        return f"{int(age_hours)}h ago"
    return f"{int(age_hours / 24)}d ago"


def build_shared_memory_context(query: str, n_results: int = 5) -> str:
    """Build context from SHARED MEMORY (all raw conversations).
    This gives agents awareness of the full conversation history.
    Results are ranked by composite score (similarity + recency + importance)."""
    memories = retrieve_global_memories(query, n_results)
    if not memories:
        return ""

    lines = ["[SHARED CONVERSATION HISTORY — ranked by relevance × recency]"]
    for i, mem in enumerate(memories, 1):
        age = _format_age(mem['timestamp'])
        score = mem.get('score', 0)
        lines.append(f"\n--- Conversation {i} ({age}, relevance: {score:.0%}) ---")
        lines.append(mem["document"])
    return "\n".join(lines)


def build_agent_memory_context(agent_id: str, query: str, n_results: int = 5) -> str:
    """Build context from this agent's PERSONAL (role-based) memory.
    Contains only exchanges relevant to this agent's expertise.
    Results are ranked by composite score (similarity + recency + importance)."""
    memories = retrieve_agent_memories(agent_id, query, n_results)
    if not memories:
        return ""

    lines = ["[YOUR ROLE-SPECIFIC MEMORIES — ranked by relevance × recency]"]
    for i, mem in enumerate(memories, 1):
        age = _format_age(mem['timestamp'])
        score = mem.get('score', 0)
        lines.append(f"\n--- Memory {i} ({age}, relevance: {score:.0%}) ---")
        lines.append(mem["document"])
    return "\n".join(lines)


def build_memory_context(query: str, agent_id: str = "", n_results: int = 5) -> str:
    """Backward-compatible. If agent_id → personal, else → global."""
    if agent_id:
        return build_agent_memory_context(agent_id, query, n_results)
    return build_shared_memory_context(query, n_results)


# ── Agent Notes (persistent per-agent summaries) ─────────────────────

def store_agent_note(agent_id: str, agent_variant: str, note: str):
    """Store a note in this agent's PERSONAL notes collection."""
    col = _get_agent_notes_collection(agent_id)
    doc_id = f"note_{int(time.time() * 1000)}"

    try:
        col.add(
            documents=[note],
            metadatas=[{
                "agent_id": agent_id,
                "agent_variant": agent_variant,
                "timestamp": time.time(),
            }],
            ids=[doc_id],
        )
        logger.info(f"[Memory] Stored note for {agent_variant}: {note[:80]}...")
    except Exception as e:
        logger.error(f"[Memory] Failed to store note for {agent_id}: {e}")


def get_agent_notes(agent_id: str, n_results: int = 10) -> list[str]:
    """Retrieve all notes from this agent's personal notes collection."""
    col = _get_agent_notes_collection(agent_id)

    if col.count() == 0:
        return []

    try:
        results = col.get(limit=n_results)
    except Exception as e:
        logger.error(f"[Memory] Failed to get notes for {agent_id}: {e}")
        return []

    return results["documents"] if results and results["documents"] else []


def build_agent_notes_context(agent_id: str) -> str:
    """Build formatted string of this agent's personal notes."""
    notes = get_agent_notes(agent_id)
    if not notes:
        return ""

    lines = ["[YOUR PERSISTENT NOTES ABOUT THIS USER]"]
    for note in notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


# ── Stats / debug ────────────────────────────────────────────────────

def get_agent_memory_stats(agent_id: str) -> dict:
    """Get memory stats for a specific agent."""
    mem_col = _get_agent_collection(agent_id)
    notes_col = _get_agent_notes_collection(agent_id)
    return {
        "agent_id": agent_id,
        "personal_exchanges": mem_col.count(),
        "notes": notes_col.count(),
        "topic_keywords": len(_agent_topic_map.get(agent_id, set())),
    }


def get_all_memory_stats() -> dict:
    """Get stats across all collections."""
    client = _get_client()
    collections = client.list_collections()
    global_col = _get_global_collection()
    return {
        "total_collections": len(collections),
        "shared_exchanges": global_col.count(),
        "collections": [c.name for c in collections],
        "topic_router_agents": len(_agent_topic_map),
    }


# ── Backfill existing SQLite data ────────────────────────────────────

def backfill_from_sqlite():
    """One-time migration: load existing SQLite messages into dual-layer ChromaDB.
    Each exchange goes to shared memory + topic-routed personal memories."""
    try:
        import conversation_store as cs
        conn = cs._get_conn()

        sessions = conn.execute(
            "SELECT id, user_name, agents FROM sessions ORDER BY created_at ASC"
        ).fetchall()

        total_stored = 0
        for session in sessions:
            session_id = session[0]
            user_name = session[1] or "User"

            messages = conn.execute(
                "SELECT role, variant, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()

            current_user_msg = None
            for msg in messages:
                role, variant, content, ts = msg[0], msg[1], msg[2], msg[3]
                if role == "user":
                    current_user_msg = content
                elif current_user_msg:
                    store_exchange(
                        session_id=session_id,
                        agent_id=role,
                        agent_variant=variant or role,
                        user_message=current_user_msg,
                        agent_reply=content,
                        user_name=user_name,
                    )
                    total_stored += 1

        logger.info(f"[Memory] Backfilled {total_stored} exchanges into dual-layer ChromaDB")
        return total_stored
    except Exception as e:
        logger.error(f"[Memory] Backfill failed: {e}")
        return 0

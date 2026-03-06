"""
Per-agent vector memory using ChromaDB.

Each agent gets its OWN ChromaDB collection — true per-agent RAG.
When an agent is about to speak, we retrieve semantically relevant
past conversations from THAT agent's personal memory store.

Architecture:
  - Collection per agent: "agent_{agent_id}" (e.g. "agent_tapan-strategist")
  - Collection for notes: "notes_{agent_id}"
  - Global collection: "conversations" (cross-agent search)

Each document = one user↔agent exchange, embedded for cosine similarity.
"""

import json
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
    import re
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # Must start/end with alphanumeric
    clean = clean.strip("_-") or "default"
    return clean[:63]


def _get_agent_collection(agent_id: str):
    """Get or create this agent's PERSONAL vector store."""
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
    """Global collection for cross-agent search (e.g. _build_context)."""
    client = _get_client()
    return client.get_or_create_collection(
        name="conversations",
        metadata={"hnsw:space": "cosine"},
    )


# ── Store conversation exchanges ─────────────────────────────────────

def store_exchange(
    session_id: str,
    agent_id: str,
    agent_variant: str,
    user_message: str,
    agent_reply: str,
    user_name: str = "",
):
    """Store a user↔agent exchange in BOTH the agent's personal collection
    AND the global collection."""
    doc_text = f"User ({user_name or 'User'}): {user_message}\n{agent_variant}: {agent_reply}"
    ts = time.time()
    doc_id = f"{session_id}_{agent_id}_{int(ts * 1000)}"

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
        # Store in agent's personal collection
        agent_col = _get_agent_collection(agent_id)
        agent_col.add(documents=[doc_text], metadatas=[metadata], ids=[doc_id])

        # Also store in global collection for cross-agent retrieval
        global_col = _get_global_collection()
        global_col.add(documents=[doc_text], metadatas=[metadata], ids=[f"g_{doc_id}"])

        logger.debug(f"[Memory] Stored exchange in agent_{agent_id} + global ({len(doc_text)} chars)")
    except Exception as e:
        logger.error(f"[Memory] Failed to store exchange for {agent_id}: {e}")


def store_group_round(
    session_id: str,
    user_message: str,
    agent_replies: list[dict],
    user_name: str = "",
):
    """Store all exchanges from a conversation round — each goes to the
    respective agent's personal collection + global."""
    for reply in agent_replies:
        store_exchange(
            session_id=session_id,
            agent_id=reply.get("agent_id", ""),
            agent_variant=reply.get("variant", ""),
            user_message=user_message,
            agent_reply=reply.get("content", ""),
            user_name=user_name,
        )


# ── Retrieve from an agent's personal memory ─────────────────────────

def _query_collection(collection, query: str, n_results: int = 5) -> list[dict]:
    """Run a semantic query against any ChromaDB collection."""
    if collection.count() == 0:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
        )
    except Exception as e:
        logger.error(f"[Memory] Query failed: {e}")
        return []

    memories = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            memories.append({
                "document": doc,
                "user_message": meta.get("user_message", ""),
                "agent_reply": meta.get("agent_reply", ""),
                "agent_variant": meta.get("agent_variant", ""),
                "agent_id": meta.get("agent_id", ""),
                "timestamp": meta.get("timestamp", 0),
                "distance": dist,
            })
    return memories


def retrieve_agent_memories(agent_id: str, query: str, n_results: int = 5) -> list[dict]:
    """Retrieve from this agent's PERSONAL vector store."""
    col = _get_agent_collection(agent_id)
    return _query_collection(col, query, n_results)


def retrieve_global_memories(query: str, n_results: int = 5) -> list[dict]:
    """Retrieve from the GLOBAL collection (all agents)."""
    col = _get_global_collection()
    return _query_collection(col, query, n_results)


def retrieve_memories(query: str, agent_id: str = "", n_results: int = 5, **kwargs) -> list[dict]:
    """Backward-compatible retrieval. Uses agent's personal store if agent_id provided,
    otherwise falls back to global."""
    if agent_id:
        return retrieve_agent_memories(agent_id, query, n_results)
    return retrieve_global_memories(query, n_results)


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


def build_memory_context(query: str, agent_id: str = "", n_results: int = 5) -> str:
    """Build formatted context from an agent's personal memories.
    If agent_id is provided, searches that agent's personal collection.
    Otherwise searches the global collection."""
    memories = retrieve_memories(query=query, agent_id=agent_id, n_results=n_results)

    if not memories:
        return ""

    lines = [f"[RELEVANT MEMORIES FROM YOUR PAST CONVERSATIONS]"]
    for i, mem in enumerate(memories, 1):
        lines.append(f"\n--- Memory {i} ({_format_age(mem['timestamp'])}) ---")
        lines.append(mem["document"])

    return "\n".join(lines)


def build_agent_memory_context(agent_id: str, query: str, n_results: int = 5) -> str:
    """Build RAG context specifically from this agent's personal vector store.
    This is the primary function for per-agent RAG injection."""
    memories = retrieve_agent_memories(agent_id, query, n_results)

    if not memories:
        return ""

    lines = [f"[YOUR PERSONAL MEMORIES (from your past conversations)]"]
    for i, mem in enumerate(memories, 1):
        lines.append(f"\n--- Memory {i} ({_format_age(mem['timestamp'])}) ---")
        lines.append(mem["document"])

    return "\n".join(lines)


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
        "exchanges": mem_col.count(),
        "notes": notes_col.count(),
    }


def get_all_memory_stats() -> dict:
    """Get stats across all collections."""
    client = _get_client()
    collections = client.list_collections()
    global_col = _get_global_collection()
    return {
        "total_collections": len(collections),
        "global_exchanges": global_col.count(),
        "collections": [c.name for c in collections],
    }


# ── Backfill existing SQLite data into per-agent ChromaDB ────────────

def backfill_from_sqlite():
    """One-time migration: load existing SQLite messages into per-agent ChromaDB."""
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

        logger.info(f"[Memory] Backfilled {total_stored} exchanges into per-agent ChromaDB")
        return total_stored
    except Exception as e:
        logger.error(f"[Memory] Backfill failed: {e}")
        return 0

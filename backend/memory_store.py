"""
Vector-based conversation memory using ChromaDB.

Stores conversation exchanges as embeddings for semantic retrieval.
Each exchange (user message + agent reply) is stored as a single document.
Retrieval finds the most relevant past exchanges given a new query.

Also manages agent-level summaries (notes) that persist across sessions.
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


def _get_collection(name: str = "conversations"):
    """Get or create a ChromaDB collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def _get_notes_collection():
    """Collection for agent-level persistent notes/summaries."""
    client = _get_client()
    return client.get_or_create_collection(
        name="agent_notes",
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
    """Store a single user→agent exchange as an embeddable document.
    The document text is the combined exchange for semantic matching."""
    collection = _get_collection()

    # Build a searchable document from the exchange
    doc_text = f"User ({user_name or 'User'}): {user_message}\n{agent_variant}: {agent_reply}"
    doc_id = f"{session_id}_{agent_id}_{int(time.time() * 1000)}"

    metadata = {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_variant": agent_variant,
        "user_name": user_name,
        "timestamp": time.time(),
        "user_message": user_message[:500],  # truncate for metadata
        "agent_reply": agent_reply[:500],
    }

    try:
        collection.add(
            documents=[doc_text],
            metadatas=[metadata],
            ids=[doc_id],
        )
        logger.debug(f"[Memory] Stored exchange: {agent_variant} ({len(doc_text)} chars)")
    except Exception as e:
        logger.error(f"[Memory] Failed to store exchange: {e}")


def store_group_round(
    session_id: str,
    user_message: str,
    agent_replies: list[dict],
    user_name: str = "",
):
    """Store all exchanges from a single conversation round.
    Each agent reply becomes a separate document for targeted retrieval."""
    for reply in agent_replies:
        store_exchange(
            session_id=session_id,
            agent_id=reply.get("agent_id", ""),
            agent_variant=reply.get("variant", ""),
            user_message=user_message,
            agent_reply=reply.get("content", ""),
            user_name=user_name,
        )


# ── Retrieve relevant memories ───────────────────────────────────────

def retrieve_memories(
    query: str,
    agent_id: str = "",
    n_results: int = 5,
    max_age_hours: float = 0,
) -> list[dict]:
    """Retrieve the most relevant past exchanges for a given query.
    
    Args:
        query: The current user message or topic to match against.
        agent_id: If provided, only retrieve memories involving this agent.
        n_results: Max number of results to return.
        max_age_hours: If > 0, only retrieve memories newer than this.
    
    Returns:
        List of dicts with keys: document, user_message, agent_reply, 
        agent_variant, timestamp, distance.
    """
    collection = _get_collection()

    # Check if collection has any documents
    if collection.count() == 0:
        return []

    # Build where clause for filtering
    where = None
    where_clauses = []
    if agent_id:
        where_clauses.append({"agent_id": agent_id})
    if max_age_hours > 0:
        cutoff = time.time() - (max_age_hours * 3600)
        where_clauses.append({"timestamp": {"$gte": cutoff}})
    
    if len(where_clauses) == 1:
        where = where_clauses[0]
    elif len(where_clauses) > 1:
        where = {"$and": where_clauses}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            where=where if where else None,
        )
    except Exception as e:
        logger.error(f"[Memory] Retrieval failed: {e}")
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


def build_memory_context(
    query: str,
    agent_id: str = "",
    n_results: int = 5,
) -> str:
    """Build a formatted context string from retrieved memories.
    Ready to inject into an agent's system prompt or conversation context."""
    memories = retrieve_memories(query=query, agent_id=agent_id, n_results=n_results)
    
    if not memories:
        return ""

    lines = ["[RELEVANT MEMORIES FROM PAST CONVERSATIONS]"]
    for i, mem in enumerate(memories, 1):
        # Format timestamp as relative time
        age_hours = (time.time() - mem["timestamp"]) / 3600 if mem["timestamp"] else 0
        if age_hours < 1:
            age_str = f"{int(age_hours * 60)}m ago"
        elif age_hours < 24:
            age_str = f"{int(age_hours)}h ago"
        else:
            age_str = f"{int(age_hours / 24)}d ago"

        lines.append(f"\n--- Memory {i} ({age_str}) ---")
        lines.append(mem["document"])

    return "\n".join(lines)


# ── Agent Notes (persistent summaries) ───────────────────────────────

def store_agent_note(agent_id: str, agent_variant: str, note: str):
    """Store a persistent note/summary for an agent about the user."""
    collection = _get_notes_collection()
    doc_id = f"note_{agent_id}_{int(time.time() * 1000)}"

    try:
        collection.add(
            documents=[note],
            metadatas=[{
                "agent_id": agent_id,
                "agent_variant": agent_variant,
                "timestamp": time.time(),
                "type": "agent_note",
            }],
            ids=[doc_id],
        )
        logger.info(f"[Memory] Stored note for {agent_variant}: {note[:80]}...")
    except Exception as e:
        logger.error(f"[Memory] Failed to store note: {e}")


def get_agent_notes(agent_id: str, n_results: int = 5) -> list[str]:
    """Retrieve persistent notes for an agent."""
    collection = _get_notes_collection()
    
    if collection.count() == 0:
        return []

    try:
        results = collection.get(
            where={"agent_id": agent_id},
            limit=n_results,
        )
    except Exception as e:
        logger.error(f"[Memory] Failed to get notes: {e}")
        return []

    if results and results["documents"]:
        return results["documents"]
    return []


def build_agent_notes_context(agent_id: str) -> str:
    """Build a formatted string of agent notes for prompt injection."""
    notes = get_agent_notes(agent_id)
    if not notes:
        return ""
    
    lines = ["[YOUR PERSISTENT NOTES ABOUT THIS USER]"]
    for note in notes:
        lines.append(f"- {note}")
    return "\n".join(lines)


# ── Backfill existing SQLite data into ChromaDB ─────────────────────

def backfill_from_sqlite():
    """One-time migration: load existing SQLite messages into ChromaDB."""
    try:
        import conversation_store as cs
        conn = cs._get_conn()
        
        # Get all sessions
        sessions = conn.execute(
            "SELECT id, user_name, agents FROM sessions ORDER BY created_at ASC"
        ).fetchall()
        
        total_stored = 0
        for session in sessions:
            session_id = session[0]
            user_name = session[1] or "User"
            
            # Get messages for this session
            messages = conn.execute(
                "SELECT role, variant, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
            
            # Pair user messages with agent replies
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
        
        logger.info(f"[Memory] Backfilled {total_stored} exchanges from SQLite to ChromaDB")
        return total_stored
    except Exception as e:
        logger.error(f"[Memory] Backfill failed: {e}")
        return 0

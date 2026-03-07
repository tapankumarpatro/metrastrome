"""
The Multiverse — Agent Definitions (AutoGen Edition)

Loads agent config from agents.config.json in the project root.
Users can edit that JSON to add/modify agents without touching code.

Used by AutoGen SelectorGroupChat — the `description` field drives
speaker selection, `system_prompt` is assembled from structured data.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from loguru import logger


# ── Shared prompt fragments ──────────────────────────────────────────
def _common_identity(owner: str = "You") -> str:
    return (
        f"You are {owner} — one specific version of {owner} from a multiverse of "
        "possibilities. In every universe you share the same core: deeply curious, "
        "relentlessly driven, slightly irreverent, and genuinely passionate about "
        "what you do. But each version of you diverged at a crossroads and became "
        "something different.\n\n"
    )

def _common_chat_rules(owner: str = "You") -> str:
    return (
        "\n\nRULES FOR THIS CONVERSATION: "
        f"You are on a live voice call with a human user and possibly other {owner} "
        "variants. Respond like you're talking, not writing. Keep replies SHORT — "
        "1-3 sentences max. Be warm, natural, conversational. Use contractions. "
        "Respond ONLY to what the user just said. Do NOT ask multiple questions "
        f"at once — ask one thing, then wait. Do NOT reference any {owner} variant "
        "who is not listed in the PARTICIPANTS section. Do NOT use bullet points "
        "or numbered lists. Do NOT repeat yourself or paraphrase what you just said. "
        "When relevant, reference your specific PROJECTS and WORK HISTORY — share "
        "concrete examples, metrics, and lessons from your past work. This makes "
        "your advice grounded and real, not generic."
    )


@dataclass
class AgentConfig:
    """Configuration for an agent variant used by AutoGen."""

    agent_name: str        # AutoGen agent name (e.g. "TheVisionary")
    identity: str          # slug id (e.g. "tapan-visionary")
    variant: str           # display name (e.g. "The Visionary")
    description: str       # used by SelectorGroupChat for speaker selection
    system_prompt: str     # full system prompt (auto-generated from JSON)
    tagline: str = ""
    voice: str = "en-US-AndrewMultilingualNeural"  # edge-tts voice name
    emoji: str = ""
    color: str = "zinc"
    personality: str = ""
    backstory: str = ""
    image: str = ""        # filename in frontend/public/images/
    expertise: List[str] = field(default_factory=list)
    projects: List[dict] = field(default_factory=list)


def _build_system_prompt(agent_data: dict, owner_name: str = "") -> str:
    """Build a full system prompt from structured JSON data."""
    variant = agent_data["variant"]
    backstory = agent_data.get("backstory", "")
    expertise = agent_data.get("expertise", [])
    projects = agent_data.get("projects", [])
    owner = owner_name or "You"

    # Identity section
    prompt = _common_identity(owner)
    prompt += f"In this universe, you are {owner} {variant}. {backstory} "

    # Expertise
    if expertise:
        prompt += f"\nYou have deep expertise in {', '.join(expertise)}."

    # Projects
    if projects:
        prompt += "\n\nYOUR PROJECTS & WORK HISTORY:\n"
        for i, p in enumerate(projects, 1):
            name = p.get("name", "Unnamed Project")
            role = p.get("role", "")
            period = p.get("period", "")
            desc = p.get("description", "")
            outcome = p.get("outcome", "")
            lesson = p.get("lesson", "")

            prompt += f"{i}. {name}"
            if role:
                prompt += f" ({role}"
                if period:
                    prompt += f", {period}"
                prompt += ")"
            prompt += f": {desc}"
            if outcome:
                prompt += f" Outcome: {outcome}."
            if lesson:
                prompt += f" Lesson: {lesson}"
            prompt += "\n"

    prompt += _common_chat_rules(owner)
    return prompt


def _load_config_json() -> dict:
    """Find and load agents.config.json from known locations."""
    candidates = [
        Path(__file__).parent.parent.parent / "agents.config.json",  # project root
        Path(__file__).parent.parent / "agents.config.json",          # backend dir
        Path.cwd() / "agents.config.json",                            # cwd
    ]
    for path in candidates:
        if path.exists():
            logger.info(f"Loading agent config from {path}")
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    logger.warning("agents.config.json not found, using empty config")
    return {"agents": []}


def _sanitize_agent_name(raw: str) -> str:
    """Convert any string into a valid Python identifier for AutoGen.
    E.g. 'Elon Musk' -> 'ElonMusk', 'tapan-visionary' -> 'TapanVisionary'."""
    # Remove everything except alphanumeric and spaces/hyphens/underscores
    cleaned = re.sub(r"[^a-zA-Z0-9 _\-]", "", raw)
    # Split on non-alpha separators and title-case each part
    parts = re.split(r"[\s\-_]+", cleaned)
    name = "".join(p.capitalize() for p in parts if p)
    # Ensure it doesn't start with a digit
    if name and name[0].isdigit():
        name = "Agent" + name
    return name or "UnnamedAgent"


def load_agents_from_json() -> Dict[str, AgentConfig]:
    """Load all agents from agents.config.json and return a registry dict."""
    config = _load_config_json()
    registry: Dict[str, AgentConfig] = {}

    for agent_data in config.get("agents", []):
        agent_id = agent_data.get("id", "")
        if not agent_id:
            logger.warning(f"Skipping agent with no id: {agent_data}")
            continue

        system_prompt = agent_data.get("system_prompt_override") or _build_system_prompt(agent_data)

        cfg = AgentConfig(
            agent_name=_sanitize_agent_name(agent_data.get("agent_name", agent_id)),
            identity=agent_id,
            variant=agent_data.get("variant", agent_id),
            description=agent_data.get("description", ""),
            system_prompt=system_prompt,
            tagline=agent_data.get("tagline", ""),
            voice=agent_data.get("voice", "en-US-AndrewMultilingualNeural"),
            emoji=agent_data.get("emoji", "🤖"),
            color=agent_data.get("color", "zinc"),
            personality=agent_data.get("personality", ""),
            backstory=agent_data.get("backstory", ""),
            image=agent_data.get("image", ""),
            expertise=agent_data.get("expertise", []),
            projects=agent_data.get("projects", []),
        )
        registry[agent_id] = cfg
        logger.debug(f"Loaded agent: {agent_id} ({cfg.variant})")

    logger.info(f"Loaded {len(registry)} agents from config")
    return registry


# Load on import
AGENT_REGISTRY = load_agents_from_json()
DEFAULT_AGENT = next(iter(AGENT_REGISTRY.values()), None)


def reload_agents() -> Dict[str, AgentConfig]:
    """Reload agents from agents.config.json (call after add/remove)."""
    global AGENT_REGISTRY, DEFAULT_AGENT
    AGENT_REGISTRY = load_agents_from_json()
    DEFAULT_AGENT = next(iter(AGENT_REGISTRY.values()), None)
    return AGENT_REGISTRY


def rebuild_prompt_for_owner(cfg: AgentConfig, owner_name: str) -> str:
    """Rebuild a system prompt personalized with the owner's name.
    Re-generates from the AgentConfig fields (variant, backstory, expertise, projects).
    Falls back to the existing system_prompt if it was a custom override."""
    agent_data = {
        "variant": cfg.variant,
        "backstory": cfg.backstory,
        "expertise": cfg.expertise,
        "projects": cfg.projects,
    }
    return _build_system_prompt(agent_data, owner_name=owner_name)


def get_config_path() -> Path:
    """Return the path to agents.config.json."""
    candidates = [
        Path(__file__).parent.parent.parent / "agents.config.json",
        Path(__file__).parent.parent / "agents.config.json",
        Path.cwd() / "agents.config.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]

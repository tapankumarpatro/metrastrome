"""
User Perception Module — Raven-inspired emotion detection.

Analyzes webcam frames to detect user emotional state.
Uses a vision-capable LLM to classify facial expressions.

The detected emotion is injected into agent system prompts so
they can adapt their responses (e.g., simplify when user looks confused).

Requires: OPENROUTER_API_KEY (uses a vision model for analysis).
Configure via: PERCEPTION_MODEL env var (default: google/gemini-flash-1.5).
"""

import os
import json
import time
import aiohttp
from loguru import logger

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PERCEPTION_MODEL = os.getenv("PERCEPTION_MODEL", "google/gemini-flash-1.5")

# Cache to avoid spamming the API
_last_emotion = "neutral"
_last_analysis_time = 0.0
_MIN_INTERVAL = 5.0  # Minimum seconds between analyses


ANALYSIS_PROMPT = """Analyze this person's facial expression in the webcam image.
Classify their emotional state as ONE of: happy, neutral, confused, bored, excited, frustrated, thoughtful, surprised.
Also rate their engagement level: high, medium, low.

Respond with ONLY a JSON object, no other text:
{"emotion": "...", "engagement": "...", "brief": "one sentence description"}"""


async def analyze_frame(base64_image: str) -> dict:
    """Analyze a webcam frame for emotional state.

    Args:
        base64_image: Base64-encoded JPEG image (without data URI prefix)

    Returns:
        {"emotion": str, "engagement": str, "brief": str}
    """
    global _last_emotion, _last_analysis_time

    now = time.time()
    if now - _last_analysis_time < _MIN_INTERVAL:
        return {"emotion": _last_emotion, "engagement": "medium", "brief": "cached", "cached": True}

    if not OPENROUTER_API_KEY:
        return {"emotion": "neutral", "engagement": "medium", "brief": "API key not configured"}

    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        # Ensure proper data URI format
        if not base64_image.startswith("data:"):
            base64_image = f"data:image/jpeg;base64,{base64_image}"

        payload = {
            "model": PERCEPTION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ANALYSIS_PROMPT},
                        {"type": "image_url", "image_url": {"url": base64_image}},
                    ],
                }
            ],
            "max_tokens": 100,
            "temperature": 0.1,
        }

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[Perception] API error {resp.status}: {body[:100]}")
                    return {"emotion": _last_emotion, "engagement": "medium", "brief": "API error"}

                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Parse JSON from response
                if content.startswith("{"):
                    result = json.loads(content)
                else:
                    # Try to extract JSON from markdown code block
                    import re
                    match = re.search(r'\{[^}]+\}', content)
                    if match:
                        result = json.loads(match.group())
                    else:
                        result = {"emotion": "neutral", "engagement": "medium", "brief": content[:50]}

                _last_emotion = result.get("emotion", "neutral")
                _last_analysis_time = now
                logger.info(f"[Perception] Detected: {result.get('emotion')} ({result.get('engagement')} engagement)")
                return result

    except Exception as e:
        logger.warning(f"[Perception] Analysis failed: {e}")
        return {"emotion": _last_emotion, "engagement": "medium", "brief": str(e)[:50]}


def get_emotion_context() -> str:
    """Get a prompt fragment describing the user's current emotional state.
    Injected into agent system prompts for adaptive responses."""
    if _last_emotion == "neutral":
        return ""

    emotion_guidance = {
        "confused": "The user appears confused. Simplify your explanation, ask if they need clarification, and avoid jargon.",
        "bored": "The user seems disengaged. Make your response more energetic, ask an engaging question, or change the topic.",
        "frustrated": "The user looks frustrated. Be extra patient, acknowledge their feelings, and offer clear actionable steps.",
        "happy": "The user appears happy and engaged. Match their positive energy.",
        "excited": "The user seems excited about this topic. Feed their enthusiasm with interesting details.",
        "thoughtful": "The user appears to be thinking deeply. Give them a moment, then offer a thought-provoking follow-up.",
        "surprised": "The user looks surprised. Explain the context to help them process the information.",
    }

    guidance = emotion_guidance.get(_last_emotion, "")
    if guidance:
        return f"\n\n[USER EMOTIONAL STATE: {_last_emotion}] {guidance}"
    return ""

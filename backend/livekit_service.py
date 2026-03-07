"""
LiveKit WebRTC Integration — Optional real-time A/V transport layer.

Replaces WebSocket-based audio with LiveKit rooms for:
  - Sub-100ms audio transport (vs ~200-400ms for base64 WS blobs)
  - Bidirectional video (enables user perception/emotion detection)
  - Native echo cancellation, noise suppression
  - SFU architecture (scales to many participants)

Setup:
  1. Install: pip install livekit-api
  2. Run LiveKit server: https://docs.livekit.io/home/self-hosting/local/
  3. Configure .env:
     LIVEKIT_URL=ws://localhost:7880
     LIVEKIT_API_KEY=devkey
     LIVEKIT_API_SECRET=secret

When LIVEKIT_URL is set, the /livekit/token endpoint becomes available.
The frontend can then connect to LiveKit rooms for real-time A/V alongside
the existing WebSocket for chat messages.
"""

import os
from loguru import logger

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


def is_livekit_configured() -> bool:
    """Check if LiveKit is configured."""
    return bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET)


def get_livekit_info() -> dict:
    """Return LiveKit status for /system/capabilities."""
    return {
        "enabled": is_livekit_configured(),
        "url": LIVEKIT_URL if is_livekit_configured() else None,
    }


def generate_token(room_name: str, participant_name: str, is_agent: bool = False) -> str | None:
    """Generate a LiveKit access token for a participant.

    Returns JWT string or None if LiveKit is not configured.
    Requires: pip install livekit-api
    """
    if not is_livekit_configured():
        return None

    try:
        from livekit.api import AccessToken, VideoGrants

        token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity(participant_name)
        token.with_name(participant_name)

        grants = VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
        token.with_grants(grants)

        jwt = token.to_jwt()
        logger.info(f"[LiveKit] Generated token for {participant_name} in room {room_name}")
        return jwt

    except ImportError:
        logger.warning("[LiveKit] livekit-api not installed. Run: pip install livekit-api")
        return None
    except Exception as e:
        logger.error(f"[LiveKit] Token generation failed: {e}")
        return None

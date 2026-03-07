"""
Multi-TTS Provider Module — Tavus-inspired low-latency TTS

Supports:
  - edge     (default, free, ~300-500ms latency)
  - cartesia (ultra-fast ~100ms, $0.10/1K chars, requires CARTESIA_API_KEY)
  - elevenlabs (high quality ~300ms, $0.30/1K chars, requires ELEVENLABS_API_KEY)
  - deepgram (fast ~150ms, $0.015/1K chars, requires DEEPGRAM_API_KEY)

Configure via .env:
  TTS_PROVIDER=edge          # or cartesia, elevenlabs, deepgram
  CARTESIA_API_KEY=...       # required for cartesia
  ELEVENLABS_API_KEY=...     # required for elevenlabs
  DEEPGRAM_API_KEY=...       # required for deepgram
"""

import os
import aiohttp
import edge_tts
from loguru import logger

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge").lower()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# ── Voice mappings per provider ──────────────────────────────────────
# Maps edge-tts voice names to provider-specific voice IDs.
# Users can override per-agent via VOICE_MAP_<PROVIDER> env var (JSON).

CARTESIA_VOICE_MAP = {
    # Default Cartesia voices (English, conversational)
    "en-US-AndrewMultilingualNeural": "a0e99841-438c-4a64-b679-ae501e7d6091",  # Barbershop Man
    "en-US-BrianMultilingualNeural": "ee7ea9f8-c0c1-498c-9f43-e7a9571f512a",   # Classy British Man
    "en-US-RogerNeural": "b7d50908-b17c-442d-ad8d-7c56e74dd5da",              # California Girl (casual)
    "en-GB-ThomasNeural": "63ff761f-c1e8-414b-b969-d1833d1c870c",             # British Reading Lady
    "en-GB-RyanNeural": "ee7ea9f8-c0c1-498c-9f43-e7a9571f512a",              # Classy British Man
    "en-AU-WilliamMultilingualNeural": "41534e16-2966-4c6b-9670-111411def906", # Australian Man
    "_default": "a0e99841-438c-4a64-b679-ae501e7d6091",
}

ELEVENLABS_VOICE_MAP = {
    "en-US-AndrewMultilingualNeural": "pNInz6obpgDQGcFmaJgB",  # Adam
    "en-US-BrianMultilingualNeural": "yoZ06aMxZJJ28mfd3POQ",   # Sam
    "en-US-RogerNeural": "VR6AewLTigWG4xSOukaG",              # Arnold
    "en-GB-ThomasNeural": "pqHfZKP75CvOlQylNhV4",             # Bill
    "en-GB-RyanNeural": "TX3LPaxmHKxFdv7VOQHJ",              # Liam
    "en-AU-WilliamMultilingualNeural": "VR6AewLTigWG4xSOukaG", # Arnold
    "_default": "pNInz6obpgDQGcFmaJgB",
}

DEEPGRAM_VOICE_MAP = {
    "en-US-AndrewMultilingualNeural": "aura-orion-en",
    "en-US-BrianMultilingualNeural": "aura-arcas-en",
    "en-US-RogerNeural": "aura-angus-en",
    "en-GB-ThomasNeural": "aura-helios-en",
    "en-GB-RyanNeural": "aura-orpheus-en",
    "en-AU-WilliamMultilingualNeural": "aura-orion-en",
    "_default": "aura-orion-en",
}


def _map_voice(edge_voice: str, voice_map: dict) -> str:
    """Map an edge-tts voice name to a provider-specific voice ID."""
    return voice_map.get(edge_voice, voice_map.get("_default", ""))


# ── Provider implementations ─────────────────────────────────────────

async def _edge_tts(text: str, voice: str) -> bytes:
    """Generate TTS using Microsoft Edge TTS (free)."""
    communicate = edge_tts.Communicate(text, voice)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


async def _cartesia_tts(text: str, voice: str) -> bytes:
    """Generate TTS using Cartesia API (ultra-fast, ~100ms)."""
    if not CARTESIA_API_KEY:
        logger.warning("[TTS] Cartesia API key not set, falling back to Edge TTS")
        return await _edge_tts(text, voice)

    voice_id = _map_voice(voice, CARTESIA_VOICE_MAP)
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": "sonic-2",
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "mp3",
            "bit_rate": 128000,
            "sample_rate": 44100,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    audio = await resp.read()
                    logger.debug(f"[Cartesia] Generated {len(audio)/1024:.1f}KB for '{text[:30]}...'")
                    return audio
                else:
                    body = await resp.text()
                    logger.warning(f"[Cartesia] Error {resp.status}: {body[:200]}")
                    return await _edge_tts(text, voice)
    except Exception as e:
        logger.warning(f"[Cartesia] Failed, falling back to Edge: {e}")
        return await _edge_tts(text, voice)


async def _elevenlabs_tts(text: str, voice: str) -> bytes:
    """Generate TTS using ElevenLabs API (high quality)."""
    if not ELEVENLABS_API_KEY:
        logger.warning("[TTS] ElevenLabs API key not set, falling back to Edge TTS")
        return await _edge_tts(text, voice)

    voice_id = _map_voice(voice, ELEVENLABS_VOICE_MAP)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    audio = await resp.read()
                    logger.debug(f"[ElevenLabs] Generated {len(audio)/1024:.1f}KB for '{text[:30]}...'")
                    return audio
                else:
                    body = await resp.text()
                    logger.warning(f"[ElevenLabs] Error {resp.status}: {body[:200]}")
                    return await _edge_tts(text, voice)
    except Exception as e:
        logger.warning(f"[ElevenLabs] Failed, falling back to Edge: {e}")
        return await _edge_tts(text, voice)


async def _deepgram_tts(text: str, voice: str) -> bytes:
    """Generate TTS using Deepgram API (fast, cheap)."""
    if not DEEPGRAM_API_KEY:
        logger.warning("[TTS] Deepgram API key not set, falling back to Edge TTS")
        return await _edge_tts(text, voice)

    model = _map_voice(voice, DEEPGRAM_VOICE_MAP)
    url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mp3"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    audio = await resp.read()
                    logger.debug(f"[Deepgram TTS] Generated {len(audio)/1024:.1f}KB for '{text[:30]}...'")
                    return audio
                else:
                    body = await resp.text()
                    logger.warning(f"[Deepgram TTS] Error {resp.status}: {body[:200]}")
                    return await _edge_tts(text, voice)
    except Exception as e:
        logger.warning(f"[Deepgram TTS] Failed, falling back to Edge: {e}")
        return await _edge_tts(text, voice)


# ── Public API ────────────────────────────────────────────────────────

async def generate_tts(text: str, voice: str = "en-US-AndrewMultilingualNeural") -> bytes:
    """Generate TTS audio using the configured provider.
    Falls back to Edge TTS on any error."""
    if TTS_PROVIDER == "cartesia":
        return await _cartesia_tts(text, voice)
    elif TTS_PROVIDER == "elevenlabs":
        return await _elevenlabs_tts(text, voice)
    elif TTS_PROVIDER == "deepgram":
        return await _deepgram_tts(text, voice)
    else:
        return await _edge_tts(text, voice)


def get_tts_info() -> dict:
    """Return info about the active TTS provider for /system/capabilities."""
    return {
        "provider": TTS_PROVIDER,
        "has_api_key": bool(
            (TTS_PROVIDER == "cartesia" and CARTESIA_API_KEY) or
            (TTS_PROVIDER == "elevenlabs" and ELEVENLABS_API_KEY) or
            (TTS_PROVIDER == "deepgram" and DEEPGRAM_API_KEY) or
            TTS_PROVIDER == "edge"
        ),
    }

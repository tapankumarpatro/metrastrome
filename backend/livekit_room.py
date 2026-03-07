"""
LiveKit Room Manager — Server-side WebRTC participation.

When LiveKit is configured, the backend joins each meeting room as a
hidden participant ("metrastrome-server"). This enables:

  - Receiving user audio via WebRTC → forwarded to Deepgram STT
  - Receiving user video frames for emotion/perception analysis
  - WebRTC echo cancellation + noise suppression on user audio

Agent audio output stays on WebSocket (base64 MP3) for simplicity —
no ffmpeg/PCM conversion required.

Falls back gracefully when LiveKit is not configured.
"""

import asyncio
import json
import os
from typing import Callable, Optional, Awaitable

import aiohttp
from loguru import logger

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")


def is_configured() -> bool:
    """Check if LiveKit is configured."""
    return bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET)


class RoomManager:
    """Manages the backend's participation in a single LiveKit room.

    Joins as 'metrastrome-server', subscribes to user audio/video,
    and forwards audio to Deepgram for real-time STT.
    """

    def __init__(
        self,
        room_name: str,
        on_user_transcript: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.room_name = room_name
        self.on_user_transcript = on_user_transcript
        self._room = None
        self._connected = False
        self._stt_task: Optional[asyncio.Task] = None
        self._interim_text = ""

    async def connect(self) -> bool:
        """Join the LiveKit room as the server participant."""
        if not is_configured():
            logger.info("[LiveKit] Not configured, skipping room join")
            return False

        try:
            from livekit import rtc, api as lk_api

            # Generate token for server participant
            token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            token.with_identity("metrastrome-server")
            token.with_name("Metrastrome Server")
            token.with_grants(lk_api.VideoGrants(
                room_join=True,
                room=self.room_name,
                can_publish=False,      # Server doesn't publish A/V tracks
                can_subscribe=True,     # Server subscribes to user tracks
                can_publish_data=True,  # For sending metadata if needed
            ))
            jwt = token.to_jwt()

            # Connect to room
            self._room = rtc.Room()

            @self._room.on("track_subscribed")
            def on_track_subscribed(track, publication, participant):
                if participant.identity == "metrastrome-server":
                    return  # Ignore our own tracks
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    logger.info(f"[LiveKit] Subscribed to audio from {participant.identity}")
                    self._stt_task = asyncio.ensure_future(
                        self._handle_user_audio(track)
                    )
                elif track.kind == rtc.TrackKind.KIND_VIDEO:
                    logger.info(f"[LiveKit] Subscribed to video from {participant.identity}")
                    # Video frames can be used for perception/emotion detection
                    # TODO: integrate with perception.py

            @self._room.on("participant_disconnected")
            def on_participant_left(participant):
                logger.info(f"[LiveKit] Participant left: {participant.identity}")
                if self._stt_task and not self._stt_task.done():
                    self._stt_task.cancel()

            await asyncio.wait_for(
                self._room.connect(LIVEKIT_URL, jwt), timeout=5.0
            )
            self._connected = True
            logger.info(f"[LiveKit] Joined room: {self.room_name}")
            return True

        except ImportError:
            logger.warning("[LiveKit] livekit package not installed. Run: pip install livekit")
            return False
        except Exception as e:
            logger.error(f"[LiveKit] Failed to join room: {e}")
            return False

    async def _handle_user_audio(self, track):
        """Receive user audio from LiveKit and forward to Deepgram STT."""
        from livekit import rtc

        if not DEEPGRAM_API_KEY:
            logger.warning("[LiveKit] No DEEPGRAM_API_KEY — cannot do server STT via LiveKit")
            return

        deepgram_url = (
            "wss://api.deepgram.com/v1/listen"
            "?model=nova-2&language=en&smart_format=true"
            "&interim_results=true&endpointing=300&vad_events=true"
            "&encoding=linear16&sample_rate=48000&channels=1"
        )
        dg_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        session = None
        dg_ws = None
        try:
            session = aiohttp.ClientSession()
            dg_ws = await session.ws_connect(deepgram_url, headers=dg_headers)
            logger.info("[LiveKit] Connected to Deepgram for user audio STT")

            audio_stream = rtc.AudioStream(track)

            async def forward_audio():
                """LiveKit audio frames → Deepgram."""
                try:
                    async for frame_event in audio_stream:
                        frame = frame_event.frame
                        # LiveKit audio frames are already PCM — send directly
                        pcm_bytes = bytes(frame.data)
                        if dg_ws and not dg_ws.closed:
                            await dg_ws.send_bytes(pcm_bytes)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"[LiveKit] Audio forward error: {e}")
                finally:
                    if dg_ws and not dg_ws.closed:
                        try:
                            await dg_ws.send_str(json.dumps({"type": "CloseStream"}))
                        except Exception:
                            pass

            async def receive_transcripts():
                """Deepgram transcripts → process as user messages."""
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

                                    if speech_final and transcript.strip():
                                        # Complete utterance — process it
                                        final = (self._interim_text + " " + transcript).strip()
                                        self._interim_text = ""
                                        logger.info(f"[LiveKit STT] Final: {final}")
                                        if self.on_user_transcript:
                                            await self.on_user_transcript(final)
                                    elif is_final and transcript.strip():
                                        # Sentence-level final — accumulate
                                        self._interim_text = (
                                            self._interim_text + " " + transcript
                                        ).strip()
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"[LiveKit] Transcript receive error: {e}")

            await asyncio.gather(
                forward_audio(), receive_transcripts(), return_exceptions=True
            )

        except Exception as e:
            logger.error(f"[LiveKit] Deepgram STT via LiveKit failed: {e}")
        finally:
            if dg_ws and not dg_ws.closed:
                await dg_ws.close()
            if session:
                await session.close()
            logger.info("[LiveKit] STT session closed")

    @property
    def connected(self) -> bool:
        return self._connected

    async def disconnect(self):
        """Leave the room and clean up."""
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
        if self._room:
            await self._room.disconnect()
            self._connected = False
            logger.info(f"[LiveKit] Left room: {self.room_name}")

Tavus PALs vs Metrastrome — Gap Analysis
Architecture Comparison
Layer	Tavus PALs	Metrastrome (Current)	Gap
Transport	WebRTC via Daily.co (bidirectional video+audio, ultra-low latency)	WebSocket (text + base64 audio blobs)	🔴 Major
STT	Deepgram (server-side, real-time streaming)	Browser Web Speech API (client-side)	🟡 Medium
LLM	Custom models (tavus-gpt-4o, tavus-llama) + 30ms RAG	OpenRouter → Llama 4 Maverick + ChromaDB RAG	🟢 Comparable
TTS	Cartesia / ElevenLabs / PlayHT (ultra-low latency)	Edge TTS (free, ~300-500ms per sentence)	🟡 Medium
Video Rendering	Phoenix — real-time Gaussian-diffusion, micro-expressions, 30+ languages	MuseTalk — batch lip-sync, single image, ~15x slower on 3060	🔴 Major
Perception (User Vision)	Raven — reads facial expressions, body language, confusion detection	None	🔴 Missing
Turn-taking	Sparrow — ML transformer model, handles interruptions naturally	Keyword-based selector + MaxMessageTermination	🟡 Medium
Memory	Persistent memory across sessions	ChromaDB dual-layer + SQLite + agent notes	🟢 We're strong here
Frontend	React + WebGL green-screen compositing (transparent avatar overlay)	Next.js + CSS animations (no video compositing)	🟡 Medium
Latency	Sub-600ms round-trip (parallelized pipeline)	~2-5s per sentence chunk (sequential: LLM → TTS → send)	🔴 Major
What Tavus Does That We Don't (Yet)
1. 🔴 Parallelized Pipeline (Biggest Win)
Tavus's killer advantage — they don't wait for the full LLM response before starting TTS. They:

Start TTS on the first few tokens while LLM is still generating
Start video rendering while TTS is still synthesizing
Everything runs in parallel
Our current flow (_stream_text_and_audio in main.py:873):

LLM generates FULL response → split into sentences → TTS sentence 1 → send → TTS sentence 2 → send...
What Tavus does:

LLM token 1-10 → TTS starts on token 1-10 → Video renders → Send
LLM token 11-20 → TTS starts on token 11-20 → Video renders → Send  (all parallel)
Actionable: Switch to LLM streaming (OpenRouter supports it) and pipe tokens into TTS as sentences complete, instead of waiting for the full response from AutoGen.

2. 🔴 WebRTC Instead of WebSocket
WebSocket sends base64 audio blobs — adds encoding overhead + no real bidirectional A/V. WebRTC gives:

Direct audio/video streams (no base64 encoding)
~50-100ms transport vs ~200-400ms for our WS blobs
User camera feed back to server (enables perception)
Actionable: Integrate Daily.co or LiveKit (open-source WebRTC). Both have Python + React SDKs.

3. 🔴 User Perception (Raven equivalent)
Tavus reads the user's face — detects confusion, engagement, boredom. This lets the AI:

Pause and simplify if user looks confused
Speed up if user seems impatient
React to non-verbal cues
We have zero user video analysis. Even our "camera" tile is just a placeholder.

Actionable: With WebRTC in place, feed user video frames to a lightweight vision model (e.g., a fine-tuned CLIP or even GPT-4V for facial emotion classification).

4. 🟡 Real-time STT (Server-side)
We use the browser's Web Speech API (useSpeechRecognition hook). It's free but:

Unreliable across browsers
No streaming to server — transcript arrives after user stops
Can't do server-side turn-taking decisions
Tavus uses Deepgram server-side — streams audio from WebRTC, gets real-time word-level transcripts.

Actionable: Add Deepgram or Whisper streaming STT. Costs ~$0.0043/min (Deepgram) or free with local Whisper.

5. 🟡 Smarter Turn-Taking (Sparrow equivalent)
Our turn-taking (_keyword_selector at main.py:614) is keyword matching + random fallback. Tavus's Sparrow:

Predicts when user is done speaking (not just silence detection)
Handles interruptions mid-sentence
Controls conversational rhythm
Actionable: Train a lightweight classifier on conversation signals (pause duration, intonation drop, sentence completion markers) to predict turn boundaries.

Where We're Already Strong
🟢 Multi-Agent Architecture — Tavus is single-avatar. We run AutoGen SelectorGroupChat with multiple AI personalities. This is genuinely differentiated.
🟢 Persistent Memory — Our dual-layer ChromaDB (personal + shared) + SQLite + agent notes is comparable or better than what Tavus describes.
🟢 Meeting Persistence — Rejoin past meetings with full history. Tavus mentions persistent memory but not meeting replay.
🟢 Dynamic Agent Creation — Users can create custom agents via /agents endpoint + AI generation. Tavus agents are pre-configured.
Prioritized Roadmap — IMPLEMENTATION STATUS (Audited March 2026)
Priority	Feature	Status	Files Changed
P0	Parallel TTS pipeline	✅ DONE	backend/main.py (_stream_text_and_audio — concurrent TTS for all sentences)
P0	Token-level LLM streaming	✅ DONE	backend/main.py (_stream_llm_tokens → _try_extract_sentence → interleaved text+TTS)
P1	Multi-TTS providers	✅ DONE	backend/tts_providers.py (Cartesia, ElevenLabs, Deepgram, Edge — auto-fallback)
P1	Server-side STT (Deepgram)	✅ DONE	backend/main.py (/ws/stt), frontend/hooks/useServerSTT.ts (+ browser fallback)
P2	Smarter turn-taking	✅ DONE	backend/main.py (_pick_next_agent — 4-factor weighted: relevance/recency/diversity/reactivity)
P2	LiveKit WebRTC transport	✅ DONE	backend/livekit_room.py (RoomManager joins room, subscribes to user audio → Deepgram STT), frontend/hooks/useLiveKitRoom.ts (connects room, publishes mic/camera via WebRTC), MeetingRoom.tsx (auto-detects LiveKit from session_start, disables fallback STT)
P3	User perception (emotion)	✅ DONE	backend/perception.py (Gemini Flash vision), /perception/analyze endpoint, emotion injected into agent prompts via _build_llm_messages(), frontend/hooks/useEmotionDetection.ts (webcam capture every 5s when camera ON)
P3	User interruption handling	✅ DONE	frontend MeetingRoom.tsx (sendVoiceTranscript cancels audio queue + stops playback when user speaks)
P3	WebGL green-screen compositing	⏳ DEFERRED	Requires real-time video rendering first

Remaining Gaps (not code — configuration/infrastructure):
- LiveKit requires a running server (docker or cloud) + LIVEKIT_URL/KEY/SECRET in .env
- Deepgram STT requires DEEPGRAM_API_KEY in .env (falls back to browser Speech Recognition)
- Faster TTS: set TTS_PROVIDER=cartesia + CARTESIA_API_KEY for ~100ms latency (vs ~400ms Edge)
- Faster LLM: switch OPENROUTER_MODEL to groq/llama for ~100ms TTFT
- Video rendering: MuseTalk disabled (too slow on RTX 3060), CSS animations used instead

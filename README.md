<div align="center">

# 🌀 The Multiverse of You

**An AI-powered brainstorming room where you talk to Any no of expert personas — all variants of the same person from parallel universes.**

*Think Google Meet, but your colleagues are AI agents with real backstories, opinions, and expertise.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![AutoGen](https://img.shields.io/badge/AutoGen-0.4%2B-green.svg)](https://github.com/microsoft/autogen)

</div>

---

## What is this?

Imagine you could brainstorm with 8 versions of yourself — each one took a different career path. One became a startup CEO, another a Google architect, another a DeepMind researcher. They all share your curiosity and drive, but bring wildly different expertise to the table.

That's **The Multiverse of You**.

You join a virtual meeting room, pick your team of AI agents, type or speak your idea, and watch them debate, build on each other's points, and challenge your thinking — complete with voice responses and speaking animations.

**It's a fun project.** Built for tinkerers, AI enthusiasts, and anyone who wants to see what multi-agent conversations feel like in a real-time UI.

---

## For this example here are my variants

| Emoji | Variant | Expertise | Backstory |
|:-----:|---------|-----------|-----------|
| 🚀 | **The Visionary** | Startups, fundraising, go-to-market | Dropped out of PhD, built a company in a garage, sold it for 9 figures |
| 🏗️ | **The Architect** | Distributed systems, API design, security | Ex-Google/Stripe, designed systems serving billions of requests |
| ⚡ | **The Builder** | Full-stack dev, React, testing, DevOps | Started coding at 13, polyglot engineer, ex-Meta |
| 🧬 | **The Scientist** | Deep learning, NLP, causal inference | PhD → DeepMind postdoc, 23 papers, NeurIPS best paper |
| ⚙️ | **The Machinist** | MLOps, GPU optimization, model serving | Ex-Netflix, turned Jupyter notebooks into 10k inferences/sec |
| 📊 | **The Datasmith** | Data modeling, dbt, Spark, pipelines | Ex-Airbnb, built the data platform a whole company trusts |
| 🎯 | **The Strategist** | Product strategy, user research, prioritization | Ex-Notion/Spotify, killed 3 features everyone loved, shipped 1 that doubled revenue |
| 🎨 | **The Artist** | Interaction design, accessibility, design systems | Ex-Apple/Figma, made an app so intuitive the onboarding tutorial was deleted |

> **Want your own agents?** Just edit `agents.config.json` — add a name, backstory, expertise, and optionally an image. No code changes needed. [See below.](#-create-your-own-agents)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        BROWSER — Next.js (localhost:3001)                        │
│                                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Your Tile│  │ Agent 1  │  │ Agent 2  │  │ Agent 3  │  │  Chat sidebar    │  │
│  │ (webcam) │  │(speaking)│  │          │  │          │  │  (text + files)  │  │
│  └────┬─────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
│       │                                                                          │
│       ├── useLiveKitRoom ──── WebRTC mic + camera ──────────┐                   │
│       ├── useEmotionDetection ── webcam frames (5s) ────────┼──┐                │
│       └── useServerSTT / useSpeechRecognition (fallback) ───┼──┼──┐             │
│                                                              │  │  │             │
│  Controls: [🎤 Mute] [📷 Camera] [💬 Chat] [📞 Leave]      │  │  │             │
└──────────────────────────────────────────────────────────────┼──┼──┼─────────────┘
                                                               │  │  │
               WebRTC (UDP, low-latency)  ─────────────────────┘  │  │
               HTTPS POST /perception ────────────────────────────┘  │
               WebSocket /ws/chat  + /ws/stt ────────────────────────┘
                                                               │
┌────────────────────┐                                         │
│  LIVEKIT SERVER    │◄──── WebRTC audio/video ────────────────┘
│  (Docker :7880)    │                                         │
│  Echo cancellation │      WebSocket (text + audio)           │
│  Noise suppression │                                         ▼
│  Opus codec        │     ┌──────────────────────────────────────────────────────┐
└────────┬───────────┘     │            BACKEND — FastAPI (localhost:8000)         │
         │                 │                                                      │
         │ WebRTC          │  livekit_room.py ── subscribes to user audio          │
         └────────────────►│    └→ streams PCM to Deepgram STT                    │
                           │    └→ returns transcripts                             │
                           │                                                      │
                           │  MeetingSession (AutoGen GroupChat)                   │
                           │    ├── Agent 1 (persona + memory + emotion context)  │
                           │    ├── Agent 2     "                                 │
                           │    └── Agent N     "                                 │
                           │                                                      │
                           │  TTS Pipeline ── parallel sentence streaming          │
                           │    └→ base64 MP3 chunks → WebSocket → browser        │
                           │                                                      │
                           │  perception.py ── Gemini Flash emotion analysis       │
                           └──────────┬───────────┬───────────┬───────────────────┘
                                      │           │           │
                                ┌─────┴───┐ ┌────┴────┐ ┌────┴──────┐
                                │Deepgram │ │OpenRouter│ │  Gemini   │
                                │STT+TTS  │ │  LLM    │ │  Flash    │
                                │(Nova-2) │ │ (cloud) │ │ (emotion) │
                                └─────────┘ └─────────┘ └───────────┘
```

### STT Priority Chain (automatic fallback)

| Priority | Method | Latency | Requirement |
|----------|--------|---------|-------------|
| 1st | **LiveKit WebRTC + Deepgram** | ~100-300ms | LiveKit server + `DEEPGRAM_API_KEY` |
| 2nd | **Deepgram direct** (`/ws/stt`) | ~200-400ms | `DEEPGRAM_API_KEY` only |
| 3rd | **Browser SpeechRecognition** | ~300-500ms | Chrome/Edge (built-in, free) |
| 4th | **Text chat only** | — | Always available |

### TTS Providers

| Provider | Set in `.env` | Latency | Cost |
|----------|---------------|---------|------|
| `edge` (default) | `TTS_PROVIDER=edge` | ~400ms | Free |
| `deepgram` | `TTS_PROVIDER=deepgram` | ~150-200ms | $200 free credit |
| `cartesia` | `TTS_PROVIDER=cartesia` | ~100ms | Paid |
| `elevenlabs` | `TTS_PROVIDER=elevenlabs` | ~300ms | Paid |

**No GPU required for the default setup.** The LLM runs in the cloud via OpenRouter, TTS uses Microsoft's free Edge TTS. Everything else is CPU-based.

---

## Minimum Requirements

### Default Setup (No GPU Needed)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Windows 10 / Linux / macOS | Windows 11 / Ubuntu 22.04 |
| **CPU** | Any modern quad-core | Intel i5 / Ryzen 5 or better |
| **RAM** | 4 GB | 8 GB |
| **GPU** | **Not required** | — |
| **Python** | 3.10+ | 3.10 or 3.11 |
| **Node.js** | 18+ | 20 LTS |
| **Internet** | Required (for OpenRouter API + Edge TTS) | Broadband |

### Optional: MuseTalk Lip-Sync Video (GPU Required)

If you want AI-generated lip-sync video avatars instead of CSS animations:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | NVIDIA RTX 3060 (12 GB VRAM) | NVIDIA RTX 4090 (24 GB VRAM) |
| **CUDA** | 11.7+ | 12.1+ |
| **VRAM** | 8 GB | 12+ GB |

> ⚠️ **Heads up:** On an RTX 3060, MuseTalk generates video ~15x slower than real-time (~25-30s for a 2s clip). The CSS animations look great and are instant — MuseTalk is only worth enabling on RTX 4080+ GPUs.

---

## Tech Stack & Libraries

### Backend (Python)

| Library | Version | Purpose | License |
|---------|---------|---------|--------|
| [AutoGen](https://github.com/microsoft/autogen) | ≥0.4.0 | Multi-agent orchestration (SelectorGroupChat) | MIT |
| [FastAPI](https://fastapi.tiangolo.com/) | ≥0.115.0 | WebSocket server + REST API | MIT |
| [Uvicorn](https://www.uvicorn.org/) | ≥0.34.0 | ASGI server | BSD-3 |
| [LiveKit Server SDK](https://github.com/livekit/python-sdks) | latest | WebRTC room management, audio subscription | Apache-2.0 |
| [Edge TTS](https://github.com/rany2/edge-tts) | latest | Free text-to-speech (default provider) | GPL-3.0 |
| [aiohttp](https://docs.aiohttp.org/) | latest | Async HTTP/WebSocket client (Deepgram, MuseTalk) | Apache-2.0 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | latest | Environment variable management | BSD-3 |
| [Loguru](https://github.com/Delgan/loguru) | latest | Beautiful logging | MIT |
| [websockets](https://websockets.readthedocs.io/) | ≥14.0 | WebSocket protocol support | BSD-3 |

### Frontend (TypeScript)

| Library | Version | Purpose | License |
|---------|---------|---------|--------|
| [Next.js](https://nextjs.org/) | 16.1.6 | React framework with App Router | MIT |
| [React](https://react.dev/) | 19.2.3 | UI library | MIT |
| [Tailwind CSS](https://tailwindcss.com/) | 4.x | Utility-first CSS framework | MIT |
| [livekit-client](https://github.com/livekit/client-sdk-js) | latest | WebRTC client for LiveKit rooms | Apache-2.0 |
| [TypeScript](https://www.typescriptlang.org/) | 5.x | Type safety | Apache-2.0 |

### Optional: MuseTalk (Lip-Sync Video)

| Library | Purpose | License |
|---------|---------|---------|
| [MuseTalk](https://github.com/TMElyralab/MuseTalk) | Real-time lip-sync video generation | MIT |
| [PyTorch](https://pytorch.org/) | Deep learning runtime | BSD-3 |
| [OpenCV](https://opencv.org/) | Video processing | Apache-2.0 |
| [FFmpeg](https://ffmpeg.org/) | Audio/video muxing | LGPL/GPL |

### Cloud Services

| Service | Purpose | Cost |
|---------|---------|------|
| [OpenRouter](https://openrouter.ai/) | LLM API (Llama, GPT, Claude, etc.) | Pay-per-token (many free models available) |
| [Deepgram](https://deepgram.com/) | STT (Nova-2) + optional TTS (Aura) | **$200 free credit**, no CC required |
| [Gemini Flash](https://ai.google.dev/) | Emotion/perception analysis from webcam | Free tier available |
| Microsoft Edge TTS | Neural text-to-speech (default) | **Free** |
| [LiveKit](https://livekit.io/) | WebRTC SFU server (self-hosted via Docker) | **Free** (open source) |

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/tapankumarpatro/metrastrome.git
cd metrastrome
```

### 2. Start the Backend

```bash
# Create a virtual environment
python -m venv backend/venv

# Activate it
# Windows:
backend\venv\Scripts\activate
# Linux/macOS:
source backend/venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

Set up your environment:

```bash
# Windows:
copy backend\.env.example backend\.env
# Linux/macOS:
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your API keys:

```env
# Required
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=meta-llama/llama-4-maverick

# Recommended — enables high-quality voice input + optional fast TTS
DEEPGRAM_API_KEY=your-deepgram-key-here   # Free $200 credit at deepgram.com
TTS_PROVIDER=edge                          # edge (free) | deepgram (~2x faster) | cartesia | elevenlabs
```

> **API keys:**
> - [openrouter.ai](https://openrouter.ai) — LLM. Many models (like Llama) have free tiers.
> - [deepgram.com](https://console.deepgram.com/signup) — STT + TTS. **$200 free credit**, no credit card.

### 3. Start LiveKit (recommended — enables WebRTC voice)

Requires [Docker](https://docs.docker.com/desktop/install/windows-install/).

```powershell
# Option A: Use the included script (Windows)
.\start_livekit.ps1

# Option B: Manual
docker run -d --name metrastrome-livekit \
  -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
  --restart unless-stopped \
  livekit/livekit-server --dev
```

LiveKit env vars are already set in `.env.example` — no changes needed for local dev.

> **Don't want LiveKit?** Just comment out the `LIVEKIT_*` vars in `.env`. Voice falls back to Deepgram direct STT or browser speech recognition.

### 4. Run the backend

```bash
cd backend
python main.py
# OR if you prefer uvicorn directly:
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:

```
Loaded 9 agents from config
[LiveKit] Joined room: ...         ← confirms WebRTC is active
Uvicorn running on http://0.0.0.0:8000
```

### 5. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. Open in your browser

Go to **http://localhost:3001**, enter your name, pick your agents, and start brainstorming!

The header shows **"WebRTC"** when LiveKit is active, or **"Connected"** when using WebSocket fallback.

---

## Project Structure

```
metrastrome/
├── agents.config.json              # 🎯 Agent definitions (edit this to customize!)
├── start_livekit.ps1               # LiveKit server manager script (Windows)
├── README.md
│
├── backend/                        # Python FastAPI + AutoGen server
│   ├── agents/
│   │   └── base_agent.py           # Loads agents from JSON, builds system prompts
│   ├── main.py                     # WebSocket server, 3-phase conversation orchestrator, TTS
│   ├── livekit_room.py             # LiveKit WebRTC room manager (audio → Deepgram STT)
│   ├── livekit_service.py          # LiveKit token generation + health checks
│   ├── perception.py               # Emotion detection via Gemini Flash
│   ├── tts_providers.py            # TTS abstraction (edge/deepgram/cartesia/elevenlabs)
│   ├── memory_store.py             # ChromaDB dual-layer vector memory (shared + per-agent)
│   ├── conversation_store.py       # SQLite persistence (sessions, messages, agent notes)
│   ├── file_utils.py               # File text extraction (PDF, DOCX, CSV, code, etc.)
│   ├── check_gpu.py                # GPU capability detection
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                        # Your API keys (gitignored)
│
├── frontend/                       # Next.js 16 + React 19 + Tailwind v4
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Landing page — agent selection grid
│   │   │   └── meet/
│   │   │       └── page.tsx        # Meeting room entry point
│   │   ├── components/
│   │   │   ├── MeetingRoom.tsx     # Main meeting UI — tiles, chat, WebSocket, LiveKit
│   │   │   ├── ParticipantTile.tsx # Agent video tiles with speaking animations
│   │   │   └── MeetingControls.tsx # Mic, camera, chat toggle buttons
│   │   ├── hooks/
│   │   │   ├── useLiveKitRoom.ts   # WebRTC connection to LiveKit (mic + camera)
│   │   │   ├── useServerSTT.ts     # Deepgram direct STT via /ws/stt (fallback)
│   │   │   ├── useSpeechRecognition.ts  # Browser speech-to-text (last resort)
│   │   │   └── useEmotionDetection.ts   # Webcam → emotion analysis
│   │   └── lib/
│   │       └── agents.ts           # Dynamic agent fetching from backend API
│   └── public/
│       └── images/                 # Agent avatar photos (optional)
│
├── musetalk/                       # Optional: MuseTalk lip-sync (disabled by default)
│   ├── service.py                  # FastAPI wrapper on port 8001
│   └── ...                         # MuseTalk model code and weights
│
└── infrastructure/                 # Docker configs (optional)
```

---

## 🧬 Create Your Own Agents

The magic of this project is that agents are **fully configurable via JSON**. No code changes needed.

Edit `agents.config.json` at the project root:

```jsonc
{
  "agents": [
    // ... existing agents ...

    // Add your own!
    {
      "id": "tapan-hacker",                    // unique slug
      "agent_name": "TheHacker",               // internal name (no spaces)
      "variant": "The Hacker",                 // display name
      "tagline": "Broke into a bank's system at 16. Now secures them.",
      "emoji": "🔓",                           // avatar fallback if no image
      "color": "red",                           // amber|violet|blue|emerald|rose|cyan|orange|pink|red|green|purple|yellow|teal|indigo
      "personality": "Paranoid about security, loves CTFs, thinks in threat models",
      "backstory": "This Tapan discovered a buffer overflow in a banking app at 16...",
      "expertise": ["penetration testing", "cryptography", "zero-trust architecture"],
      "description": "A cybersecurity expert who thinks like an attacker. Best suited for security reviews and threat modeling.",
      "voice": "en-US-AndrewMultilingualNeural",  // Edge TTS voice name
      "image": "",                              // leave empty for emoji avatar, or "my_image.png"
      "projects": [
        {
          "name": "Project X",
          "role": "Lead",
          "period": "2020-2023",
          "description": "What you did...",
          "technologies": ["tech1", "tech2"],
          "outcome": "The result",
          "lesson": "The key takeaway"
        }
      ]
    }
  ]
}
```

### Agent images

- **With image:** Place a `.png` file in `frontend/public/images/` and set `"image": "filename.png"`
- **Without image:** Leave `"image": ""` — the emoji becomes a large animated avatar with a colored gradient background. Looks great!

### Available voices

Edge TTS provides many free neural voices. Some good ones:

| Voice | Accent | Style |
|-------|--------|-------|
| `en-US-AndrewMultilingualNeural` | American | Warm, conversational |
| `en-US-BrianMultilingualNeural` | American | Clear, professional |
| `en-US-RogerNeural` | American | Casual |
| `en-GB-ThomasNeural` | British | Thoughtful |
| `en-GB-RyanNeural` | British | Friendly |
| `en-AU-WilliamMultilingualNeural` | Australian | Relaxed |

Run `edge-tts --list-voices` for the full list.

---

## Optional: Enable Video Call (MuseTalk Lip-Sync)

> Only recommended for GPUs with 16+ GB VRAM (RTX 4090/5090). On lower-end GPUs, CSS speaking animations are used instead.

1. Check your GPU capabilities:

```bash
cd backend
python check_gpu.py
```

2. If recommended, edit `backend/.env`:

```env
USE_VIDEO_CALL=true
MUSETALK_URL=http://localhost:8001
```

3. Set up and start the MuseTalk service:

```bash
cd musetalk
python service.py
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | **Yes** | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-4-maverick` | LLM model to use |
| `DEEPGRAM_API_KEY` | Recommended | — | Deepgram API key (STT + optional TTS). Free $200 credit |
| `TTS_PROVIDER` | No | `edge` | TTS engine: `edge` \| `deepgram` \| `cartesia` \| `elevenlabs` |
| `LIVEKIT_URL` | No | `ws://localhost:7880` | LiveKit server URL (WebRTC) |
| `LIVEKIT_API_KEY` | No | `devkey` | LiveKit API key (dev mode default) |
| `LIVEKIT_API_SECRET` | No | `secret` | LiveKit API secret (dev mode default) |
| `KIE_API_KEY` | No | — | Kie.ai image generation key |
| `USE_VIDEO_CALL` | No | `false` | Enable lip-sync video (needs 16+ GB VRAM GPU) |
| `MUSETALK_URL` | No | `http://localhost:8001` | MuseTalk service URL |

### Frontend (`frontend/.env.local`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_WS_URL` | No | `ws://localhost:8000` | Backend WebSocket URL |

---

## CLI Options

```bash
# Run with all agents (default)
python backend/main.py

# Run with specific agents only
python backend/main.py --agents tapan-architect,tapan-builder,tapan-strategist

# Run on a custom port
python backend/main.py --port 8080
```

---

## How It Works

1. **You join a meeting room** and pick which variants you want in your brainstorming session
2. **You speak or type** your idea — voice goes through LiveKit WebRTC → Deepgram STT (or type in chat)
3. **Your emotion is detected** from your webcam every 5 seconds via Gemini Flash — agents adapt their tone
4. **The 3-phase conversation orchestrator** plans the response:
   - **Phase 1 (Plan):** Scores all agents by expertise relevance → decides who speaks and how (zero LLM calls, ~0ms)
   - **Phase 2 (Primary):** Lead agent gives a detailed answer; supporting agents add perspectives or brief reactions
   - **Phase 3 (Follow-up):** Agents react to each other — agreeing, pushing back, building on points (like a real call)
5. **Response length varies naturally** — quick 1-sentence reactions, normal 2-4 sentence replies, or detailed 4-8 sentence deep dives
6. **Agents can [pass]** if they have nothing meaningful to add — no forced robotic one-liners
7. **TTS converts each response to audio** — sentences are generated in parallel for low latency
8. **The agent's tile animates** — photo zooms, glow ring pulses, equalizer bars dance
9. **You can interrupt anytime** — speaking mid-agent cancels their audio immediately
10. **Agents remember you** — dual-layer memory (ChromaDB) persists context across sessions

---

## Fun Things to Try

- 🧠 **"I want to build a SaaS for [X]"** — watch The Visionary and The Strategist debate go-to-market while The Architect designs the system
- 🔬 **"How should we evaluate this ML model?"** — The Scientist will insist on proper experiment design while The Machinist asks about serving latency
- 🎨 **"Review this UI mockup"** — The Artist will fight for accessibility while The Builder asks about implementation cost
- 📊 **"Our data pipeline is slow"** — The Datasmith and The Architect will have opinions
- 🤔 **"Should we rewrite our backend in Rust?"** — grab popcorn

---

## Credits & Acknowledgments

This project stands on the shoulders of amazing open-source work:

- **[Microsoft AutoGen](https://github.com/microsoft/autogen)** — The multi-agent framework that makes the group chat magic possible
- **[LiveKit](https://livekit.io/)** — Open-source WebRTC SFU for real-time audio/video transport
- **[Deepgram](https://deepgram.com/)** — Lightning-fast speech-to-text (Nova-2) and text-to-speech (Aura)
- **[FastAPI](https://fastapi.tiangolo.com/)** — Blazing fast Python web framework by Sebastián Ramírez
- **[Next.js](https://nextjs.org/)** by Vercel — The React framework for the web
- **[Tailwind CSS](https://tailwindcss.com/)** — Utility-first CSS that made the UI possible in record time
- **[Edge TTS](https://github.com/rany2/edge-tts)** by rany2 — Free access to Microsoft's neural TTS voices
- **[MuseTalk](https://github.com/TMElyralab/MuseTalk)** by Tencent's Lyra Lab — Real-time lip-sync video generation
- **[OpenRouter](https://openrouter.ai/)** — Unified API for all the best LLMs
- **[Loguru](https://github.com/Delgan/loguru)** — Python logging that doesn't suck
- **[Uvicorn](https://www.uvicorn.org/)** — Lightning-fast ASGI server

If you use this project, build on it, or learn from it — **a credit or mention would be awesome!** This is a fun community project, and spreading the word helps it grow. 🌀

---

## Contributing

This is a fun, experimental project. PRs welcome! Some ideas:

- 🌍 **Multi-language support** — agents that speak different languages
- 🖼️ **AI-generated agent portraits** — auto-generate images from backstories
- 📱 **Mobile layout** — responsive meeting room for phones
- 🔌 **Plugin system** — let agents call external tools (search, code execution, etc.)
- 🎭 **More agent personalities** — submit your own via PR to `agents.config.json`!
- 🔊 **LiveKit audio output** — route agent TTS audio through WebRTC instead of WebSocket
- 💬 **Conversation tuning** — tweak the 3-phase orchestrator weights for different conversation styles
- 📊 **Analytics dashboard** — visualize agent speaking patterns, topic coverage, memory usage

---

## License

MIT License — do whatever you want with it.

```
MIT License

Copyright (c) 2025 The Multiverse of Tapan Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<div align="center">

**Built with curiosity, caffeine, and a healthy disrespect for the idea that you can only live one life.** 🌀

*If you build something cool with this, let us know!*

</div>

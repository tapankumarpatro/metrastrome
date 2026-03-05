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

## The Agents

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
┌─────────────────────┐        WebSocket (ws://localhost:8000)        ┌──────────────────────────────┐
│                     │ ◄──────────────────────────────────────────► │                              │
│   Next.js Frontend  │    text messages + base64 audio streaming    │   FastAPI + AutoGen Backend  │
│   (React, Tailwind) │                                              │                              │
│   localhost:3001    │                                              │   localhost:8000             │
└─────────────────────┘                                              └──────────┬───────────────────┘
                                                                                │
                                                                     ┌──────────┼──────────┐
                                                                     │          │          │
                                                               ┌─────┴───┐ ┌────┴────┐ ┌──┴──────────┐
                                                               │ AutoGen │ │Edge TTS │ │ OpenRouter  │
                                                               │ Group   │ │ (free)  │ │ LLM API    │
                                                               │ Chat    │ │         │ │ (cloud)    │
                                                               └─────────┘ └─────────┘ └─────────────┘
```

**No GPU required for the default setup.** The LLM runs in the cloud via OpenRouter, and TTS uses Microsoft's free Edge TTS service. Everything else is CPU-based.

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
|---------|---------|---------|---------|
| [AutoGen](https://github.com/microsoft/autogen) | ≥0.4.0 | Multi-agent orchestration (SelectorGroupChat) | MIT |
| [FastAPI](https://fastapi.tiangolo.com/) | ≥0.115.0 | WebSocket server + REST API | MIT |
| [Uvicorn](https://www.uvicorn.org/) | ≥0.34.0 | ASGI server | BSD-3 |
| [Edge TTS](https://github.com/rany2/edge-tts) | latest | Free text-to-speech via Microsoft Edge neural voices | GPL-3.0 |
| [aiohttp](https://docs.aiohttp.org/) | latest | Async HTTP client (MuseTalk integration) | Apache-2.0 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | latest | Environment variable management | BSD-3 |
| [Loguru](https://github.com/Delgan/loguru) | latest | Beautiful logging | MIT |
| [websockets](https://websockets.readthedocs.io/) | ≥14.0 | WebSocket protocol support | BSD-3 |

### Frontend (TypeScript)

| Library | Version | Purpose | License |
|---------|---------|---------|---------|
| [Next.js](https://nextjs.org/) | 16.1.6 | React framework with App Router | MIT |
| [React](https://react.dev/) | 19.2.3 | UI library | MIT |
| [Tailwind CSS](https://tailwindcss.com/) | 4.x | Utility-first CSS framework | MIT |
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
| Microsoft Edge TTS | Neural text-to-speech | **Free** |

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/your-username/metrastrome.git
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

Edit `backend/.env` and add your OpenRouter API key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=meta-llama/llama-4-maverick
```

> Get a free API key at [openrouter.ai](https://openrouter.ai). Many models (like Llama) have free tiers.

Run the backend:

```bash
python backend/main.py
```

You should see:

```
Loaded 8 agents from config
Starting server with 8 agent(s)
Uvicorn running on http://0.0.0.0:8000
```

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open in your browser

Go to **http://localhost:3001**, enter your name, pick your agents, and start brainstorming!

---

## Project Structure

```
metrastrome/
├── agents.config.json          # 🎯 Agent definitions (edit this to customize!)
├── README.md
│
├── backend/                    # Python FastAPI + AutoGen server
│   ├── agents/
│   │   └── base_agent.py       # Loads agents from JSON, builds system prompts
│   ├── main.py                 # WebSocket server, TTS, group chat orchestration
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                    # Your API keys (gitignored)
│
├── frontend/                   # Next.js 16 + React 19 + Tailwind v4
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx        # Landing page — agent selection grid
│   │   │   └── meet/
│   │   │       └── page.tsx    # Meeting room entry point
│   │   ├── components/
│   │   │   ├── MeetingRoom.tsx # Main meeting UI — chat, audio, WebSocket
│   │   │   ├── ParticipantTile.tsx  # Agent video tiles with animations
│   │   │   └── MeetingControls.tsx  # Mic, camera, chat toggle buttons
│   │   ├── hooks/
│   │   │   └── useSpeechRecognition.ts  # Browser speech-to-text
│   │   └── lib/
│   │       └── agents.ts       # Dynamic agent fetching from backend API
│   └── public/
│       └── images/             # Agent avatar photos (optional)
│
├── musetalk/                   # Optional: MuseTalk lip-sync (disabled by default)
│   ├── service.py              # FastAPI wrapper on port 8001
│   └── ...                     # MuseTalk model code and weights
│
└── infrastructure/             # Docker configs (optional, for LiveKit)
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

## Optional: Enable MuseTalk Lip-Sync Video

> Only recommended for RTX 4080+ GPUs. On lower-end GPUs, the CSS animations are a better experience.

1. Set up MuseTalk following the instructions in `musetalk/README.md`
2. Edit `backend/.env`:

```env
MUSETALK_ENABLED=true
MUSETALK_URL=http://localhost:8001
```

3. Start the MuseTalk service:

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
| `MUSETALK_ENABLED` | No | `false` | Enable lip-sync video (needs GPU) |
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

1. **You join a meeting room** and pick which Tapan variants you want in your brainstorming session
2. **You type or speak** your idea or question
3. **AutoGen's SelectorGroupChat** dynamically picks the most relevant agent to respond based on context
4. **The agent responds** with a short, conversational answer (1-3 sentences, like a real call)
5. **Edge TTS** converts the response to audio, which streams back to your browser
6. **The agent's tile animates** — photo zooms, glow ring pulses, equalizer bars dance
7. **The conversation continues** naturally, with agents building on each other's points

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

- 🎤 **Better STT** — integrate Whisper for more accurate speech recognition
- 🌍 **Multi-language support** — agents that speak different languages
- 🖼️ **AI-generated agent portraits** — auto-generate images from backstories
- 📱 **Mobile layout** — responsive meeting room for phones
- 🔌 **Plugin system** — let agents call external tools (search, code execution, etc.)
- 🎭 **More agent personalities** — submit your own via PR to `agents.config.json`!

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

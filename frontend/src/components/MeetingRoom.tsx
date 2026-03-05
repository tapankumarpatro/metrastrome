"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ParticipantTile } from "./ParticipantTile";
import { MeetingControls } from "./MeetingControls";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import type { AgentInfo } from "@/lib/agents";
import { getProfile } from "@/lib/profile";

export interface MeetingRoomProps {
  wsUrl: string;
  identity: string;
  enabledAgents: AgentInfo[];
  onLeave: () => void;
}

interface ChatMessage {
  id: string;
  type: "user" | "agent" | "system";
  agentId?: string;
  variant?: string;
  content: string;
  timestamp: number;
}

export function MeetingRoom({
  wsUrl,
  identity,
  enabledAgents,
  onLeave,
}: MeetingRoomProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingAgent, setThinkingAgent] = useState<string | null>(null);
  const [speakingAgentId, setSpeakingAgentId] = useState<string | null>(null);
  const [agentVideos, setAgentVideos] = useState<Record<string, string>>({});
  const [isMuted, setIsMuted] = useState(true);
  const [isCameraOff, setIsCameraOff] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const msgIdRef = useRef(0);

  // ── Audio playback state (declared early so speech recognition can reference it) ──
  const audioQueueRef = useRef<Array<{ audioB64: string; agentId: string }>>([]);
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const [playingAgentId, setPlayingAgentId] = useState<string | null>(null);

  // ── Speech Recognition: mic → transcript → WebSocket ──
  const sendVoiceTranscript = useCallback((transcript: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [
      ...prev,
      { id: `user-${++msgIdRef.current}`, type: "user", content: transcript, timestamp: Date.now() },
    ]);
    wsRef.current.send(JSON.stringify({ type: "chat", content: transcript }));
    setIsThinking(true);
  }, []);

  const isAudioPlaying = playingAgentId !== null;

  const { isListening, isSupported: sttSupported } = useSpeechRecognition({
    onTranscript: sendVoiceTranscript,
    enabled: !isMuted && isConnected,
    pauseWhilePlaying: isAudioPlaying,
  });

  const playNextInQueue = useCallback(() => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    const next = audioQueueRef.current.shift();
    if (!next) return;

    isPlayingRef.current = true;
    setPlayingAgentId(next.agentId);
    console.log("[Audio] Playing for", next.agentId);

    const audio = new Audio(`data:audio/mp3;base64,${next.audioB64}`);
    currentAudioRef.current = audio;
    audio.onended = () => {
      console.log("[Audio] Ended for", next.agentId);
      isPlayingRef.current = false;
      setPlayingAgentId(null);
      currentAudioRef.current = null;
      playNextInQueue();
    };
    audio.onerror = (e) => {
      console.error("[Audio] Error for", next.agentId, e);
      isPlayingRef.current = false;
      setPlayingAgentId(null);
      currentAudioRef.current = null;
      playNextInQueue();
    };
    audio.play().catch((err) => {
      console.error("[Audio] play() failed for", next.agentId, err);
      isPlayingRef.current = false;
      setPlayingAgentId(null);
      playNextInQueue();
    });
  }, []);

  const enqueueAudio = useCallback((audioB64: string, agentId: string) => {
    audioQueueRef.current.push({ audioB64, agentId });
    playNextInQueue();
  }, [playNextInQueue]);

  const stopAllAudio = useCallback(() => {
    audioQueueRef.current = [];
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    isPlayingRef.current = false;
    setPlayingAgentId(null);
  }, []);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Track unread messages when chat is closed
  useEffect(() => {
    if (isChatOpen) setUnreadCount(0);
  }, [isChatOpen]);

  // WebSocket connection
  useEffect(() => {
    const agentIds = enabledAgents.map((a) => a.id).join(",");
    const userName = encodeURIComponent(identity);
    const videoMode = getProfile().videoMode ? "1" : "0";
    const url = `${wsUrl}/ws/chat?agents=${agentIds}&user=${userName}&video=${videoMode}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      addSystemMessage(`Connected. ${enabledAgents.length} variant${enabledAgents.length !== 1 ? "s" : ""} ready.`);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "agent_typing") {
        setIsThinking(true);
        setThinkingAgent(data.variant || data.agent_id);
      } else if (data.type === "agent_message") {
        setIsThinking(false);
        setThinkingAgent(null);
        setSpeakingAgentId(data.agent_id);
        setMessages((prev) => [
          ...prev,
          {
            id: `agent-${++msgIdRef.current}`,
            type: "agent",
            agentId: data.agent_id,
            variant: data.variant,
            content: data.content,
            timestamp: Date.now(),
          },
        ]);
        setUnreadCount((c) => c + 1);

        // speakingAgentId clears when round_complete arrives or audio ends (playingAgentId handles that)
      } else if (data.type === "agent_audio") {
        // Queue the audio for playback
        enqueueAudio(data.audio, data.agent_id);
      } else if (data.type === "agent_video") {
        // Lip-synced MP4 video arrived from MuseTalk
        console.log("[MeetingRoom] agent_video received for", data.agent_id, "size:", data.video?.length || 0, "chars");
        if (data.video) {
          setAgentVideos((prev) => ({
            ...prev,
            [data.agent_id]: data.video,
          }));
        }
      } else if (data.type === "round_complete") {
        setIsThinking(false);
        setSpeakingAgentId(null);
      } else if (data.type === "error") {
        setIsThinking(false);
        addSystemMessage(`Error: ${data.content}`);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      addSystemMessage("Disconnected from server.");
    };

    return () => { ws.close(); };
  }, [wsUrl, enabledAgents]);

  function addSystemMessage(content: string) {
    setMessages((prev) => [
      ...prev,
      { id: `sys-${++msgIdRef.current}`, type: "system", content, timestamp: Date.now() },
    ]);
  }

  const sendMessage = useCallback(() => {
    const text = chatInput.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [
      ...prev,
      { id: `user-${++msgIdRef.current}`, type: "user", content: text, timestamp: Date.now() },
    ]);
    wsRef.current.send(JSON.stringify({ type: "chat", content: text }));
    setChatInput("");
    setIsThinking(true);
    chatInputRef.current?.focus();
  }, [chatInput]);

  const getAgentInfo = (agentId?: string) =>
    enabledAgents.find((a) => a.id === agentId);

  // Grid columns based on participant count
  const totalTiles = enabledAgents.length + 1;
  const gridCols =
    totalTiles <= 2
      ? "grid-cols-1 sm:grid-cols-2"
      : totalTiles <= 4
        ? "grid-cols-2"
        : totalTiles <= 6
          ? "grid-cols-2 lg:grid-cols-3"
          : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4";

  return (
    <div className="flex h-screen flex-col bg-zinc-950">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-zinc-800 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600">
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-white">The Multiverse of Tapan</h1>
            <p className="text-xs text-zinc-500">
              {enabledAgents.length + 1} participants
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <div className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500" : "bg-amber-500 animate-pulse"}`} />
          <span className="text-zinc-400">{isConnected ? "Connected" : "Connecting..."}</span>
        </div>
      </header>

      {/* Main: Tile grid + optional chat panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Participant tile grid (PRIMARY view) ── */}
        <div className="flex flex-1 items-center justify-center p-4">
          <div className={`grid w-full max-w-6xl gap-3 ${gridCols}`}>
            {/* You tile */}
            <ParticipantTile
              name={`${identity} (You)`}
              role={isListening ? "Listening..." : isMuted ? "Muted" : "You"}
              initials={identity.slice(0, 2).toUpperCase()}
              isLocal={true}
              isSpeaking={isListening}
              isAgent={false}
              isConnected={isConnected}
              iconBg="bg-zinc-700"
              iconText="text-zinc-300"
            />

            {/* Agent tiles */}
            {enabledAgents.map((agent) => (
              <ParticipantTile
                key={agent.id}
                name={agent.variant}
                role={agent.personality.split(",")[0]}
                initials={agent.emoji}
                isLocal={false}
                isSpeaking={speakingAgentId === agent.id || playingAgentId === agent.id}
                isAgent={true}
                isConnected={isConnected}
                iconBg={agent.iconBg}
                iconText={agent.iconText}
                agentId={agent.id}
                agent={agent}
              />
            ))}
          </div>
        </div>

        {/* ── Chat panel (collapsible sidebar) ── */}
        {isChatOpen && (
          <aside className="flex w-80 shrink-0 flex-col border-l border-zinc-800 bg-zinc-900/50">
            {/* Chat header */}
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <span className="text-sm font-semibold text-white">Chat</span>
              <button
                onClick={() => setIsChatOpen(false)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5">
              {messages.map((msg) => {
                if (msg.type === "system") {
                  return (
                    <div key={msg.id} className="text-center">
                      <span className="text-[10px] text-zinc-600">{msg.content}</span>
                    </div>
                  );
                }

                if (msg.type === "user") {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-xl rounded-br-sm bg-violet-600 px-3 py-2">
                        <p className="text-xs text-white">{msg.content}</p>
                      </div>
                    </div>
                  );
                }

                const agent = getAgentInfo(msg.agentId);
                return (
                  <div key={msg.id} className="flex items-start gap-2">
                    <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${agent?.iconBg || "bg-zinc-700"}`}>
                      <svg viewBox="0 0 80 80" className={`h-3.5 w-3.5 ${agent?.iconText || "text-zinc-400"}`} fill="currentColor">
                        <circle cx="40" cy="28" r="14" />
                        <ellipse cx="40" cy="64" rx="24" ry="16" />
                      </svg>
                    </div>
                    <div className="max-w-[85%]">
                      <span className="text-[10px] font-semibold text-zinc-400">{msg.variant}</span>
                      <div className="rounded-xl rounded-tl-sm bg-zinc-800 px-3 py-2">
                        <p className="text-xs leading-relaxed text-zinc-300">{msg.content}</p>
                      </div>
                    </div>
                  </div>
                );
              })}

              {isThinking && (
                <div className="flex items-center gap-2 px-2">
                  <div className="flex gap-1">
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-500" style={{ animationDelay: "0ms" }} />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-500" style={{ animationDelay: "150ms" }} />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-500" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span className="text-[10px] text-zinc-400">
                    {thinkingAgent ? `${thinkingAgent} is typing...` : "Agents are thinking..."}
                  </span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Chat input */}
            <div className="border-t border-zinc-800 p-3">
              <div className="flex gap-2">
                <input
                  ref={chatInputRef}
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  placeholder="Type a message..."
                  disabled={!isConnected || isThinking}
                  className="flex-1 rounded-lg bg-zinc-800 px-3 py-2 text-xs text-white placeholder-zinc-600 outline-none ring-1 ring-zinc-700 focus:ring-violet-500 disabled:opacity-50"
                />
                <button
                  onClick={sendMessage}
                  disabled={!isConnected || !chatInput.trim() || isThinking}
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-white disabled:opacity-30"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                  </svg>
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* Controls bar */}
      <MeetingControls
        isMuted={isMuted}
        isCameraOff={isCameraOff}
        isChatOpen={isChatOpen}
        onToggleMute={() => setIsMuted((m) => !m)}
        onToggleCamera={() => setIsCameraOff((c) => !c)}
        onToggleChat={() => { setIsChatOpen((o) => !o); setUnreadCount(0); }}
        onLeave={() => { stopAllAudio(); onLeave(); }}
        unreadCount={isChatOpen ? 0 : unreadCount}
      />
    </div>
  );
}

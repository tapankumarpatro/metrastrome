"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ParticipantTile } from "./ParticipantTile";
import { MeetingControls } from "./MeetingControls";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useServerSTT } from "@/hooks/useServerSTT";
import { useEmotionDetection } from "@/hooks/useEmotionDetection";
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import type { AgentInfo } from "@/lib/agents";

export interface MeetingRoomProps {
  wsUrl: string;
  identity: string;
  enabledAgents: AgentInfo[];
  onLeave: () => void;
  meetingId?: string;
}

interface ChatAttachment {
  file_id: string;
  name: string;
  url: string;
  size: number;
  is_image: boolean;
  mime: string;
}

interface ChatMessage {
  id: string;
  type: "user" | "agent" | "system";
  agentId?: string;
  variant?: string;
  content: string;
  timestamp: number;
  attachments?: ChatAttachment[];
}

export function MeetingRoom({
  wsUrl,
  identity,
  enabledAgents,
  onLeave,
  meetingId,
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
  const [pendingFiles, setPendingFiles] = useState<ChatAttachment[]>([]);
  const [uploadingFile, setUploadingFile] = useState(false);

  // LiveKit WebRTC state (populated from session_start message)
  const [livekitUrl, setLivekitUrl] = useState<string | null>(null);
  const [livekitRoom, setLivekitRoom] = useState<string | null>(null);
  const [livekitEnabled, setLivekitEnabled] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const msgIdRef = useRef(0);
  const streamMsgIdRef = useRef<string | null>(null);

  // ── Audio playback state (declared early so speech recognition can reference it) ──
  const audioQueueRef = useRef<Array<{ audioB64: string; agentId: string }>>([]);
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const [playingAgentId, setPlayingAgentId] = useState<string | null>(null);

  // ── Speech Recognition: mic → transcript → WebSocket ──
  const sendVoiceTranscript = useCallback((transcript: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    // Interrupt: stop any playing agent audio when user speaks
    audioQueueRef.current = [];
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    isPlayingRef.current = false;
    setPlayingAgentId(null);
    setSpeakingAgentId(null);

    setMessages((prev) => [
      ...prev,
      { id: `user-${++msgIdRef.current}`, type: "user", content: transcript, timestamp: Date.now() },
    ]);
    wsRef.current.send(JSON.stringify({ type: "chat", content: transcript }));
    setIsThinking(true);
  }, []);

  const isAudioPlaying = playingAgentId !== null;
  const apiUrl = wsUrl.replace("ws://", "http://").replace("wss://", "https://");

  // ── LiveKit WebRTC (when backend provides livekit info in session_start) ──
  const {
    isConnected: lkConnected,
    setMicEnabled: lkSetMic,
    setCameraEnabled: lkSetCamera,
  } = useLiveKitRoom({
    livekitUrl,
    roomName: livekitRoom,
    identity,
    enabled: livekitEnabled,
    apiUrl,
  });

  // When LiveKit is connected, it handles mic audio → backend STT.
  // Disable separate STT hooks to avoid double-processing.
  const useFallbackSTT = !livekitEnabled || !lkConnected;

  // Server-side STT (Deepgram via /ws/stt) — only when LiveKit is NOT active
  const { isListening: serverListening, isAvailable: serverSttAvailable, isChecking: sttChecking } = useServerSTT({
    wsUrl,
    onTranscript: sendVoiceTranscript,
    enabled: useFallbackSTT && !isMuted && isConnected,
    pauseWhilePlaying: isAudioPlaying,
  });

  // Browser STT — last resort fallback
  const browserSttEnabled = useFallbackSTT && !isMuted && isConnected && !serverSttAvailable && !sttChecking;
  const { isListening: browserListening, isSupported: browserSttSupported, error: browserSttError, requestStart: browserSttStart, requestStop: browserSttStop } = useSpeechRecognition({
    onTranscript: sendVoiceTranscript,
    enabled: browserSttEnabled,
    pauseWhilePlaying: isAudioPlaying,
  });

  const isListening = lkConnected
    ? !isMuted  // LiveKit: if mic is unmuted, we're "listening" (STT is server-side)
    : serverSttAvailable ? serverListening : browserListening;
  const sttSupported = lkConnected || serverSttAvailable || browserSttSupported;

  // Sync mic/camera state with LiveKit
  useEffect(() => {
    if (lkConnected) {
      lkSetMic(!isMuted);
    }
  }, [isMuted, lkConnected, lkSetMic]);

  useEffect(() => {
    if (lkConnected) {
      lkSetCamera(!isCameraOff);
    }
  }, [isCameraOff, lkConnected, lkSetCamera]);

  // Log STT state changes for debugging
  useEffect(() => {
    if (isMuted || !isConnected) return;
    if (lkConnected) {
      console.log("[STT] Using LiveKit WebRTC → server-side Deepgram STT");
    } else if (sttChecking) {
      console.log("[STT] Checking server STT availability...");
    } else if (serverSttAvailable) {
      console.log("[STT] Using Deepgram server STT (WebSocket)", { serverListening });
    } else if (browserSttSupported) {
      console.log("[STT] Using browser Speech Recognition", { browserListening });
    } else {
      console.warn("[STT] No STT available — use text chat");
    }
  }, [isMuted, isConnected, lkConnected, sttChecking, serverSttAvailable, browserSttSupported, serverListening, browserListening]);

  // Raven-inspired: detect user emotion from webcam (when camera is on)
  useEmotionDetection({
    apiUrl,
    enabled: !isCameraOff && isConnected,  // Works alongside LiveKit — separate getUserMedia stream
    intervalMs: 5000,
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
    let url = `${wsUrl}/ws/chat?agents=${agentIds}&user=${userName}`;
    if (meetingId) url += `&meeting_id=${encodeURIComponent(meetingId)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      // session_start message will provide the "Connected" system message
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "session_start") {
        // Parse LiveKit info from backend
        if (data.livekit?.enabled && data.livekit?.url && data.livekit?.room) {
          setLivekitUrl(data.livekit.url);
          setLivekitRoom(data.livekit.room);
          setLivekitEnabled(true);
          addSystemMessage("LiveKit WebRTC active — voice uses WebRTC.");
        }
        const agentCount = data.agents?.length || enabledAgents.length;
        addSystemMessage(`Connected, ${agentCount} variants ready.`);

      } else if (data.type === "user_transcript") {
        // Backend transcribed user speech via LiveKit → Deepgram
        setMessages((prev) => [
          ...prev,
          { id: `user-${++msgIdRef.current}`, type: "user", content: data.content, timestamp: Date.now() },
        ]);
        setIsThinking(true);

      } else if (data.type === "agent_typing") {
        setIsThinking(true);
        setThinkingAgent(data.variant || data.agent_id);

      } else if (data.type === "agent_stream_start") {
        // New streaming: create an empty message bubble that will be filled chunk-by-chunk
        setIsThinking(false);
        setThinkingAgent(null);
        setSpeakingAgentId(data.agent_id);
        const streamMsgId = `agent-stream-${data.agent_id}-${++msgIdRef.current}`;
        streamMsgIdRef.current = streamMsgId;
        setMessages((prev) => [
          ...prev,
          {
            id: streamMsgId,
            type: "agent",
            agentId: data.agent_id,
            variant: data.variant,
            content: "",
            timestamp: Date.now(),
          },
        ]);
        setUnreadCount((c) => c + 1);

      } else if (data.type === "agent_message_chunk") {
        // Append this sentence to the streaming message bubble
        const streamMsgId = streamMsgIdRef.current;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === streamMsgId
              ? { ...msg, content: msg.content ? msg.content + " " + data.content : data.content }
              : msg
          )
        );
        // Queue audio for this sentence (text + audio arrive together)
        if (data.audio) {
          enqueueAudio(data.audio, data.agent_id);
        }

      } else if (data.type === "agent_stream_end") {
        // Streaming complete — ensure full content is set
        const streamMsgId = streamMsgIdRef.current;
        if (data.full_content) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamMsgId ? { ...msg, content: data.full_content } : msg
            )
          );
        }
        streamMsgIdRef.current = null;

      } else if (data.type === "agent_message") {
        // Legacy: full text at once (fallback)
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

      } else if (data.type === "agent_audio_chunk") {
        // Token-streaming pipeline: audio arrives separately from text
        if (data.audio) {
          enqueueAudio(data.audio, data.agent_id);
        }
      } else if (data.type === "agent_audio") {
        // Legacy: full audio blob
        enqueueAudio(data.audio, data.agent_id);
      } else if (data.type === "agent_video") {
        console.log("[MeetingRoom] agent_video received for", data.agent_id, "size:", data.video?.length || 0, "chars");
        if (data.video) {
          setAgentVideos((prev) => ({
            ...prev,
            [data.agent_id]: data.video,
          }));
        }
      } else if (data.type === "chat_history") {
        // Rejoin: load past messages from backend
        const history: ChatMessage[] = (data.messages || []).map((m: any, i: number) => ({
          id: `history-${i}`,
          type: m.role === "user" ? "user" as const : "agent" as const,
          agentId: m.role === "user" ? undefined : m.role,
          variant: m.variant || m.role,
          content: m.content,
          timestamp: (m.timestamp || 0) * 1000,
        }));
        setMessages((prev) => [...history, ...prev]);
        addSystemMessage("Previous conversation loaded.");

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

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const handleFileUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file.size > 10 * 1024 * 1024) {
      addSystemMessage("File too large (max 10 MB).");
      return;
    }

    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/chat/upload`, { method: "POST", body: formData });
      const data = await res.json();
      if (data.ok) {
        setPendingFiles((prev) => [
          ...prev,
          {
            file_id: data.file_id,
            name: data.original_name,
            url: `${API_URL}${data.url}`,
            size: data.size,
            is_image: data.is_image,
            mime: data.mime,
          },
        ]);
      } else {
        addSystemMessage(`Upload failed: ${data.error || "Unknown error"}`);
      }
    } catch (err) {
      addSystemMessage(`Upload failed: ${err}`);
    }
    setUploadingFile(false);
  }, []);

  const removePendingFile = useCallback((fileId: string) => {
    setPendingFiles((prev) => prev.filter((f) => f.file_id !== fileId));
  }, []);

  const sendMessage = useCallback(() => {
    const text = chatInput.trim();
    const hasFiles = pendingFiles.length > 0;
    if ((!text && !hasFiles) || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const attachments = pendingFiles.map((f) => ({
      file_id: f.file_id,
      name: f.name,
      url: f.url,
      size: f.size,
      is_image: f.is_image,
      mime: f.mime,
    }));

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${++msgIdRef.current}`,
        type: "user",
        content: text,
        timestamp: Date.now(),
        attachments: attachments.length > 0 ? attachments : undefined,
      },
    ]);
    wsRef.current.send(JSON.stringify({ type: "chat", content: text, attachments }));
    setChatInput("");
    setPendingFiles([]);
    setIsThinking(true);
    chatInputRef.current?.focus();
  }, [chatInput, pendingFiles]);

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
    <div className="flex h-screen flex-col bg-gradient-to-br from-slate-50 via-white to-slate-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur-sm px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500 shadow-sm shadow-blue-200">
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-slate-800">The Multiverse of {identity}</h1>
            <p className="text-xs text-slate-400">
              {enabledAgents.length + 1} participants
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <div className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500" : "bg-amber-500 animate-pulse"}`} />
          <span className="text-slate-500">{isConnected ? (lkConnected ? "WebRTC" : "Connected") : "Connecting..."}</span>
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
              role={isListening ? "Listening..." : isMuted ? "Muted" : sttChecking ? "Setting up mic..." : browserSttError === "mic-denied" ? "Mic blocked — use chat" : browserSttError === "network" ? "Speech service error" : browserSttError ? "Mic error — use chat" : !sttSupported ? "Use chat to talk" : browserSttEnabled && !browserListening ? "Starting mic..." : "Mic ready"}
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
          <aside className="flex w-80 shrink-0 flex-col border-l border-slate-200 bg-white shadow-lg shadow-slate-200/30">
            {/* Chat header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <span className="text-sm font-semibold text-slate-800">Chat</span>
              <button
                onClick={() => setIsChatOpen(false)}
                className="text-slate-400 hover:text-slate-600"
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
                      <span className="text-[10px] text-slate-400">{msg.content}</span>
                    </div>
                  );
                }

                if (msg.type === "user") {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-xl rounded-br-sm bg-blue-500 px-3 py-2 shadow-sm shadow-blue-100">
                        {/* Attachments */}
                        {msg.attachments && msg.attachments.length > 0 && (
                          <div className="mb-1.5 space-y-1.5">
                            {msg.attachments.map((att) =>
                              att.is_image ? (
                                <img
                                  key={att.file_id}
                                  src={att.url}
                                  alt={att.name}
                                  className="max-h-40 rounded-lg border border-white/20 cursor-pointer"
                                  onClick={() => window.open(att.url, "_blank")}
                                />
                              ) : (
                                <a
                                  key={att.file_id}
                                  href={att.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center gap-1.5 rounded-lg bg-blue-600/60 px-2 py-1.5 text-[10px] text-white/90 hover:bg-blue-600"
                                >
                                  <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                                  </svg>
                                  <span className="truncate">{att.name}</span>
                                  <span className="shrink-0 text-white/50">({(att.size / 1024).toFixed(0)} KB)</span>
                                </a>
                              )
                            )}
                          </div>
                        )}
                        {msg.content && <p className="text-xs text-white">{msg.content}</p>}
                      </div>
                    </div>
                  );
                }

                const agent = getAgentInfo(msg.agentId);
                return (
                  <div key={msg.id} className="flex items-start gap-2">
                    <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${agent?.iconBg || "bg-slate-200"}`}>
                      <svg viewBox="0 0 80 80" className={`h-3.5 w-3.5 ${agent?.iconText || "text-slate-500"}`} fill="currentColor">
                        <circle cx="40" cy="28" r="14" />
                        <ellipse cx="40" cy="64" rx="24" ry="16" />
                      </svg>
                    </div>
                    <div className="max-w-[85%]">
                      <span className="text-[10px] font-semibold text-slate-500">{msg.variant}</span>
                      <div className="rounded-xl rounded-tl-sm bg-slate-100 px-3 py-2 shadow-sm">
                        <p className="text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    </div>
                  </div>
                );
              })}

              {isThinking && (
                <div className="flex items-center gap-2 px-2">
                  <div className="flex gap-1">
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: "0ms" }} />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: "150ms" }} />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span className="text-[10px] text-slate-400">
                    {thinkingAgent ? `${thinkingAgent} is typing...` : "Agents are thinking..."}
                  </span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Chat input */}
            <div className="border-t border-slate-200 p-3">
              {/* Pending file previews */}
              {pendingFiles.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {pendingFiles.map((f) => (
                    <div
                      key={f.file_id}
                      className="group relative flex items-center gap-1.5 rounded-lg bg-slate-100 px-2 py-1.5 text-[10px] text-slate-600 ring-1 ring-slate-200"
                    >
                      {f.is_image ? (
                        <img src={f.url} alt={f.name} className="h-8 w-8 rounded object-cover" />
                      ) : (
                        <svg className="h-4 w-4 shrink-0 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      )}
                      <span className="max-w-[100px] truncate">{f.name}</span>
                      <button
                        onClick={() => removePendingFile(f.file_id)}
                        className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-slate-300 text-[8px] text-white opacity-0 transition group-hover:opacity-100 hover:bg-red-500"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".txt,.md,.pdf,.docx,.csv,.json,.py,.js,.ts,.tsx,.jsx,.html,.css,.xml,.yaml,.yml,.log,.sh,.sql,.png,.jpg,.jpeg,.gif,.webp,.svg"
                  onChange={(e) => {
                    handleFileUpload(e.target.files);
                    e.target.value = "";
                  }}
                />

                {/* Paperclip / attach button */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!isConnected || uploadingFile}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 ring-1 ring-slate-200 transition hover:text-blue-600 hover:ring-blue-200 hover:bg-blue-50 disabled:opacity-30"
                  title="Attach a file"
                >
                  {uploadingFile ? (
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
                  ) : (
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                  )}
                </button>

                <input
                  ref={chatInputRef}
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  placeholder={pendingFiles.length > 0 ? "Add a message or just send..." : "Type a message..."}
                  disabled={!isConnected || isThinking}
                  className="flex-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-800 placeholder-slate-400 outline-none ring-1 ring-slate-200 focus:ring-blue-300 focus:bg-white disabled:opacity-50"
                />
                <button
                  onClick={sendMessage}
                  disabled={!isConnected || (!chatInput.trim() && pendingFiles.length === 0) || isThinking}
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500 text-white shadow-sm shadow-blue-200 disabled:opacity-30 hover:bg-blue-600"
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
        onToggleMute={() => {
          setIsMuted((m) => {
            const willBeUnmuted = !m;
            if (willBeUnmuted && !lkConnected && !serverSttAvailable && browserSttSupported) {
              // Directly start browser STT from user gesture context
              browserSttStart();
            }
            if (!willBeUnmuted) {
              browserSttStop();
            }
            return !m;
          });
        }}
        onToggleCamera={() => setIsCameraOff((c) => !c)}
        onToggleChat={() => { setIsChatOpen((o) => !o); setUnreadCount(0); }}
        onLeave={() => { stopAllAudio(); onLeave(); }}
        unreadCount={isChatOpen ? 0 : unreadCount}
      />
    </div>
  );
}

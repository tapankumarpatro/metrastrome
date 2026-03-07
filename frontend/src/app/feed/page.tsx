"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { fetchAgents, getAgentsCache, setAgentsCache } from "@/lib/agents";
import type { AgentInfo } from "@/lib/agents";
import { getProfile, isProfileComplete } from "@/lib/profile";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTimeAgo(unixSeconds: number): string {
  if (!unixSeconds) return "";
  const now = Date.now() / 1000;
  const diff = now - unixSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(unixSeconds * 1000).toLocaleDateString();
}

interface ChatMessage {
  role: string;
  variant: string;
  content: string;
  timestamp: number;
  isUser: boolean;
}

interface MeetingInfo {
  id: string;
  title: string;
  created_at: number;
  last_active: number;
  agents: { id: string; variant: string; emoji: string; image: string }[];
  agent_ids: string[];
  user_name: string;
  message_count: number;
  last_message: string;
}

export default function FeedPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentInfo[]>(getAgentsCache());
  const [loading, setLoading] = useState(agents.length === 0);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState<"meetings" | "chats">("meetings");
  const [meetings, setMeetings] = useState<MeetingInfo[]>([]);
  const [loadingMeetings, setLoadingMeetings] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isProfileComplete()) {
      router.replace("/settings");
      return;
    }
    if (agents.length > 0) return;
    fetchAgents().then((data) => {
      setAgents(data);
      setAgentsCache(data);
      setLoading(false);
    });
  }, [agents.length, router]);

  // Load meetings list
  useEffect(() => {
    if (activeTab !== "meetings") return;
    setLoadingMeetings(true);
    fetch(`${API_URL}/meetings?limit=30`)
      .then((r) => r.json())
      .then((data) => setMeetings(data.meetings || []))
      .catch(() => {})
      .finally(() => setLoadingMeetings(false));
  }, [activeTab]);

  const deleteMeeting = useCallback(async (id: string) => {
    if (!confirm("Delete this meeting and all its messages?")) return;
    await fetch(`${API_URL}/meetings/${id}`, { method: "DELETE" });
    setMeetings((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const rejoinMeeting = useCallback((meeting: MeetingInfo) => {
    const identity = meeting.user_name || getProfile().name || "user";
    const agentIds = meeting.agent_ids.join(",");
    router.push(
      `/meet?identity=${encodeURIComponent(identity)}&agents=${encodeURIComponent(agentIds)}&meeting_id=${encodeURIComponent(meeting.id)}`
    );
  }, [router]);

  // Load chat history when agent selected
  useEffect(() => {
    if (!selectedAgent) return;
    setLoadingHistory(true);
    setChatMessages([]);
    fetch(`${API_URL}/conversations/agent/${selectedAgent.id}?limit=30`)
      .then((r) => r.json())
      .then((data) => {
        const msgs: ChatMessage[] = (data.messages || []).map((m: any) => ({
          role: m.role,
          variant: m.variant || m.role,
          content: m.content,
          timestamp: m.timestamp * 1000,
          isUser: m.role === "user",
        }));
        setChatMessages(msgs);
      })
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, [selectedAgent]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const sendMessage = useCallback(async () => {
    if (!chatInput.trim() || !selectedAgent || sending) return;
    const text = chatInput.trim();
    setChatInput("");
    setSending(true);

    // Optimistic user message
    setChatMessages((prev) => [
      ...prev,
      {
        role: "user",
        variant: getProfile().name || "You",
        content: text,
        timestamp: Date.now(),
        isUser: true,
      },
    ]);

    try {
      const res = await fetch(`${API_URL}/chat/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: selectedAgent.id,
          message: text,
          user_name: getProfile().name,
        }),
      });
      const data = await res.json();
      if (data.reply) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: selectedAgent.id,
            variant: data.variant || selectedAgent.variant,
            content: data.reply,
            timestamp: Date.now(),
            isUser: false,
          },
        ]);
      } else if (data.error) {
        setChatMessages((prev) => [
          ...prev,
          {
            role: "system",
            variant: "System",
            content: `Error: ${data.error}`,
            timestamp: Date.now(),
            isUser: false,
          },
        ]);
      }
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "system",
          variant: "System",
          content: `Failed to send: ${err}`,
          timestamp: Date.now(),
          isUser: false,
        },
      ]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [chatInput, selectedAgent, sending]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50">
      {/* ── Left sidebar: Tabs + content ── */}
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-200 bg-white">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h1 className="text-lg font-bold text-slate-900">Messages</h1>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/")}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 transition"
            >
              Home
            </button>
            <button
              onClick={() => router.push("/settings")}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 transition"
            >
              Settings
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-100">
          <button
            onClick={() => { setActiveTab("meetings"); setSelectedAgent(null); }}
            className={`flex-1 py-2.5 text-xs font-semibold transition ${
              activeTab === "meetings"
                ? "text-blue-600 border-b-2 border-blue-600"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            Meetings
          </button>
          <button
            onClick={() => setActiveTab("chats")}
            className={`flex-1 py-2.5 text-xs font-semibold transition ${
              activeTab === "chats"
                ? "text-blue-600 border-b-2 border-blue-600"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            1-on-1 Chats
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {activeTab === "meetings" ? (
            <>
              {loadingMeetings && (
                <div className="flex justify-center py-8">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
                </div>
              )}
              {!loadingMeetings && meetings.length === 0 && (
                <div className="py-10 text-center">
                  <p className="text-sm text-slate-400">No meetings yet</p>
                  <p className="mt-1 text-xs text-slate-300">Start a meeting from the home page</p>
                </div>
              )}
              {meetings.map((meeting) => (
                <div
                  key={meeting.id}
                  className="group rounded-xl border border-slate-100 p-3 transition hover:bg-slate-50 hover:border-slate-200"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-800">
                        {meeting.title}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1.5">
                        {/* Agent avatars */}
                        <div className="flex -space-x-1.5">
                          {meeting.agents.slice(0, 4).map((a) => (
                            <div
                              key={a.id}
                              className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 ring-1 ring-white text-[9px]"
                              title={a.variant}
                            >
                              {a.image ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={a.image} alt={a.variant} className="h-5 w-5 rounded-full object-cover" />
                              ) : (
                                a.emoji || "🤖"
                              )}
                            </div>
                          ))}
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {meeting.message_count} msgs
                        </span>
                      </div>
                      {meeting.last_message && (
                        <p className="mt-1 truncate text-[11px] text-slate-400">
                          {meeting.last_message}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="text-[10px] text-slate-300">
                        {formatTimeAgo(meeting.last_active)}
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 flex gap-2 opacity-0 group-hover:opacity-100 transition">
                    <button
                      onClick={() => rejoinMeeting(meeting)}
                      className="flex-1 rounded-lg bg-blue-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-blue-700 transition"
                    >
                      Rejoin
                    </button>
                    <button
                      onClick={() => deleteMeeting(meeting.id)}
                      className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] text-slate-400 hover:border-red-200 hover:text-red-500 transition"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </>
          ) : (
            /* 1-on-1 agent chats list */
            agents.map((agent) => {
              const isActive = selectedAgent?.id === agent.id;
              return (
                <button
                  key={agent.id}
                  onClick={() => setSelectedAgent(agent)}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                    isActive
                      ? "bg-blue-50 ring-1 ring-blue-200"
                      : "hover:bg-slate-50"
                  }`}
                >
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${agent.iconBg}`}>
                    {agent.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={agent.image}
                        alt={agent.variant}
                        className="h-10 w-10 rounded-full object-cover"
                      />
                    ) : (
                      <span className="text-lg">{agent.emoji || "🤖"}</span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-slate-800">
                      {agent.variant}
                    </div>
                    <div className="truncate text-[11px] text-slate-400">
                      {agent.personality.split(",")[0]}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* ── Main chat area ── */}
      <main className="flex flex-1 flex-col">
        {selectedAgent ? (
          <>
            {/* Chat header */}
            <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-3">
              <div className={`flex h-9 w-9 items-center justify-center rounded-full ${selectedAgent.iconBg}`}>
                {selectedAgent.image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={selectedAgent.image}
                    alt={selectedAgent.variant}
                    className="h-9 w-9 rounded-full object-cover"
                  />
                ) : (
                  <span className="text-base">{selectedAgent.emoji || "🤖"}</span>
                )}
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-800">{selectedAgent.variant}</div>
                <div className="text-[11px] text-slate-400">{selectedAgent.personality.split(",")[0]}</div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
              {loadingHistory && (
                <div className="flex justify-center py-8">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
                </div>
              )}

              {!loadingHistory && chatMessages.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className={`flex h-16 w-16 items-center justify-center rounded-2xl ${selectedAgent.iconBg} mb-4`}>
                    <span className="text-3xl">{selectedAgent.emoji || "🤖"}</span>
                  </div>
                  <p className="text-sm font-medium text-slate-600">
                    Start a conversation with {selectedAgent.variant}
                  </p>
                  <p className="mt-1 text-xs text-slate-400 max-w-xs">
                    This is a 1-on-1 chat outside of meetings. {selectedAgent.variant} remembers your past conversations.
                  </p>
                </div>
              )}

              {chatMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.isUser ? "justify-end" : "justify-start"}`}
                >
                  {!msg.isUser && (
                    <div className={`mt-1 mr-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${selectedAgent.iconBg}`}>
                      <span className="text-xs">{selectedAgent.emoji || "🤖"}</span>
                    </div>
                  )}
                  <div
                    className={`max-w-[70%] rounded-2xl px-4 py-2.5 ${
                      msg.isUser
                        ? "rounded-br-md bg-blue-600 text-white"
                        : msg.role === "system"
                          ? "bg-red-50 text-red-600 border border-red-100"
                          : "rounded-bl-md bg-white text-slate-700 shadow-sm border border-slate-100"
                    }`}
                  >
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                    <p className={`mt-1 text-[10px] ${msg.isUser ? "text-blue-200" : "text-slate-300"}`}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex justify-start">
                  <div className={`mt-1 mr-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${selectedAgent.iconBg}`}>
                    <span className="text-xs">{selectedAgent.emoji || "🤖"}</span>
                  </div>
                  <div className="rounded-2xl rounded-bl-md bg-white px-4 py-3 shadow-sm border border-slate-100">
                    <div className="flex gap-1">
                      <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                      <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "150ms" }} />
                      <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-slate-200 bg-white px-6 py-3">
              <div className="flex gap-3">
                <input
                  ref={inputRef}
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  placeholder={`Message ${selectedAgent.variant}...`}
                  disabled={sending}
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 disabled:opacity-50"
                />
                <button
                  onClick={sendMessage}
                  disabled={!chatInput.trim() || sending}
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white transition hover:bg-blue-700 disabled:opacity-30"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                  </svg>
                </button>
              </div>
            </div>
          </>
        ) : (
          /* No agent/meeting selected */
          <div className="flex flex-1 flex-col items-center justify-center text-center">
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-slate-100 mb-4">
              {activeTab === "meetings" ? (
                <svg className="h-10 w-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                </svg>
              ) : (
                <svg className="h-10 w-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                </svg>
              )}
            </div>
            <h2 className="text-lg font-semibold text-slate-700">
              {activeTab === "meetings"
                ? "Select a meeting to rejoin"
                : "Select an agent to chat"}
            </h2>
            <p className="mt-1 text-sm text-slate-400 max-w-sm">
              {activeTab === "meetings"
                ? "Pick a past meeting from the sidebar to continue where you left off. All chat history is preserved."
                : "Pick any agent from the sidebar to start a 1-on-1 conversation. They remember your past meetings."}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

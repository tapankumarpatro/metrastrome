"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  fetchAgents,
  setAgentsCache,
  AgentInfo,
} from "@/lib/agents";
import { getProfile, isProfileComplete } from "@/lib/profile";

export default function Home() {
  const router = useRouter();
  const [profileName, setProfileName] = useState("");
  const [userName, setUserName] = useState("");
  const [isJoining, setIsJoining] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isProfileComplete()) {
      router.replace("/settings");
      return;
    }
    const p = getProfile();
    setProfileName(p.name);
    setUserName(p.name);

    fetchAgents().then((data) => {
      setAgents(data);
      setAgentsCache(data);
      // Auto-enable all agents on first load
      setEnabledAgents(new Set(data.map((a) => a.id)));
      setLoading(false);
    });
  }, [router]);

  const toggleAgent = (id: string) => {
    setEnabledAgents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleJoin = () => {
    if (!userName.trim() || enabledAgents.size === 0) return;
    setIsJoining(true);
    const displayName = userName.trim();
    const selected = Array.from(enabledAgents).join(",");
    router.push(
      `/meet?identity=${encodeURIComponent(displayName)}&agents=${encodeURIComponent(selected)}`
    );
  };

  const gridCols =
    agents.length <= 3 ? "grid-cols-3"
    : agents.length <= 4 ? "grid-cols-4"
    : agents.length <= 6 ? "grid-cols-3"
    : agents.length <= 8 ? "grid-cols-4"
    : agents.length <= 12 ? "grid-cols-4"
    : "grid-cols-5";

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gradient-to-br from-slate-50 via-white to-slate-100">
      {/* ── Header ── */}
      <header className="shrink-0 px-6 pt-5 pb-3">
        <div className="mx-auto max-w-[1400px] flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-800">
              The Multiverse of {profileName || "You"}
            </h1>
            <p className="mt-0.5 text-sm text-slate-400 font-light">
              Every variant is you — pick your team, then start talking.
            </p>
          </div>
          <div className="flex items-center gap-2.5 pb-1">
            <button
              onClick={() => router.push("/feed")}
              className="h-9 rounded-xl bg-white px-3.5 text-sm font-medium text-slate-500 shadow-sm shadow-slate-200/60 border border-slate-100 transition-all hover:shadow-md hover:shadow-slate-200/80 hover:text-slate-700 hover:-translate-y-px"
              title="Chat with agents 1-on-1"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="inline h-4 w-4 mr-1 -mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
              </svg>
              Messages
            </button>
            <button
              onClick={() => router.push("/settings")}
              className="h-9 rounded-xl bg-white px-3.5 text-sm font-medium text-slate-500 shadow-sm shadow-slate-200/60 border border-slate-100 transition-all hover:shadow-md hover:shadow-slate-200/80 hover:text-slate-700 hover:-translate-y-px"
              title="Settings — add or remove agents"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="inline h-4 w-4 mr-1 -mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
              </svg>
              Settings
            </button>
            <input
              type="text"
              placeholder="Your name..."
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleJoin()}
              className="h-9 w-48 rounded-xl bg-white px-3.5 text-sm text-slate-800 placeholder-slate-300 shadow-sm shadow-slate-200/60 border border-slate-100 outline-none transition-all focus:shadow-md focus:shadow-blue-100 focus:border-blue-200"
            />
            <button
              onClick={handleJoin}
              disabled={!userName.trim() || enabledAgents.size === 0 || isJoining}
              className="h-9 rounded-xl bg-gradient-to-r from-blue-500 to-blue-600 px-6 text-sm font-semibold text-white shadow-md shadow-blue-200/50 transition-all hover:shadow-lg hover:shadow-blue-300/60 hover:-translate-y-px active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              {isJoining ? "Joining..." : "Let's Talk"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Agent card grid ── */}
      <main className="flex-1 min-h-0 overflow-y-auto px-8 py-6">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-slate-400 animate-pulse">Loading agents from backend...</p>
          </div>
        ) : agents.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-slate-400">
              No agents found. Make sure the backend is running and agents.config.json exists.
            </p>
          </div>
        ) : (
          <div className={`mx-auto grid max-w-[1200px] gap-6 ${gridCols}`}>
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                isEnabled={enabledAgents.has(agent.id)}
                onToggle={() => toggleAgent(agent.id)}
                onChat={() => router.push(`/feed?agent=${agent.id}`)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

/* ── Agent profile card — white card, circular avatar, soft shadow ── */

function AgentCard({
  agent,
  isEnabled,
  onToggle,
  onChat,
}: {
  agent: AgentInfo;
  isEnabled: boolean;
  onToggle: () => void;
  onChat: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const hasImage = agent.image && !imgError;

  return (
    <div
      className={`group flex flex-col items-center rounded-xl bg-white px-5 pb-5 pt-7 transition-all duration-300 ease-out ${
        isEnabled
          ? "shadow-lg shadow-blue-100/60 ring-2 ring-blue-400/40 -translate-y-0.5"
          : "shadow-[0_2px_15px_-3px_rgba(0,0,0,0.07),0_10px_20px_-2px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_20px_-3px_rgba(0,0,0,0.1),0_12px_25px_-2px_rgba(0,0,0,0.06)] hover:-translate-y-1"
      }`}
    >
      {/* Clickable avatar area for selection */}
      <button onClick={onToggle} className="flex flex-col items-center focus:outline-none w-full">
        {/* Circular avatar with ring + status dot */}
        <div className="relative mb-4">
          <div className={`h-24 w-24 rounded-full p-[3px] ${
            isEnabled
              ? "bg-gradient-to-br from-blue-400 to-blue-500"
              : "bg-gradient-to-br from-slate-200 to-slate-300 group-hover:from-blue-300 group-hover:to-blue-400"
          } transition-all duration-300`}>
            <div className="flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-white">
              {hasImage ? (
                <img
                  src={agent.image}
                  alt={agent.variant}
                  className="h-full w-full rounded-full object-cover object-top"
                  loading="lazy"
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className={`flex h-full w-full items-center justify-center rounded-full ${agent.iconBg}`}>
                  <span className="text-4xl select-none">{agent.emoji || "🤖"}</span>
                </div>
              )}
            </div>
          </div>
          {/* Online / selected indicator dot */}
          <div className={`absolute right-0.5 top-0.5 h-5 w-5 rounded-full border-[2.5px] border-white transition-colors duration-300 ${
            isEnabled ? "bg-emerald-400" : "bg-slate-300 group-hover:bg-emerald-300"
          }`} />
        </div>

        {/* Name */}
        <h3 className="text-[15px] font-semibold text-slate-800 leading-tight text-center">
          {agent.variant}
        </h3>

        {/* Tagline / subtitle */}
        <p className="mt-0.5 text-xs text-slate-400 text-center truncate w-full">
          {agent.tagline}
        </p>

        {/* Role / expertise label */}
        <p className="mt-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-400">
          {agent.personality.split(",")[0].trim()}
        </p>
      </button>

      {/* Chat button */}
      <button
        onClick={(e) => { e.stopPropagation(); onChat(); }}
        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500 ring-1 ring-slate-200/80 transition-all hover:bg-blue-50 hover:text-blue-600 hover:ring-blue-200"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
        </svg>
        Chat
      </button>
    </div>
  );
}

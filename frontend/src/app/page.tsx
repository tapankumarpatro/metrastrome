"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  fetchAgents,
  setAgentsCache,
  DEFAULT_ENABLED_AGENTS,
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
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(
    new Set(DEFAULT_ENABLED_AGENTS)
  );

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
    const identity = userName.trim().toLowerCase().replace(/\s+/g, "-");
    const selected = Array.from(enabledAgents).join(",");
    router.push(
      `/meet?identity=${encodeURIComponent(identity)}&agents=${encodeURIComponent(selected)}`
    );
  };

  const gridCols =
    agents.length <= 3
      ? "grid-cols-3"
      : agents.length <= 4
        ? "grid-cols-4"
        : agents.length <= 6
          ? "grid-cols-3 grid-rows-2"
          : "grid-cols-4 grid-rows-2";

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      {/* ── Header ── */}
      <header className="shrink-0 px-6 pt-4 pb-2">
        <div className="mx-auto max-w-[1400px] flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              The Multiverse of {profileName || "You"}
            </h1>
            <p className="text-sm text-slate-400">
              Every variant is you — pick your team, then start talking.
            </p>
          </div>
          <div className="flex items-center gap-3 pb-1">
            <button
              onClick={() => router.push("/settings")}
              className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
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
              className="h-9 w-48 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500"
            />
            <button
              onClick={handleJoin}
              disabled={!userName.trim() || enabledAgents.size === 0 || isJoining}
              className="h-9 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white transition-all hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isJoining ? "Joining..." : "Let's Talk"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Agent card grid ── */}
      <main className="flex-1 min-h-0 px-6 py-3">
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
          <div className={`mx-auto grid h-full max-w-[1400px] gap-3 ${gridCols}`}>
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                isEnabled={enabledAgents.has(agent.id)}
                onToggle={() => toggleAgent(agent.id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

/* ── Agent card with photo or emoji fallback ── */

function AgentCard({
  agent,
  isEnabled,
  onToggle,
}: {
  agent: AgentInfo;
  isEnabled: boolean;
  onToggle: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const hasImage = agent.image && !imgError;

  return (
    <button
      onClick={onToggle}
      className={`group relative h-full w-full overflow-hidden focus:outline-none ${
        isEnabled ? "opacity-100" : "opacity-85 hover:opacity-100"
      }`}
    >
      {/* Photo or emoji fallback */}
      {hasImage ? (
        <img
          src={agent.image}
          alt={agent.variant}
          className="absolute inset-0 h-full w-full object-cover object-top"
          loading="lazy"
          onError={() => setImgError(true)}
        />
      ) : (
        <div className={`absolute inset-0 flex items-center justify-center ${agent.iconBg} bg-opacity-100`}>
          <span className="text-7xl select-none" style={{ filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.3))" }}>
            {agent.emoji || "🤖"}
          </span>
        </div>
      )}

      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/5 to-transparent" />

      {/* Selected indicator */}
      {isEnabled && (
        <div className="absolute right-2.5 top-2.5 h-3 w-3 rounded-full bg-blue-500 shadow-sm shadow-blue-500/50" />
      )}

      {/* Name overlaid */}
      <div className="absolute bottom-0 left-0 right-0 px-3 pb-3">
        <h3
          className="text-lg font-light uppercase leading-tight tracking-widest text-white"
          style={{ fontWeight: 300 }}
        >
          {agent.variant.replace("The ", "")}
        </h3>
        <p className="mt-0.5 text-[10px] text-white/60">
          {agent.personality.split(",")[0]}
        </p>
      </div>

      {/* Hover overlay */}
      <div className="absolute inset-0 flex flex-col justify-end bg-black/70 px-3 pb-3 pt-2 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        <h3
          className="text-lg font-light uppercase tracking-widest text-white"
          style={{ fontWeight: 300 }}
        >
          {agent.variant.replace("The ", "")}
        </h3>
        <p className={`mt-1 text-[10px] font-semibold uppercase tracking-wider ${agent.iconText}`}>
          {agent.personality.split(",")[0]}
        </p>
        <p className="mt-1.5 line-clamp-4 text-[11px] leading-relaxed text-white/80">
          {agent.backstory}
        </p>
        <p className="mt-1 text-[10px] italic text-white/50">
          {agent.tagline}
        </p>
      </div>
    </button>
  );
}

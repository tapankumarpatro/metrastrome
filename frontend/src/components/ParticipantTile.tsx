"use client";

import { useState } from "react";
import type { AgentInfo } from "@/lib/agents";

interface ParticipantTileProps {
  name: string;
  role: string;
  initials: string;
  isLocal: boolean;
  isSpeaking: boolean;
  isAgent: boolean;
  isConnected: boolean;
  iconBg: string;
  iconText: string;
  agentId?: string;
  agent?: AgentInfo;
  videoSrc?: string;
  onVideoComplete?: () => void;
}

export function ParticipantTile({
  name,
  role,
  isLocal,
  isSpeaking,
  isAgent,
  isConnected,
  iconBg,
  iconText,
  agent,
}: ParticipantTileProps) {
  const [imgError, setImgError] = useState(false);
  const hasImage = agent?.image && !imgError;

  return (
    <div
      className={`group relative flex aspect-video flex-col items-center justify-center overflow-hidden rounded-2xl transition-all duration-500 ${
        isSpeaking
          ? "ring-2 ring-emerald-500/80 shadow-xl shadow-emerald-500/25"
          : "ring-1 ring-zinc-800/80"
      } ${isLocal ? "bg-zinc-900" : "bg-zinc-900/80"}`}
    >
      {/* Agent photo background with speaking zoom effect */}
      {agent && hasImage && (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={agent.image}
            alt={agent.variant}
            className={`absolute inset-0 h-full w-full object-cover object-top transition-all duration-700 ease-out ${
              isSpeaking
                ? "scale-110 opacity-60"
                : "scale-100 opacity-40"
            }`}
            onError={() => setImgError(true)}
          />
          <div
            className={`absolute inset-0 transition-all duration-700 ${
              isSpeaking
                ? "bg-gradient-to-t from-zinc-900 via-zinc-900/40 to-transparent"
                : "bg-gradient-to-t from-zinc-900 via-zinc-900/60 to-transparent"
            }`}
          />
        </>
      )}

      {/* Emoji background when no image */}
      {agent && !hasImage && (
        <div className={`absolute inset-0 flex items-center justify-center ${agent.iconBg}`}>
          <span
            className={`select-none transition-all duration-500 ${
              isSpeaking ? "text-8xl scale-110" : "text-7xl scale-100 opacity-30"
            }`}
          >
            {agent.emoji || "🤖"}
          </span>
        </div>
      )}

      {/* Speaking glow ring pulse */}
      {isSpeaking && (
        <div className="pointer-events-none absolute inset-0 z-10">
          <div className="absolute inset-0 rounded-2xl ring-1 ring-emerald-400/30" style={{ animation: 'speakPulse 2s ease-in-out infinite' }} />
        </div>
      )}

      {/* Center content: avatar + info */}
      <div className="relative z-10 flex flex-col items-center">
        {agent ? (
          <div
            className={`relative transition-all duration-500 ${
              isSpeaking ? "scale-110" : "scale-100"
            }`}
          >
            {isSpeaking && (
              <div className="absolute -inset-2 rounded-full bg-emerald-500/20 blur-md" style={{ animation: 'speakPulse 2s ease-in-out infinite' }} />
            )}
            <div
              className={`relative h-16 w-16 overflow-hidden rounded-full transition-all duration-500 ${
                isSpeaking
                  ? "ring-2 ring-emerald-400/60"
                  : "ring-2 ring-white/20"
              }`}
            >
              {hasImage ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={agent.image}
                  alt={agent.variant}
                  className="h-full w-full object-cover object-top"
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className={`flex h-full w-full items-center justify-center ${agent.iconBg}`}>
                  <span className="text-2xl select-none">{agent.emoji || "🤖"}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div
            className={`flex h-16 w-16 items-center justify-center rounded-full ${iconBg}`}
          >
            <svg viewBox="0 0 80 80" className={`h-9 w-9 ${iconText}`} fill="currentColor">
              <circle cx="40" cy="28" r="14" />
              <ellipse cx="40" cy="64" rx="24" ry="16" />
            </svg>
          </div>
        )}

        {/* Name + role */}
        <div className="mt-2 flex flex-col items-center">
          <span className="text-sm font-medium text-white">{name}</span>
          <span className="text-[11px] text-zinc-400">{role}</span>
        </div>
      </div>

      {/* Audio visualizer bars (shown when speaking) */}
      {isSpeaking && (
        <div className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-end gap-[3px]">
          {[0.45, 0.55, 0.70, 0.50, 0.65, 0.40, 0.52].map((dur, i) => (
            <div
              key={i}
              className="w-[3px] rounded-full bg-emerald-400"
              style={{
                animation: `eqBar ${dur}s ease-in-out ${i * 0.08}s infinite alternate`,
                height: "4px",
              }}
            />
          ))}
        </div>
      )}

      {/* Connection status badge */}
      <div className="absolute left-3 top-3 z-10 flex items-center gap-1.5">
        <div
          className={`h-2 w-2 rounded-full ${
            isLocal
              ? isConnected ? "bg-emerald-500" : "bg-amber-500 animate-pulse"
              : isConnected ? "bg-emerald-500" : "bg-zinc-600"
          }`}
        />
        <span className="text-[10px] text-zinc-400">
          {isLocal
            ? isConnected ? "You" : "Connecting..."
            : isConnected ? "Live" : "Not joined yet"}
        </span>
      </div>

      {/* Role badge (top right) */}
      {isAgent && (
        <div
          className={`absolute right-3 top-3 z-10 rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${iconBg} ${iconText}`}
        >
          {role}
        </div>
      )}

    </div>
  );
}

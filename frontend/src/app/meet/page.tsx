"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useState, useEffect } from "react";
import { MeetingRoom } from "@/components/MeetingRoom";
import { fetchAgents, getAgentsCache, setAgentsCache } from "@/lib/agents";
import type { AgentInfo } from "@/lib/agents";
import { isProfileComplete } from "@/lib/profile";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

function MeetContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const identity = searchParams.get("identity");
  const agentsParam = searchParams.get("agents") || "";
  const meetingId = searchParams.get("meeting_id") || undefined;

  const [agents, setAgents] = useState<AgentInfo[]>(getAgentsCache());
  const [loading, setLoading] = useState(agents.length === 0);

  useEffect(() => {
    if (agents.length > 0) return;
    fetchAgents().then((data) => {
      setAgents(data);
      setAgentsCache(data);
      setLoading(false);
    });
  }, [agents.length]);

  if (!isProfileComplete()) {
    router.replace("/settings");
    return null;
  }

  if (!identity) {
    router.push("/");
    return null;
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
      </div>
    );
  }

  const enabledAgentIds = agentsParam.split(",").filter(Boolean);
  const enabledAgents = agents.filter((a) => enabledAgentIds.includes(a.id));

  return (
    <MeetingRoom
      wsUrl={WS_URL}
      identity={identity}
      enabledAgents={enabledAgents}
      onLeave={() => router.push("/")}
      meetingId={meetingId}
    />
  );
}

export default function MeetPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
        </div>
      }
    >
      <MeetContent />
    </Suspense>
  );
}

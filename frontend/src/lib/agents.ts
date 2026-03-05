export interface AgentInfo {
  id: string;
  variant: string;
  tagline: string;
  backstory: string;
  personality: string;
  iconBg: string;
  iconText: string;
  emoji: string;
  image: string;
  color: string;
  expertise: string[];
}

// ── Color → Tailwind class mapping ──────────────────────────────────
const COLOR_MAP: Record<string, { bg: string; text: string }> = {
  amber:   { bg: "bg-amber-600/20",   text: "text-amber-400" },
  violet:  { bg: "bg-violet-600/20",  text: "text-violet-400" },
  blue:    { bg: "bg-blue-600/20",    text: "text-blue-400" },
  emerald: { bg: "bg-emerald-600/20", text: "text-emerald-400" },
  rose:    { bg: "bg-rose-600/20",    text: "text-rose-400" },
  cyan:    { bg: "bg-cyan-600/20",    text: "text-cyan-400" },
  orange:  { bg: "bg-orange-600/20",  text: "text-orange-400" },
  pink:    { bg: "bg-pink-600/20",    text: "text-pink-400" },
  red:     { bg: "bg-red-600/20",     text: "text-red-400" },
  green:   { bg: "bg-green-600/20",   text: "text-green-400" },
  purple:  { bg: "bg-purple-600/20",  text: "text-purple-400" },
  yellow:  { bg: "bg-yellow-600/20",  text: "text-yellow-400" },
  teal:    { bg: "bg-teal-600/20",    text: "text-teal-400" },
  indigo:  { bg: "bg-indigo-600/20",  text: "text-indigo-400" },
  zinc:    { bg: "bg-zinc-600/20",    text: "text-zinc-400" },
};

function colorToClasses(color: string): { bg: string; text: string } {
  return COLOR_MAP[color] || COLOR_MAP.zinc;
}

// ── Transform API response to AgentInfo ─────────────────────────────
interface AgentApiResponse {
  id: string;
  variant: string;
  tagline: string;
  backstory: string;
  personality: string;
  emoji: string;
  color: string;
  image: string;
  expertise: string[];
  description?: string;
}

export function apiToAgentInfo(data: AgentApiResponse): AgentInfo {
  const colors = colorToClasses(data.color || "zinc");
  return {
    id: data.id,
    variant: data.variant,
    tagline: data.tagline || "",
    backstory: data.backstory || "",
    personality: data.personality || "",
    iconBg: colors.bg,
    iconText: colors.text,
    emoji: data.emoji || "🤖",
    image: data.image || "",
    color: data.color || "zinc",
    expertise: data.expertise || [],
  };
}

// ── Backend API URL ─────────────────────────────────────────────────
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchAgents(): Promise<AgentInfo[]> {
  try {
    const res = await fetch(`${API_URL}/agents`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: AgentApiResponse[] = await res.json();
    return data.map(apiToAgentInfo);
  } catch (err) {
    console.warn("[agents] Failed to fetch from backend, using empty list:", err);
    return [];
  }
}

// ── Static fallback (used until API loads) ──────────────────────────
// Mutable: set by the landing page after fetching
let _cachedAgents: AgentInfo[] = [];

export function setAgentsCache(agents: AgentInfo[]) {
  _cachedAgents = agents;
}

export function getAgentsCache(): AgentInfo[] {
  return _cachedAgents;
}

// Legacy export for components that import AGENTS directly
export const AGENTS: AgentInfo[] = _cachedAgents;

export const DEFAULT_ENABLED_AGENTS = [
  "tapan-architect",
  "tapan-builder",
  "tapan-strategist",
];

// ── Agent CRUD + AI generation ──────────────────────────────────────

export interface GenerateAgentRequest {
  name: string;
  agent_type: "variant" | "real_figure";
  context?: string;
  user_name?: string;
}

export interface AgentConfigData {
  id: string;
  agent_name: string;
  variant: string;
  tagline: string;
  emoji: string;
  color: string;
  personality: string;
  backstory: string;
  expertise: string[];
  description: string;
  voice: string;
  image: string;
  projects: {
    name: string;
    role: string;
    period: string;
    description: string;
    technologies: string[];
    outcome: string;
    lesson: string;
  }[];
}

export interface GenerationProgress {
  step: string;
  message: string;
}

export async function generateAgentConfigStream(
  req: GenerateAgentRequest,
  onProgress: (progress: GenerationProgress) => void,
): Promise<{ agent?: AgentConfigData; error?: string }> {
  try {
    const res = await fetch(`${API_URL}/agents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });

    if (!res.ok) {
      return { error: `HTTP ${res.status}` };
    }

    const reader = res.body?.getReader();
    if (!reader) return { error: "No response stream" };

    const decoder = new TextDecoder();
    let buffer = "";
    let result: { agent?: AgentConfigData; error?: string } = {};

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // keep incomplete line in buffer

      let eventType = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6);
          try {
            const parsed = JSON.parse(data);
            if (eventType === "progress") {
              onProgress(parsed as GenerationProgress);
            } else if (eventType === "result") {
              result = parsed;
            } else if (eventType === "error") {
              result = parsed;
            }
          } catch {
            // skip malformed JSON
          }
          eventType = "";
        }
      }
    }

    return result;
  } catch (err) {
    return { error: String(err) };
  }
}

export async function generateAgentConfig(
  req: GenerateAgentRequest
): Promise<{ agent?: AgentConfigData; error?: string }> {
  // Fallback non-streaming version
  return generateAgentConfigStream(req, () => {});
}

export async function addAgent(
  agent: AgentConfigData
): Promise<{ ok?: boolean; error?: string }> {
  try {
    const res = await fetch(`${API_URL}/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(agent),
    });
    return await res.json();
  } catch (err) {
    return { error: String(err) };
  }
}

export async function deleteAgent(
  agentId: string
): Promise<{ ok?: boolean; error?: string }> {
  try {
    const res = await fetch(`${API_URL}/agents/${agentId}`, {
      method: "DELETE",
    });
    return await res.json();
  } catch (err) {
    return { error: String(err) };
  }
}

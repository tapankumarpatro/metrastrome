"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  fetchAgents,
  setAgentsCache,
  generateAgentConfigStream,
  addAgent,
  deleteAgent,
  uploadAgentImage,
  regenerateAgentImage,
  AgentInfo,
  AgentConfigData,
  GenerationProgress,
} from "@/lib/agents";
import { getProfile, saveProfile, UserProfile } from "@/lib/profile";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const COLORS = [
  "amber", "violet", "blue", "emerald", "rose", "cyan",
  "orange", "pink", "red", "green", "purple", "yellow", "teal", "indigo",
];

const COLOR_DOTS: Record<string, string> = {
  amber: "bg-amber-400", violet: "bg-violet-400", blue: "bg-blue-400",
  emerald: "bg-emerald-400", rose: "bg-rose-400", cyan: "bg-cyan-400",
  orange: "bg-orange-400", pink: "bg-pink-400", red: "bg-red-400",
  green: "bg-green-400", purple: "bg-purple-400", yellow: "bg-yellow-400",
  teal: "bg-teal-400", indigo: "bg-indigo-400",
};

type Tab = "about" | "agents";

export default function SettingsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("about");
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  // ── About Me state ──
  const [profile, setProfile] = useState<UserProfile>({ name: "", bio: "", expertise: "", photo: "" });
  const [profileSaved, setProfileSaved] = useState(false);

  // "I want to talk to" form state
  const [nameInput, setNameInput] = useState("");
  const [agentType, setAgentType] = useState<"variant" | "real_figure">("variant");
  const [contextInput, setContextInput] = useState("");

  // AI generation state
  const [generating, setGenerating] = useState(false);
  const [generatingStep, setGeneratingStep] = useState("");
  const [progressLog, setProgressLog] = useState<GenerationProgress[]>([]);
  const [generated, setGenerated] = useState<AgentConfigData | null>(null);
  const [editMode, setEditMode] = useState(false);

  // Image editing state
  const [uploadingImage, setUploadingImage] = useState(false);
  const [regeneratingImage, setRegeneratingImage] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("");

  // Saving state
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Status messages
  const [status, setStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  // ── Load profile from localStorage on mount ──
  useEffect(() => {
    const p = getProfile();
    setProfile(p);
    // If profile already filled, default to agents tab
    if (p.name.trim()) setTab("agents");
  }, []);

  const loadAgents = useCallback(async () => {
    const data = await fetchAgents();
    setAgents(data);
    setAgentsCache(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  // Clear status after 4 seconds
  useEffect(() => {
    if (!status) return;
    const t = setTimeout(() => setStatus(null), 4000);
    return () => clearTimeout(t);
  }, [status]);

  // ── About Me handlers ──
  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setStatus({ type: "error", msg: "Please upload an image file." });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setStatus({ type: "error", msg: "Image must be under 5 MB." });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUri = reader.result as string;
      setProfile((prev) => ({ ...prev, photo: dataUri }));
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    if (!profile.name.trim()) {
      setStatus({ type: "error", msg: "Name is required." });
      return;
    }
    saveProfile(profile);

    // Upload reference photo to backend if present
    if (profile.photo) {
      try {
        await fetch(`${API_URL}/user/photo`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ photo: profile.photo }),
        });
      } catch (err) {
        console.warn("Failed to upload reference photo to backend:", err);
      }
    }

    setProfileSaved(true);
    setStatus({ type: "success", msg: "Profile saved!" });
    setTimeout(() => setProfileSaved(false), 2000);
  };

  const handleGenerate = async () => {
    if (!nameInput.trim()) return;
    setGenerating(true);
    setGenerated(null);
    setEditMode(false);
    setStatus(null);
    setProgressLog([]);
    setGeneratingStep("Starting...");

    // Ensure reference photo is uploaded before variant generation
    if (agentType === "variant" && profile.photo) {
      try {
        await fetch(`${API_URL}/user/photo`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ photo: profile.photo }),
        });
      } catch (err) {
        console.warn("Failed to upload reference photo:", err);
      }
    }

    const result = await generateAgentConfigStream(
      {
        name: nameInput.trim(),
        agent_type: agentType,
        context: contextInput.trim(),
        user_name: profile.name.trim(),
      },
      (progress) => {
        setGeneratingStep(progress.message);
        setProgressLog((prev) => {
          // Replace last entry if same step category, otherwise append
          const isUpdate =
            prev.length > 0 &&
            progress.step === "image_progress" &&
            prev[prev.length - 1].step === "image_progress";
          if (isUpdate) {
            return [...prev.slice(0, -1), progress];
          }
          return [...prev, progress];
        });
      },
    );

    if (result.error) {
      setStatus({ type: "error", msg: result.error });
    } else if (result.agent) {
      setGenerated(result.agent);
      setEditMode(true);
    }
    setGenerating(false);
    setGeneratingStep("");
  };

  const handleSave = async () => {
    if (!generated) return;
    setSaving(true);
    setStatus(null);

    const result = await addAgent(generated);
    if (result.error) {
      setStatus({ type: "error", msg: result.error });
    } else {
      setStatus({ type: "success", msg: `Added "${generated.variant}" to your team!` });
      setGenerated(null);
      setEditMode(false);
      setNameInput("");
      setContextInput("");
      await loadAgents();
    }
    setSaving(false);
  };

  const handleDelete = async (agentId: string) => {
    setDeletingId(agentId);
    setStatus(null);

    const result = await deleteAgent(agentId);
    if (result.error) {
      setStatus({ type: "error", msg: result.error });
    } else {
      setStatus({ type: "success", msg: `Removed agent.` });
      await loadAgents();
    }
    setDeletingId(null);
  };

  const updateGenField = (field: keyof AgentConfigData, value: unknown) => {
    if (!generated) return;
    setGenerated({ ...generated, [field]: value });
  };

  const userName = profile.name.trim() || "You";

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Header ── */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
              Settings
            </h1>
            <p className="text-xs text-slate-400">
              Set up your profile and manage your AI conversation partners
            </p>
          </div>
          <button
            onClick={() => {
              if (!profile.name.trim()) {
                setStatus({ type: "error", msg: "Please fill in your name in About Me before continuing." });
                setTab("about");
                return;
              }
              router.push("/");
            }}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
          >
            &larr; Back to Home
          </button>
        </div>
      </header>

      {/* ── Tabs ── */}
      <div className="mx-auto max-w-5xl px-6 pt-6">
        <div className="flex gap-1 border-b border-slate-200">
          <button
            onClick={() => setTab("about")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === "about"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            About Me
            {!profile.name.trim() && (
              <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-red-500" />
            )}
          </button>
          <button
            onClick={() => setTab("agents")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === "agents"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            Agents ({agents.length})
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6 py-8 space-y-10">
        {/* ── Status toast ── */}
        {status && (
          <div
            className={`rounded-lg px-4 py-3 text-sm font-medium ${
              status.type === "success"
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-red-50 text-red-700 border border-red-200"
            }`}
          >
            {status.msg}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════ */}
        {/* TAB: About Me                                                */}
        {/* ══════════════════════════════════════════════════════════════ */}
        {tab === "about" && (
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">About Me</h2>
            <p className="mt-1 text-sm text-slate-400">
              Tell us about yourself. Your name is used to personalize the multiverse
              experience. <span className="text-red-400">*</span> = required.
            </p>

            <div className="mt-5 space-y-4 max-w-lg">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Your Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Tapan, Sarah, Alex..."
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Short Bio
                </label>
                <textarea
                  placeholder="A few words about yourself — your background, what you do, what excites you..."
                  value={profile.bio}
                  onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
                  rows={3}
                  className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Areas of Expertise / Interest
                </label>
                <input
                  type="text"
                  placeholder="e.g. AI, product design, music production..."
                  value={profile.expertise}
                  onChange={(e) => setProfile({ ...profile, expertise: e.target.value })}
                  className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Reference Photo
                </label>
                <p className="mb-2 text-[11px] text-slate-400">
                  Upload your photo — it will be used as a reference when generating variant agent portraits.
                </p>
                <div className="flex items-center gap-4">
                  {profile.photo ? (
                    <div className="relative">
                      <img
                        src={profile.photo}
                        alt="Reference"
                        className="h-20 w-20 rounded-xl object-cover border border-slate-200 shadow-sm"
                      />
                      <button
                        onClick={() => setProfile((prev) => ({ ...prev, photo: "" }))}
                        className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white text-xs shadow hover:bg-red-600"
                        title="Remove photo"
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <label className="flex h-20 w-20 cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 text-slate-400 transition hover:border-blue-400 hover:text-blue-500">
                      <div className="text-center">
                        <svg className="mx-auto h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                        </svg>
                        <span className="text-[9px] font-medium">Upload</span>
                      </div>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handlePhotoUpload}
                      />
                    </label>
                  )}
                  {!profile.photo && (
                    <span className="text-xs text-slate-400">JPG or PNG, max 5 MB</span>
                  )}
                </div>
              </div>

              {/* Video mode info — server-controlled */}
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700">
                    Video Avatars
                  </label>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    Video call mode is controlled by the server based on GPU capabilities.
                    Run <code className="bg-slate-200 px-1 rounded text-[10px]">python check_gpu.py</code> in the backend folder and set <code className="bg-slate-200 px-1 rounded text-[10px]">USE_VIDEO_CALL=true</code> in .env if your GPU supports it (16+ GB VRAM).
                  </p>
                </div>
              </div>

              <button
                onClick={handleSaveProfile}
                className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-all hover:bg-blue-700"
              >
                {profileSaved ? "Saved ✓" : "Save Profile"}
              </button>
            </div>
          </section>
        )}

        {/* ══════════════════════════════════════════════════════════════ */}
        {/* TAB: Agents                                                  */}
        {/* ══════════════════════════════════════════════════════════════ */}
        {tab === "agents" && (
          <>
            {/* SECTION: "I want to talk to..." */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-900">
                I want to talk to&hellip;
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                Type a name or archetype and our AI will create a full backstory, expertise, personality, and a portrait photo for your new agent.
              </p>

              <div className="mt-5 grid gap-4 sm:grid-cols-[1fr_auto]">
                <div className="space-y-3">
                  <input
                    type="text"
                    placeholder='e.g. "Elon Musk", "The Chef", "Marie Curie", "The Philosopher"...'
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !generating && handleGenerate()}
                    className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  />

                  <div className="flex items-center gap-3">
                    <label className="text-xs font-medium text-slate-500">Create as:</label>
                    <select
                      value={agentType}
                      onChange={(e) => setAgentType(e.target.value as "variant" | "real_figure")}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 outline-none focus:border-blue-500"
                    >
                      <option value="variant">Variant of me ({userName} multiverse)</option>
                      <option value="real_figure">Real / fictional figure</option>
                    </select>
                  </div>

                  <textarea
                    placeholder="Optional: extra context or personality traits you want (e.g. 'Make them sarcastic and obsessed with Rust')"
                    value={contextInput}
                    onChange={(e) => setContextInput(e.target.value)}
                    rows={2}
                    className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                  />
                </div>

                <div className="flex items-start">
                  <button
                    onClick={handleGenerate}
                    disabled={!nameInput.trim() || generating}
                    className="whitespace-nowrap rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white transition-all hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {generating ? (
                      <span className="flex items-center gap-2">
                        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                        Generating...
                      </span>
                    ) : (
                      "Generate with AI"
                    )}
                  </button>
                </div>
              </div>

              {/* ── Live progress tracker ── */}
              {(generating || progressLog.length > 0) && !editMode && (
                <div className="mt-6 rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 p-5">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <svg className="h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Generation Progress
                  </h3>
                  <div className="space-y-2">
                    {progressLog.map((p, i) => {
                      const isLast = i === progressLog.length - 1;
                      const isDone = !isLast || !generating;
                      const isComplete = p.step === "complete";
                      return (
                        <div
                          key={`${p.step}-${i}`}
                          className={`flex items-start gap-2.5 text-sm transition-all duration-300 ${
                            isLast && generating ? "text-blue-700 font-medium" : "text-slate-500"
                          }`}
                        >
                          <span className="mt-0.5 flex-shrink-0">
                            {isComplete ? (
                              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                              </span>
                            ) : isDone ? (
                              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                              </span>
                            ) : (
                              <span className="inline-flex h-5 w-5 items-center justify-center">
                                <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                              </span>
                            )}
                          </span>
                          <span>{p.message}</span>
                        </div>
                      );
                    })}
                    {generating && progressLog.length === 0 && (
                      <div className="flex items-center gap-2.5 text-sm text-blue-600">
                        <span className="inline-flex h-5 w-5 items-center justify-center">
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                        </span>
                        <span>Connecting to AI...</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </section>

            {/* Generated agent preview / editor */}
            {editMode && generated && (
              <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-bold text-slate-900">
                    Preview &amp; Edit
                  </h2>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setGenerated(null); setEditMode(false); }}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                    >
                      Discard
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white transition-all hover:bg-emerald-700 disabled:opacity-40"
                    >
                      {saving ? "Saving..." : "Add to Team"}
                    </button>
                  </div>
                </div>

                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  {/* Left column: identity + image preview */}
                  <div className="space-y-3">
                    {/* Image preview + management */}
                    <div className="mb-3">
                      <label className="mb-1 block text-xs font-medium text-slate-500">Portrait</label>
                      <div className="flex items-start gap-3">
                        {generated.image ? (
                          <div className="relative">
                            <img
                              src={generated.image.startsWith("/images/") ? generated.image : `/images/${generated.image}`}
                              alt={generated.variant}
                              className="h-40 w-40 rounded-xl object-cover border border-slate-200 shadow-sm"
                            />
                            <button
                              onClick={() => updateGenField("image", "")}
                              className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white text-xs shadow hover:bg-red-600"
                              title="Remove image"
                            >
                              ×
                            </button>
                          </div>
                        ) : (
                          <div className="flex h-40 w-40 items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50">
                            <span className="text-5xl select-none">{generated.emoji || "🤖"}</span>
                          </div>
                        )}
                        <div className="flex flex-col gap-2">
                          {/* Upload custom image */}
                          <label className={`cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 text-center ${uploadingImage ? "opacity-50 pointer-events-none" : ""}`}>
                            {uploadingImage ? "Uploading..." : "Upload Image"}
                            <input
                              type="file"
                              accept="image/*"
                              className="hidden"
                              onChange={async (e) => {
                                const file = e.target.files?.[0];
                                if (!file) return;
                                if (file.size > 5 * 1024 * 1024) {
                                  setStatus({ type: "error", msg: "Image must be under 5 MB." });
                                  return;
                                }
                                setUploadingImage(true);
                                const reader = new FileReader();
                                reader.onload = async () => {
                                  const dataUri = reader.result as string;
                                  const result = await uploadAgentImage(generated.id, dataUri);
                                  if (result.image) {
                                    updateGenField("image", result.image);
                                  } else if (result.error) {
                                    setStatus({ type: "error", msg: result.error });
                                  }
                                  setUploadingImage(false);
                                };
                                reader.readAsDataURL(file);
                                e.target.value = "";
                              }}
                            />
                          </label>
                          {/* Regenerate with AI */}
                          <button
                            onClick={async () => {
                              const prompt = generated.image_prompt || imagePrompt;
                              if (!prompt) {
                                setStatus({ type: "error", msg: "No image prompt available. Enter one below." });
                                return;
                              }
                              setRegeneratingImage(true);
                              const result = await regenerateAgentImage(generated.id, prompt, agentType);
                              if (result.image) {
                                updateGenField("image", result.image);
                              } else if (result.error) {
                                setStatus({ type: "error", msg: result.error });
                              }
                              setRegeneratingImage(false);
                            }}
                            disabled={regeneratingImage}
                            className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:bg-blue-100 disabled:opacity-50"
                          >
                            {regeneratingImage ? (
                              <span className="flex items-center gap-1.5">
                                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                                Generating...
                              </span>
                            ) : "Regenerate Image"}
                          </button>
                        </div>
                      </div>
                      {/* Image prompt (editable) */}
                      {(generated.image_prompt || !generated.image) && (
                        <div className="mt-2">
                          <label className="mb-1 block text-[10px] font-medium text-slate-400">Image Prompt</label>
                          <textarea
                            value={generated.image_prompt || imagePrompt}
                            onChange={(e) => {
                              if (generated.image_prompt !== undefined) {
                                updateGenField("image_prompt", e.target.value);
                              } else {
                                setImagePrompt(e.target.value);
                              }
                            }}
                            rows={2}
                            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 placeholder-slate-400 outline-none focus:border-blue-500 resize-none"
                            placeholder="Describe the portrait you want generated..."
                          />
                        </div>
                      )}
                    </div>
                    <FieldInput label="Display Name" value={generated.variant}
                      onChange={(v) => updateGenField("variant", v)} />
                    <FieldInput label="ID (slug)" value={generated.id}
                      onChange={(v) => updateGenField("id", v)} />
                    <FieldInput label="Internal Name" value={generated.agent_name}
                      onChange={(v) => updateGenField("agent_name", v)} />
                    <FieldInput label="Tagline" value={generated.tagline}
                      onChange={(v) => updateGenField("tagline", v)} />
                    <FieldInput label="Personality (comma-separated)" value={generated.personality}
                      onChange={(v) => updateGenField("personality", v)} />

                    <div className="grid grid-cols-2 gap-3">
                      <FieldInput label="Emoji" value={generated.emoji}
                        onChange={(v) => updateGenField("emoji", v)} />
                      <div>
                        <label className="mb-1 block text-xs font-medium text-slate-500">Color</label>
                        <div className="flex flex-wrap gap-1.5">
                          {COLORS.map((c) => (
                            <button
                              key={c}
                              onClick={() => updateGenField("color", c)}
                              className={`h-6 w-6 rounded-full border-2 transition ${COLOR_DOTS[c]} ${
                                generated.color === c ? "border-slate-900 scale-110" : "border-transparent hover:border-slate-300"
                              }`}
                              title={c}
                            />
                          ))}
                        </div>
                      </div>
                    </div>

                    <FieldInput label="Expertise (comma-separated)"
                      value={generated.expertise.join(", ")}
                      onChange={(v) => updateGenField("expertise", v.split(",").map((s) => s.trim()).filter(Boolean))} />
                  </div>

                  {/* Right column: text areas */}
                  <div className="space-y-3">
                    <FieldTextarea label="Backstory" value={generated.backstory}
                      onChange={(v) => updateGenField("backstory", v)} rows={4} />
                    <FieldTextarea label="Description (for AI selector)" value={generated.description}
                      onChange={(v) => updateGenField("description", v)} rows={3} />

                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-500">
                        Projects ({generated.projects.length})
                      </label>
                      <div className="space-y-2">
                        {generated.projects.map((p, i) => (
                          <div key={i} className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
                            <span className="font-semibold text-slate-800">{p.name}</span>
                            {p.role && <span className="text-slate-400"> &middot; {p.role}</span>}
                            {p.period && <span className="text-slate-400"> &middot; {p.period}</span>}
                            <p className="mt-1">{p.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* Current agents list */}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-900">
                Your Agents
                <span className="ml-2 text-sm font-normal text-slate-400">
                  ({agents.length})
                </span>
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                These agents are available in your brainstorming sessions. Remove any you don&apos;t need.
              </p>

              {loading ? (
                <p className="mt-4 text-sm text-slate-400 animate-pulse">Loading...</p>
              ) : agents.length === 0 ? (
                <p className="mt-4 text-sm text-slate-400">
                  No agents yet. Use the form above to create your first one!
                </p>
              ) : (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {agents.map((agent) => (
                    <div
                      key={agent.id}
                      className="group relative flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/50 p-4 transition hover:border-slate-200 hover:bg-white"
                    >
                      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${agent.iconBg}`}>
                        {agent.image ? (
                          <img src={agent.image} alt="" className="h-11 w-11 rounded-full object-cover" />
                        ) : (
                          <span className="text-xl">{agent.emoji}</span>
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-semibold text-slate-800 truncate">
                          {agent.variant}
                        </h3>
                        <p className="text-[11px] text-slate-400 truncate">
                          {agent.personality.split(",")[0]}
                        </p>
                        <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-500">
                          {agent.tagline}
                        </p>
                      </div>

                      <button
                        onClick={() => handleDelete(agent.id)}
                        disabled={deletingId === agent.id}
                        className="absolute right-2 top-2 rounded-md p-1 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 disabled:opacity-50"
                        title="Remove agent"
                      >
                        {deletingId === agent.id ? (
                          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-red-400 border-t-transparent" />
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Reusable field components ── */

function FieldInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      />
    </div>
  );
}

function FieldTextarea({
  label,
  value,
  onChange,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
      />
    </div>
  );
}

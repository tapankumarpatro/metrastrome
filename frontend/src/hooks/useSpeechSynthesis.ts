"use client";

import { useRef, useCallback, useState, useEffect } from "react";

/* ── Browser Speech Synthesis (TTS) ── */

interface UseSpeechSynthesisOptions {
  enabled: boolean;
}

export function useSpeechSynthesis({ enabled }: UseSpeechSynthesisOptions) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentSpeaker, setCurrentSpeaker] = useState<string | null>(null);
  const voiceMapRef = useRef<Map<string, SpeechSynthesisVoice>>(new Map());
  const queueRef = useRef<Array<{ text: string; agentId: string }>>([]);
  const speakingRef = useRef(false);

  // Build a voice map — assign different voices to different agents
  useEffect(() => {
    function loadVoices() {
      const voices = speechSynthesis.getVoices();
      if (voices.length === 0) return;

      // Pick English voices, prefer different ones per agent
      const englishVoices = voices.filter(
        (v) => v.lang.startsWith("en") && !v.name.includes("Google")
      );
      const fallback = voices.find((v) => v.lang.startsWith("en")) || voices[0];

      // We'll assign voices round-robin
      voiceMapRef.current.set("__fallback__", fallback);
      voiceMapRef.current.set("__voices__", fallback); // placeholder

      // Store the full list for round-robin assignment
      (voiceMapRef.current as any).__allVoices = englishVoices.length > 0 ? englishVoices : [fallback];
    }

    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  const getVoiceForAgent = useCallback((agentId: string): SpeechSynthesisVoice | undefined => {
    if (voiceMapRef.current.has(agentId)) {
      return voiceMapRef.current.get(agentId);
    }

    const allVoices = (voiceMapRef.current as any).__allVoices as SpeechSynthesisVoice[] | undefined;
    if (!allVoices || allVoices.length === 0) return undefined;

    // Assign based on hash of agentId
    let hash = 0;
    for (let i = 0; i < agentId.length; i++) {
      hash = (hash * 31 + agentId.charCodeAt(i)) | 0;
    }
    const voice = allVoices[Math.abs(hash) % allVoices.length];
    voiceMapRef.current.set(agentId, voice);
    return voice;
  }, []);

  const processQueue = useCallback(() => {
    if (speakingRef.current || queueRef.current.length === 0) return;
    if (!enabled) {
      queueRef.current = [];
      return;
    }

    const next = queueRef.current.shift();
    if (!next) return;

    speakingRef.current = true;
    setIsSpeaking(true);
    setCurrentSpeaker(next.agentId);

    const utterance = new SpeechSynthesisUtterance(next.text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    const voice = getVoiceForAgent(next.agentId);
    if (voice) utterance.voice = voice;

    utterance.onend = () => {
      speakingRef.current = false;
      setIsSpeaking(false);
      setCurrentSpeaker(null);
      // Process next in queue
      processQueue();
    };

    utterance.onerror = () => {
      speakingRef.current = false;
      setIsSpeaking(false);
      setCurrentSpeaker(null);
      processQueue();
    };

    speechSynthesis.speak(utterance);
  }, [enabled, getVoiceForAgent]);

  const speak = useCallback(
    (text: string, agentId: string) => {
      if (!enabled) return;
      queueRef.current.push({ text, agentId });
      processQueue();
    },
    [enabled, processQueue]
  );

  const stop = useCallback(() => {
    speechSynthesis.cancel();
    queueRef.current = [];
    speakingRef.current = false;
    setIsSpeaking(false);
    setCurrentSpeaker(null);
  }, []);

  return { speak, stop, isSpeaking, currentSpeaker };
}

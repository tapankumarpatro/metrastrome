"use client";

import { useEffect, useRef, useCallback, useState } from "react";

/* ── Browser Speech Recognition (Chrome/Edge) ── */

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface UseSpeechRecognitionOptions {
  onTranscript: (text: string) => void;
  enabled: boolean;
  lang?: string;
  pauseWhilePlaying?: boolean;
}

export function useSpeechRecognition({
  onTranscript,
  enabled,
  lang = "en-US",
  pauseWhilePlaying = false,
}: UseSpeechRecognitionOptions) {
  const recognitionRef = useRef<any>(null);
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabledRef = useRef(enabled);
  const pauseRef = useRef(pauseWhilePlaying);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failCountRef = useRef(0);
  const startAttemptRef = useRef(false);
  enabledRef.current = enabled;
  pauseRef.current = pauseWhilePlaying;

  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    setIsSupported(!!SpeechRecognition);
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = lang;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const last = event.results[event.results.length - 1];
      if (last.isFinal) {
        const transcript = last[0].transcript.trim();
        if (transcript) {
          onTranscriptRef.current(transcript);
        }
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      // Auto-restart with a small delay if still enabled and not paused
      if (enabledRef.current && !pauseRef.current) {
        restartTimerRef.current = setTimeout(() => {
          try {
            recognition.start();
            setIsListening(true);
          } catch {
            // ignore — already started or not allowed
          }
        }, 300);
      }
    };

    recognition.onerror = (e: any) => {
      console.warn("[BrowserSTT] error:", e.error);
      failCountRef.current++;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        console.error("[BrowserSTT] Microphone permission denied");
        setError("mic-denied");
        setIsListening(false);
        return;
      }
      if (e.error === "network") {
        console.warn("[BrowserSTT] Network error — Google speech service unreachable");
        if (failCountRef.current > 3) {
          setError("network");
          setIsListening(false);
          return;
        }
      }
      // For "no-speech", "aborted" — let onend handle restart
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    // If a start was requested before recognition was ready, start now
    if (startAttemptRef.current && enabledRef.current && !pauseRef.current) {
      try {
        recognition.start();
        setIsListening(true);
        console.log("[BrowserSTT] Deferred start succeeded");
      } catch { /* will be handled by effect */ }
    }

    return () => {
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      try { recognition.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    };
  }, [lang]);

  // Start/stop based on enabled + pause props
  useEffect(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;

    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }

    const shouldListen = enabled && !pauseWhilePlaying;

    if (shouldListen) {
      failCountRef.current = 0;
      setError(null);
      // Small delay to avoid conflicts with audio playback ending
      const timer = setTimeout(() => {
        try {
          recognition.start();
          setIsListening(true);
          console.log("[BrowserSTT] Started listening");
        } catch (err: any) {
          // "already started" is harmless; other errors should be logged
          if (err?.message?.includes("already started")) {
            setIsListening(true);
          } else {
            console.warn("[BrowserSTT] Failed to start:", err?.message || err);
            setError("start-failed");
          }
        }
      }, 150);
      return () => clearTimeout(timer);
    } else {
      try {
        recognition.stop();
      } catch { /* ignore */ }
      setIsListening(false);
    }
  }, [enabled, pauseWhilePlaying]);

  // Imperative start — call from a user gesture (click handler) for reliable activation
  const requestStart = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      startAttemptRef.current = true; // Will start when recognition is ready
      console.log("[BrowserSTT] Recognition not ready yet, deferred");
      return;
    }
    try {
      recognition.start();
      setIsListening(true);
      setError(null);
      failCountRef.current = 0;
      console.log("[BrowserSTT] Imperative start succeeded");
    } catch (err: any) {
      if (err?.message?.includes("already started")) {
        setIsListening(true);
      } else {
        console.warn("[BrowserSTT] Imperative start failed:", err?.message || err);
        setError("start-failed");
      }
    }
  }, []);

  const requestStop = useCallback(() => {
    startAttemptRef.current = false;
    const recognition = recognitionRef.current;
    if (recognition) {
      try { recognition.stop(); } catch { /* ignore */ }
    }
    setIsListening(false);
  }, []);

  return { isListening, isSupported, error, requestStart, requestStop };
}

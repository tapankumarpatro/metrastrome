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
  const enabledRef = useRef(enabled);
  const pauseRef = useRef(pauseWhilePlaying);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
      console.warn("[SpeechRecognition] error:", e.error);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        console.error("Microphone permission denied — speech recognition disabled");
        setIsListening(false);
        return;
      }
      // For "no-speech", "aborted", "network" — let onend handle restart
      setIsListening(false);
    };

    recognitionRef.current = recognition;

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
      // Small delay to avoid conflicts with audio playback ending
      const timer = setTimeout(() => {
        try {
          recognition.start();
          setIsListening(true);
        } catch {
          // already started
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

  return { isListening, isSupported };
}

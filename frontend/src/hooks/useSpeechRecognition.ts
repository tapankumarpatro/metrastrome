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
}

export function useSpeechRecognition({
  onTranscript,
  enabled,
  lang = "en-US",
}: UseSpeechRecognitionOptions) {
  const recognitionRef = useRef<any>(null);
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

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

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const last = event.results[event.results.length - 1];
      if (last.isFinal) {
        const transcript = last[0].transcript.trim();
        if (transcript) {
          onTranscript(transcript);
        }
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      // Auto-restart if still enabled
      if (enabledRef.current) {
        try {
          recognition.start();
          setIsListening(true);
        } catch {
          // ignore — already started
        }
      }
    };

    recognition.onerror = (e: any) => {
      if (e.error === "not-allowed") {
        console.warn("Microphone permission denied");
      }
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      try { recognition.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    };
  }, [lang, onTranscript]);

  // Start/stop based on enabled prop
  useEffect(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;

    if (enabled) {
      try {
        recognition.start();
        setIsListening(true);
      } catch {
        // already started
      }
    } else {
      try {
        recognition.stop();
      } catch { /* ignore */ }
      setIsListening(false);
    }
  }, [enabled]);

  return { isListening, isSupported };
}

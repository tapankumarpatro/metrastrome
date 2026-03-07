"use client";

import { useEffect, useRef, useCallback, useState } from "react";

/**
 * Server-side Speech-to-Text via Deepgram (through backend /ws/stt).
 *
 * Captures microphone audio using Web Audio API, converts to linear16 PCM,
 * streams to backend WebSocket which forwards to Deepgram.
 * Returns real-time transcripts.
 *
 * Falls back gracefully if server STT is unavailable.
 */

interface UseServerSTTOptions {
  wsUrl: string; // e.g. "ws://localhost:8000"
  onTranscript: (text: string) => void;
  enabled: boolean;
  pauseWhilePlaying?: boolean;
}

export function useServerSTT({
  wsUrl,
  onTranscript,
  enabled,
  pauseWhilePlaying = false,
}: UseServerSTTOptions) {
  const [isListening, setIsListening] = useState(false);
  const [isAvailable, setIsAvailable] = useState<boolean | null>(null); // null = unknown
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const enabledRef = useRef(enabled);
  const pauseRef = useRef(pauseWhilePlaying);
  const onTranscriptRef = useRef(onTranscript);
  const interimRef = useRef("");

  enabledRef.current = enabled;
  pauseRef.current = pauseWhilePlaying;
  onTranscriptRef.current = onTranscript;

  const cleanup = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (contextRef.current && contextRef.current.state !== "closed") {
      contextRef.current.close().catch(() => {});
      contextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState <= 1) {
      try {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
    setIsListening(false);
  }, []);

  const startListening = useCallback(async () => {
    if (wsRef.current) return; // already active

    try {
      // 1. Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // 2. Connect to backend STT WebSocket
      const ws = new WebSocket(`${wsUrl}/ws/stt`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[ServerSTT] Connected to backend STT");
        setIsListening(true);

        // 3. Set up audio processing: capture PCM and send to backend
        const audioContext = new AudioContext({ sampleRate: 16000 });
        contextRef.current = audioContext;
        const source = audioContext.createMediaStreamSource(stream);

        // ScriptProcessorNode: buffer size 4096, 1 input channel, 1 output
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (e) => {
          if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
          const float32 = e.inputBuffer.getChannelData(0);
          // Convert float32 to int16 (linear16 PCM)
          const int16 = new Int16Array(float32.length);
          for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          wsRef.current.send(int16.buffer);
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "transcript") {
            if (data.speech_final && data.text) {
              // Final transcript for this utterance — send it
              const finalText = (interimRef.current + " " + data.text).trim();
              interimRef.current = "";
              onTranscriptRef.current(finalText);
            } else if (data.is_final && data.text) {
              // Sentence-level final — accumulate
              interimRef.current = (interimRef.current + " " + data.text).trim();
            }
          } else if (data.type === "error") {
            console.warn("[ServerSTT] Error:", data.message);
            setIsAvailable(false);
            cleanup();
          }
        } catch (e) {
          console.warn("[ServerSTT] Message parse error:", e);
        }
      };

      ws.onerror = () => {
        console.warn("[ServerSTT] WebSocket error");
        cleanup();
      };

      ws.onclose = () => {
        console.log("[ServerSTT] WebSocket closed");
        // Send any accumulated interim text
        if (interimRef.current.trim()) {
          onTranscriptRef.current(interimRef.current.trim());
          interimRef.current = "";
        }
        setIsListening(false);
        wsRef.current = null;
      };
    } catch (e) {
      console.error("[ServerSTT] Failed to start:", e);
      cleanup();
    }
  }, [wsUrl, cleanup]);

  // Check availability on mount via /system/capabilities
  useEffect(() => {
    const httpUrl = wsUrl.replace("ws://", "http://").replace("wss://", "https://");
    fetch(`${httpUrl}/system/capabilities`)
      .then((r) => r.json())
      .then((data) => {
        const hasStt = !!data?.stt?.server_side;
        setIsAvailable(hasStt);
        if (hasStt) console.log("[ServerSTT] Server-side STT available (Deepgram)");
        else console.log("[ServerSTT] Server-side STT not available, will use browser STT");
      })
      .catch(() => setIsAvailable(false));
  }, [wsUrl]);

  // Start/stop based on enabled + pause
  useEffect(() => {
    const shouldListen = enabled && !pauseWhilePlaying;

    if (shouldListen && isAvailable === true) {
      const timer = setTimeout(() => startListening(), 200);
      return () => clearTimeout(timer);
    } else {
      cleanup();
    }
  }, [enabled, pauseWhilePlaying, isAvailable, startListening, cleanup]);

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  return { isListening, isAvailable: isAvailable === true, isChecking: isAvailable === null };
}

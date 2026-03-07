"use client";

import { useEffect, useRef, useCallback, useState } from "react";

/**
 * Raven-inspired User Perception — Webcam emotion detection.
 *
 * Captures webcam frames periodically, sends to backend /perception/analyze,
 * returns detected emotional state. Agents use this to adapt responses.
 *
 * Only active when camera is on. Sends one frame every 5 seconds to
 * avoid excessive API calls.
 */

interface UseEmotionDetectionOptions {
  apiUrl: string; // e.g. "http://localhost:8000"
  enabled: boolean; // true when camera is on
  intervalMs?: number; // capture interval (default 5000ms)
}

interface EmotionState {
  emotion: string;
  engagement: string;
  brief: string;
}

export function useEmotionDetection({
  apiUrl,
  enabled,
  intervalMs = 5000,
}: UseEmotionDetectionOptions) {
  const [emotionState, setEmotionState] = useState<EmotionState>({
    emotion: "neutral",
    engagement: "medium",
    brief: "",
  });
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const captureAndAnalyze = useCallback(async () => {
    if (!enabledRef.current || !videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;

    // Only capture if video is playing
    if (video.readyState < 2) return;

    // Draw frame to canvas
    canvas.width = 320; // Low res for fast transfer
    canvas.height = 240;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, 320, 240);

    // Convert to base64 JPEG
    const dataUrl = canvas.toDataURL("image/jpeg", 0.6);
    const base64 = dataUrl.split(",")[1];

    try {
      const resp = await fetch(`${apiUrl}/perception/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: base64 }),
      });
      if (resp.ok) {
        const result = await resp.json();
        if (result.emotion && !result.cached) {
          setEmotionState(result);
        }
      }
    } catch (e) {
      // Silently fail — perception is optional
    }
  }, [apiUrl]);

  // Start/stop webcam capture
  useEffect(() => {
    if (!enabled) {
      // Cleanup
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      return;
    }

    // Create hidden video + canvas elements
    if (!videoRef.current) {
      const video = document.createElement("video");
      video.setAttribute("autoplay", "true");
      video.setAttribute("playsinline", "true");
      video.style.display = "none";
      document.body.appendChild(video);
      videoRef.current = video;
    }
    if (!canvasRef.current) {
      const canvas = document.createElement("canvas");
      canvas.style.display = "none";
      document.body.appendChild(canvas);
      canvasRef.current = canvas;
    }

    // Get webcam access
    navigator.mediaDevices
      .getUserMedia({ video: { width: 320, height: 240, facingMode: "user" } })
      .then((stream) => {
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        // Start periodic capture
        intervalRef.current = setInterval(captureAndAnalyze, intervalMs);
        console.log("[Perception] Emotion detection started");
      })
      .catch((e) => {
        console.warn("[Perception] Camera access denied:", e);
      });

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, intervalMs, captureAndAnalyze]);

  // Full cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      if (videoRef.current) {
        videoRef.current.remove();
        videoRef.current = null;
      }
      if (canvasRef.current) {
        canvasRef.current.remove();
        canvasRef.current = null;
      }
    };
  }, []);

  return { emotionState };
}

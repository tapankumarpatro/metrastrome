"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Room,
  RoomEvent,
  Track,
  ConnectionState,
  type RemoteTrack,
  type RemoteTrackPublication,
  type RemoteParticipant,
} from "livekit-client";

/**
 * LiveKit WebRTC room hook — connects to a LiveKit room for real-time A/V.
 *
 * When LiveKit is enabled (backend sends livekit info in session_start):
 *   - Publishes user mic + camera via WebRTC
 *   - Server participant subscribes to user audio → Deepgram STT
 *   - Agent audio still comes via WebSocket (base64 MP3)
 *
 * This gives us WebRTC echo cancellation, noise suppression, and
 * better audio quality for user input.
 */

interface UseLiveKitRoomOptions {
  livekitUrl: string | null;   // from session_start.livekit.url
  roomName: string | null;     // from session_start.livekit.room
  identity: string;
  enabled: boolean;            // true when livekit info is available
  apiUrl: string;              // http://localhost:8000
}

export function useLiveKitRoom({
  livekitUrl,
  roomName,
  identity,
  enabled,
  apiUrl,
}: UseLiveKitRoomOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionState, setConnectionState] = useState<string>("disconnected");
  const roomRef = useRef<Room | null>(null);
  const cleanupRef = useRef(false);

  // Connect to LiveKit room
  useEffect(() => {
    if (!enabled || !livekitUrl || !roomName) {
      return;
    }

    cleanupRef.current = false;
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
    });
    roomRef.current = room;

    room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
      setConnectionState(state);
      setIsConnected(state === ConnectionState.Connected);
      console.log(`[LiveKit] Connection state: ${state}`);
    });

    room.on(RoomEvent.Disconnected, () => {
      console.log("[LiveKit] Disconnected from room");
      setIsConnected(false);
    });

    room.on(
      RoomEvent.TrackSubscribed,
      (track: RemoteTrack, pub: RemoteTrackPublication, participant: RemoteParticipant) => {
        console.log(
          `[LiveKit] Subscribed to ${track.kind} track from ${participant.identity}`
        );
        // If server publishes audio tracks in the future, auto-play them
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          el.id = `lk-audio-${participant.identity}`;
          document.body.appendChild(el);
        }
      }
    );

    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      track.detach().forEach((el) => el.remove());
    });

    // Get token and connect
    const connectRoom = async () => {
      try {
        const resp = await fetch(
          `${apiUrl}/livekit/token?room=${encodeURIComponent(roomName)}&participant=${encodeURIComponent(identity)}`,
          { method: "POST" }
        );
        const data = await resp.json();
        if (cleanupRef.current || !data.token) {
          console.warn("[LiveKit] No token received or cleanup requested");
          return;
        }

        await room.connect(livekitUrl, data.token);
        console.log(`[LiveKit] Connected to room: ${roomName}`);
        // Mic and camera are controlled by MeetingRoom sync effects — don't auto-enable here
      } catch (e) {
        console.error("[LiveKit] Connection failed:", e);
      }
    };

    connectRoom();

    return () => {
      cleanupRef.current = true;
      room.disconnect();
      roomRef.current = null;
      setIsConnected(false);
      setConnectionState("disconnected");
    };
  }, [livekitUrl, roomName, identity, enabled, apiUrl]);

  const setMicEnabled = useCallback((on: boolean) => {
    roomRef.current?.localParticipant.setMicrophoneEnabled(on);
  }, []);

  const setCameraEnabled = useCallback((on: boolean) => {
    roomRef.current?.localParticipant.setCameraEnabled(on);
  }, []);

  return {
    isConnected,
    connectionState,
    setMicEnabled,
    setCameraEnabled,
    room: roomRef.current,
  };
}

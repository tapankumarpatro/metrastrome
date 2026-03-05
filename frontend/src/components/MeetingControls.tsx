"use client";

interface MeetingControlsProps {
  isMuted: boolean;
  isCameraOff: boolean;
  isChatOpen: boolean;
  onToggleMute: () => void;
  onToggleCamera: () => void;
  onToggleChat: () => void;
  onLeave: () => void;
  unreadCount?: number;
}

export function MeetingControls({
  isMuted,
  isCameraOff,
  isChatOpen,
  onToggleMute,
  onToggleCamera,
  onToggleChat,
  onLeave,
  unreadCount = 0,
}: MeetingControlsProps) {
  return (
    <footer className="flex items-center justify-center gap-3 border-t border-zinc-800 bg-zinc-950 px-6 py-4">
      {/* Mic */}
      <button
        onClick={onToggleMute}
        className={`flex h-12 w-12 items-center justify-center rounded-full transition-colors ${
          isMuted
            ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
            : "bg-zinc-800 text-white hover:bg-zinc-700"
        }`}
        title={isMuted ? "Unmute" : "Mute"}
      >
        {isMuted ? (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 19L5 5m14 0v4a2 2 0 01-2 2H7m0 0v2a5 5 0 0010 0v-2m-5 6v2m-3 0h6" />
          </svg>
        ) : (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
          </svg>
        )}
      </button>

      {/* Camera */}
      <button
        onClick={onToggleCamera}
        className={`flex h-12 w-12 items-center justify-center rounded-full transition-colors ${
          isCameraOff
            ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
            : "bg-zinc-800 text-white hover:bg-zinc-700"
        }`}
        title={isCameraOff ? "Turn on camera" : "Turn off camera"}
      >
        {isCameraOff ? (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M12 18.75H4.5a2.25 2.25 0 01-2.25-2.25V7.5A2.25 2.25 0 014.5 5.25H12M3 3l18 18" />
          </svg>
        ) : (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
          </svg>
        )}
      </button>

      {/* Chat toggle */}
      <button
        onClick={onToggleChat}
        className={`relative flex h-12 w-12 items-center justify-center rounded-full transition-colors ${
          isChatOpen
            ? "bg-violet-600 text-white hover:bg-violet-500"
            : "bg-zinc-800 text-white hover:bg-zinc-700"
        }`}
        title="Toggle chat"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
        </svg>
        {unreadCount > 0 && (
          <div className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </div>
        )}
      </button>

      {/* Leave */}
      <button
        onClick={onLeave}
        className="ml-4 flex h-12 items-center gap-2 rounded-full bg-red-600 px-6 font-medium text-white transition-colors hover:bg-red-500"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
        </svg>
        Leave
      </button>
    </footer>
  );
}

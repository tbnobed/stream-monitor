import React, { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { VolumeX, Volume2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface WebRtcPlayerProps {
  streamKey: string;
  webrtcUrl?: string | null;
  className?: string;
}

declare global {
  interface Window {
    SrsRtcWhipWhepAsync: any;
  }
}

export function WebRtcPlayer({ streamKey, webrtcUrl, className }: WebRtcPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);
  const runIdRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [muted, setMuted] = useState(true);
  const [error, setError] = useState(false);

  const closePlayer = () => {
    if (playerRef.current) {
      try { playerRef.current.close(); } catch (e) {}
      playerRef.current = null;
    }
  };

  const attemptPlay = async () => {
    if (!videoRef.current) return;
    closePlayer();

    const player = new window.SrsRtcWhipWhepAsync();
    playerRef.current = player;
    videoRef.current.srcObject = player.stream;

    const url = webrtcUrl || `/api/proxy/whep/?stream=${streamKey}`;
    await player.play(url);

    if (videoRef.current) {
      videoRef.current.play().catch(() => {});
    }
  };

  const initPlayer = async () => {
    if (!videoRef.current || !streamKey || !window.SrsRtcWhipWhepAsync) return;

    const runId = ++runIdRef.current;
    const isStale = () => runId !== runIdRef.current;

    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    closePlayer();
    setError(false);

    const maxAttempts = 4;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      if (isStale()) return;
      try {
        await attemptPlay();
        if (isStale()) closePlayer();
        return;
      } catch (err) {
        console.error(`WHEP play attempt ${attempt}/${maxAttempts} failed`, err);
        if (isStale()) return;
        if (attempt < maxAttempts) {
          await new Promise((r) => { timerRef.current = setTimeout(r, attempt * 1500); });
        }
      }
    }

    if (!isStale()) {
      closePlayer();
      setError(true);
    }
  };

  useEffect(() => {
    initPlayer();

    return () => {
      runIdRef.current++;
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
      closePlayer();
    };
  }, [streamKey, webrtcUrl]);

  return (
    <div className={cn("relative group bg-black overflow-hidden rounded-md flex items-center justify-center", className)}>
      <video 
        ref={videoRef}
        autoPlay
        playsInline
        muted={muted}
        className="w-full h-full object-contain"
      />
      
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white p-4 text-center">
          <p className="text-sm font-medium mb-2 text-status-down">Stream Disconnected</p>
          <Button size="sm" variant="outline" onClick={initPlayer} className="bg-transparent text-white border-white/20 hover:bg-white/10">
            <RefreshCw className="h-3 w-3 mr-2" /> Reconnect
          </Button>
        </div>
      )}
      
      <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button 
          size="icon" 
          variant="secondary" 
          className="h-7 w-7 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm"
          onClick={() => setMuted(!muted)}
        >
          {muted ? <VolumeX className="h-3 w-3" /> : <Volume2 className="h-3 w-3" />}
        </Button>
      </div>
    </div>
  );
}

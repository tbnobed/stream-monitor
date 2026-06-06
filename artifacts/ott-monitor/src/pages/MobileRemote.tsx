import { useEffect, useRef, useState } from 'react';
import {
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
  CornerUpLeft, Home, Menu, Play, Rewind, FastForward,
  Volume2, Volume1, VolumeX, Power, Loader2, Wifi, WifiOff, Smartphone,
} from 'lucide-react';
import {
  getMobileSession,
  sendMobileKey,
  MobileRemoteError,
  type MobileRemoteSession,
} from '@/lib/mobile-remote';
import { cn } from '@/lib/utils';

interface MobileRemoteProps {
  token: string;
}

export default function MobileRemote({ token }: MobileRemoteProps) {
  const [session, setSession] = useState<MobileRemoteSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ key: string; ok: boolean } | null>(null);
  const flashTimer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getMobileSession(token)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        setLoadError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof MobileRemoteError && e.status === 404) setExpired(true);
        else setLoadError(e instanceof Error ? e.message : 'Could not load remote.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const supported = new Set(session?.keys ?? []);
  const has = (key: string) => supported.has(key);

  const showFlash = (key: string, ok: boolean) => {
    setFlash({ key, ok });
    if (flashTimer.current) window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setFlash(null), 900);
  };

  const press = (key: string) => {
    if (navigator.vibrate) navigator.vibrate(10);
    sendMobileKey(token, key)
      .then(() => showFlash(key, true))
      .catch((e: unknown) => {
        if (e instanceof MobileRemoteError && e.status === 404) {
          setExpired(true);
          return;
        }
        showFlash(key, false);
      });
  };

  if (loading) {
    return (
      <Shell>
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Connecting…
        </div>
      </Shell>
    );
  }

  if (expired) {
    return (
      <Shell>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <Smartphone className="h-10 w-10 text-muted-foreground" />
          <h1 className="text-lg font-semibold">Remote link expired</h1>
          <p className="text-sm text-muted-foreground">
            This one-time link is no longer active. On your computer, open the
            device window again and scan the new QR code.
          </p>
        </div>
      </Shell>
    );
  }

  if (loadError || !session) {
    return (
      <Shell>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <WifiOff className="h-10 w-10 text-status-down" />
          <h1 className="text-lg font-semibold">Couldn’t load remote</h1>
          <p className="text-sm text-muted-foreground">{loadError || 'Unknown error.'}</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold">{session.device_name}</div>
          <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            {session.platform || '—'} · {session.protocol || '—'}
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          {session.reachable ? (
            <Wifi className="h-4 w-4 text-status-healthy" />
          ) : (
            <WifiOff className="h-4 w-4 text-status-down" />
          )}
          <span className="text-muted-foreground">
            {session.reachable ? 'online' : 'offline'}
          </span>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-1 flex-col justify-center gap-6 px-5 py-6">
        {/* D-pad */}
        <div className="mx-auto grid w-full max-w-xs grid-cols-3 grid-rows-3 gap-2">
          <span />
          <TapKey active={flash} keyName="up" icon={ChevronUp} label="Up" has={has} onPress={press} />
          <span />
          <TapKey active={flash} keyName="left" icon={ChevronLeft} label="Left" has={has} onPress={press} />
          <CenterKey active={flash} has={has} onPress={press} />
          <TapKey active={flash} keyName="right" icon={ChevronRight} label="Right" has={has} onPress={press} />
          <span />
          <TapKey active={flash} keyName="down" icon={ChevronDown} label="Down" has={has} onPress={press} />
          <span />
        </div>

        {/* Nav */}
        <div className="mx-auto grid w-full max-w-xs grid-cols-4 gap-2">
          <TapKey active={flash} keyName="back" icon={CornerUpLeft} label="Back" has={has} onPress={press} />
          <TapKey active={flash} keyName="home" icon={Home} label="Home" has={has} onPress={press} />
          <TapKey active={flash} keyName="menu" icon={Menu} label="Menu" has={has} onPress={press} />
          <TapKey active={flash} keyName="power" icon={Power} label="Power" has={has} onPress={press} />
        </div>

        {/* Transport */}
        <div className="mx-auto grid w-full max-w-xs grid-cols-3 gap-2">
          <TapKey active={flash} keyName="rewind" icon={Rewind} label="Rewind" has={has} onPress={press} />
          <TapKey active={flash} keyName="play_pause" icon={Play} label="Play / Pause" has={has} onPress={press} />
          <TapKey active={flash} keyName="forward" icon={FastForward} label="Forward" has={has} onPress={press} />
        </div>

        {/* Volume */}
        <div className="mx-auto grid w-full max-w-xs grid-cols-3 gap-2">
          <TapKey active={flash} keyName="volume_down" icon={Volume1} label="Volume Down" has={has} onPress={press} />
          <TapKey active={flash} keyName="mute" icon={VolumeX} label="Mute" has={has} onPress={press} />
          <TapKey active={flash} keyName="volume_up" icon={Volume2} label="Volume Up" has={has} onPress={press} />
        </div>
      </div>

      <div className="px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 text-center text-[11px] text-muted-foreground">
        Tap to control. This link expires when the device window is closed on the wall.
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[100dvh] flex-col bg-background text-foreground select-none">
      {children}
    </div>
  );
}

function keyClasses(active: { key: string; ok: boolean } | null, keyName: string) {
  if (active?.key !== keyName) return 'border-border bg-secondary/40';
  return active.ok
    ? 'border-status-healthy bg-status-healthy/20'
    : 'border-status-down bg-status-down/20';
}

function TapKey({
  keyName,
  icon: Icon,
  label,
  has,
  onPress,
  active,
}: {
  keyName: string;
  icon: React.ElementType;
  label: string;
  has: (k: string) => boolean;
  onPress: (k: string) => void;
  active: { key: string; ok: boolean } | null;
}) {
  if (!has(keyName)) return <span />;
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => onPress(keyName)}
      className={cn(
        'flex h-16 items-center justify-center rounded-xl border transition-transform active:scale-95',
        keyClasses(active, keyName),
      )}
    >
      <Icon className="h-7 w-7" />
    </button>
  );
}

function CenterKey({
  has,
  onPress,
  active,
}: {
  has: (k: string) => boolean;
  onPress: (k: string) => void;
  active: { key: string; ok: boolean } | null;
}) {
  if (!has('select')) return <span />;
  return (
    <button
      type="button"
      aria-label="OK / Select"
      onClick={() => onPress('select')}
      className={cn(
        'flex h-16 items-center justify-center rounded-full border-2 text-lg font-bold transition-transform active:scale-95',
        active?.key === 'select'
          ? active.ok
            ? 'border-status-healthy bg-status-healthy/20'
            : 'border-status-down bg-status-down/20'
          : 'border-primary bg-primary text-primary-foreground',
      )}
    >
      OK
    </button>
  );
}

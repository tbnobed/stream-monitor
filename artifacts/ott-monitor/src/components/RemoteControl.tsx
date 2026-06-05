import React, { useState } from 'react';
import {
  useGetRemoteStatus,
  useGetRemoteCapabilities,
  useSendRemoteKey,
  useLaunchRemoteApp,
  useBeginRemotePairing,
  useFinishRemotePairing,
  getGetRemoteStatusQueryKey,
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/use-toast';
import {
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
  CornerUpLeft, Home, Menu, Play, Rewind, FastForward,
  Volume2, Volume1, VolumeX, Power, RefreshCw, Loader2,
  Wifi, WifiOff, Link2, AppWindow,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface RemoteControlProps {
  deviceId: number;
}

export function RemoteControl({ deviceId }: RemoteControlProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [pin, setPin] = useState('');
  const [pairStarted, setPairStarted] = useState(false);
  const [pairNeedsPin, setPairNeedsPin] = useState(false);

  const {
    data: status,
    isLoading: statusLoading,
    refetch: refetchStatus,
    isRefetching,
  } = useGetRemoteStatus(deviceId);
  const { data: caps } = useGetRemoteCapabilities(deviceId);

  const sendKey = useSendRemoteKey();
  const launchApp = useLaunchRemoteApp();
  const beginPair = useBeginRemotePairing();
  const finishPair = useFinishRemotePairing();

  const refreshStatus = () => {
    queryClient.invalidateQueries({ queryKey: getGetRemoteStatusQueryKey(deviceId) });
    refetchStatus();
  };

  const supportedKeys = new Set(caps?.keys ?? []);
  const has = (key: string) => supportedKeys.has(key);

  const press = (key: string) => {
    sendKey.mutate(
      { id: deviceId, data: { key } },
      {
        onError: (err: any) => {
          toast({
            variant: 'destructive',
            title: 'Key failed',
            description: err?.data?.detail || err?.message || `Could not send "${key}".`,
          });
        },
      }
    );
  };

  const launch = (appId: string, name: string) => {
    launchApp.mutate(
      { id: deviceId, data: { app_id: appId } },
      {
        onSuccess: () => toast({ title: `Launched ${name}` }),
        onError: (err: any) =>
          toast({
            variant: 'destructive',
            title: 'Launch failed',
            description: err?.data?.detail || err?.message || `Could not launch ${name}.`,
          }),
      }
    );
  };

  const startPairing = () => {
    beginPair.mutate(
      { id: deviceId },
      {
        onSuccess: (res) => {
          setPairStarted(true);
          setPairNeedsPin(res.requires_pin);
          toast({ title: 'Pairing started', description: res.message });
          if (!res.requires_pin) {
            completePairing();
          }
        },
        onError: (err: any) =>
          toast({
            variant: 'destructive',
            title: 'Pairing failed',
            description: err?.data?.detail || err?.message || 'Could not begin pairing.',
          }),
      }
    );
  };

  const completePairing = () => {
    finishPair.mutate(
      { id: deviceId, data: { pin: pin || null } },
      {
        onSuccess: () => {
          setPin('');
          setPairStarted(false);
          setPairNeedsPin(false);
          refreshStatus();
          toast({ title: 'Paired successfully' });
        },
        onError: (err: any) =>
          toast({
            variant: 'destructive',
            title: 'Pairing failed',
            description: err?.data?.detail || err?.message || 'Could not complete pairing.',
          }),
      }
    );
  };

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Checking remote…
      </div>
    );
  }

  if (status && !status.capable) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Native remote control is not supported for this platform.
      </div>
    );
  }

  const needsPairing = !!status?.requires_pairing && !status?.paired;
  const noIp = !status?.reachable && /ip address/i.test(status?.detail || '');

  const StatusHeader = (
    <div className="flex items-center justify-between gap-2 rounded-md border bg-secondary/30 px-3 py-2 text-xs">
      <div className="flex items-center gap-2 min-w-0">
        {status?.reachable ? (
          <Wifi className="h-4 w-4 text-status-healthy shrink-0" />
        ) : (
          <WifiOff className="h-4 w-4 text-status-down shrink-0" />
        )}
        <span className="uppercase font-mono tracking-wider text-muted-foreground shrink-0">
          {status?.protocol || '—'}
        </span>
        {status?.paired && (
          <span className="flex items-center gap-1 text-status-healthy shrink-0">
            <Link2 className="h-3 w-3" /> paired
          </span>
        )}
        {status?.detail && (
          <span className="truncate text-muted-foreground" title={status.detail}>
            · {status.detail}
          </span>
        )}
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0"
        onClick={refreshStatus}
        disabled={isRefetching}
      >
        <RefreshCw className={cn('h-3.5 w-3.5', isRefetching && 'animate-spin')} />
      </Button>
    </div>
  );

  if (noIp) {
    return (
      <div className="space-y-3">
        {StatusHeader}
        <div className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
          No IP address configured for this device. Add the device's LAN IP in the
          Device Registry to enable native remote control.
        </div>
      </div>
    );
  }

  if (needsPairing) {
    return (
      <div className="space-y-3">
        {StatusHeader}
        <div className="rounded-md border p-4 space-y-3">
          <div className="text-sm font-medium">Pairing required</div>
          <p className="text-xs text-muted-foreground">
            {caps?.protocol === 'adb'
              ? 'Click Begin Pairing, then accept the "Allow USB/Network debugging" prompt on the TV.'
              : 'Click Begin Pairing — a PIN will appear on the TV screen. Enter it below to finish.'}
          </p>
          {!pairStarted ? (
            <Button onClick={startPairing} disabled={beginPair.isPending} className="w-full">
              {beginPair.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Begin Pairing
            </Button>
          ) : (
            <div className="space-y-2">
              {pairNeedsPin && (
                <Input
                  autoFocus
                  placeholder="Enter PIN from TV"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  className="text-center font-mono tracking-widest"
                />
              )}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setPairStarted(false);
                    setPairNeedsPin(false);
                    setPin('');
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={completePairing}
                  disabled={finishPair.isPending || (pairNeedsPin && !pin)}
                >
                  {finishPair.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Complete
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  const PadButton = ({
    keyName,
    icon: Icon,
    label,
    className,
  }: {
    keyName: string;
    icon: React.ElementType;
    label: string;
    className?: string;
  }) =>
    has(keyName) ? (
      <Button
        variant="outline"
        size="icon"
        className={cn('h-11 w-11', className)}
        onClick={() => press(keyName)}
        title={label}
        aria-label={label}
      >
        <Icon className="h-5 w-5" />
      </Button>
    ) : (
      <div className="h-11 w-11" />
    );

  return (
    <div className="space-y-4">
      {StatusHeader}

      {/* D-pad */}
      <div className="flex flex-col items-center gap-2">
        <PadButton keyName="up" icon={ChevronUp} label="Up" />
        <div className="flex items-center gap-2">
          <PadButton keyName="left" icon={ChevronLeft} label="Left" />
          {has('select') ? (
            <Button
              className="h-11 w-11 rounded-full font-bold"
              onClick={() => press('select')}
              title="OK / Select"
            >
              OK
            </Button>
          ) : (
            <div className="h-11 w-11" />
          )}
          <PadButton keyName="right" icon={ChevronRight} label="Right" />
        </div>
        <PadButton keyName="down" icon={ChevronDown} label="Down" />
      </div>

      {/* Nav row */}
      <div className="flex items-center justify-center gap-2">
        <PadButton keyName="back" icon={CornerUpLeft} label="Back" />
        <PadButton keyName="home" icon={Home} label="Home" />
        <PadButton keyName="menu" icon={Menu} label="Menu" />
        <PadButton keyName="power" icon={Power} label="Power" />
      </div>

      {/* Transport */}
      <div className="flex items-center justify-center gap-2">
        <PadButton keyName="rewind" icon={Rewind} label="Rewind" />
        <PadButton keyName="play_pause" icon={Play} label="Play / Pause" />
        <PadButton keyName="forward" icon={FastForward} label="Forward" />
      </div>

      {/* Volume */}
      <div className="flex items-center justify-center gap-2">
        <PadButton keyName="volume_down" icon={Volume1} label="Volume Down" />
        <PadButton keyName="mute" icon={VolumeX} label="Mute" />
        <PadButton keyName="volume_up" icon={Volume2} label="Volume Up" />
      </div>

      {/* App shortcuts */}
      {caps?.supports_app_launch && (caps?.apps?.length ?? 0) > 0 && (
        <div className="space-y-2 border-t pt-3">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted-foreground">
            <AppWindow className="h-3.5 w-3.5" /> Apps
          </div>
          <div className="flex flex-wrap gap-2">
            {caps?.apps?.map((app) => (
              <Button
                key={app.id}
                variant="secondary"
                size="sm"
                onClick={() => launch(app.id, app.name)}
              >
                {app.name}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

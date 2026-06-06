import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { Gamepad2 } from 'lucide-react';
import { RemoteControl } from '@/components/RemoteControl';
import { WebRtcPlayer } from '@/components/WebRtcPlayer';

interface RemoteDialogProps {
  deviceId: number;
  deviceName: string;
  streamKey: string;
  webrtcUrl?: string | null;
  enabled?: boolean;
  trigger?: React.ReactNode;
}

export function RemoteDialog({
  deviceId,
  deviceName,
  streamKey,
  webrtcUrl,
  enabled = true,
  trigger,
}: RemoteDialogProps) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" size="sm" className="gap-1.5">
            <Gamepad2 className="h-4 w-4" /> Remote
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="w-[95vw] max-w-[1400px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Gamepad2 className="h-4 w-4 text-primary" /> {deviceName}
          </DialogTitle>
          <DialogDescription>
            Live device screen with native on-screen remote control.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4 md:flex-row md:items-start">
          <div className="min-w-0 flex-1">
            <div className="aspect-video overflow-hidden rounded-md border border-border bg-black">
              {open && enabled ? (
                <WebRtcPlayer
                  streamKey={streamKey}
                  webrtcUrl={webrtcUrl}
                  className="h-full w-full"
                  showFullscreen
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-xs uppercase tracking-widest text-muted-foreground">
                  {enabled ? 'Loading…' : 'Disabled'}
                </div>
              )}
            </div>
          </div>
          <div className="max-h-[70vh] w-full shrink-0 overflow-y-auto md:w-80">
            {open && <RemoteControl deviceId={deviceId} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

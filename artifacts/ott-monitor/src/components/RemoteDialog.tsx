import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { Gamepad2 } from 'lucide-react';
import { RemoteControl } from '@/components/RemoteControl';

interface RemoteDialogProps {
  deviceId: number;
  deviceName: string;
  trigger?: React.ReactNode;
}

export function RemoteDialog({ deviceId, deviceName, trigger }: RemoteDialogProps) {
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Gamepad2 className="h-4 w-4 text-primary" /> {deviceName}
          </DialogTitle>
          <DialogDescription>
            Native on-screen remote control for this device.
          </DialogDescription>
        </DialogHeader>
        {open && <RemoteControl deviceId={deviceId} />}
      </DialogContent>
    </Dialog>
  );
}

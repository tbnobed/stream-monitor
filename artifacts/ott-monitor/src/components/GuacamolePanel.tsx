import React, { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Terminal } from 'lucide-react';

export function GuacamolePanel() {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('/api/proxy/guacamole/');

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="fixed bottom-4 right-4 z-50 bg-background shadow-lg">
          <Terminal className="w-4 h-4 mr-2" />
          Remote Console
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[800px] sm:w-[800px] sm:max-w-full p-0 flex flex-col h-full bg-black border-l-border">
        <SheetHeader className="p-4 border-b border-border/50 bg-background/50">
          <SheetTitle className="text-sm font-mono text-muted-foreground uppercase tracking-wider">Guacamole Remote Access</SheetTitle>
        </SheetHeader>
        <div className="flex-1 w-full h-full relative">
          <iframe 
            src={url} 
            className="absolute inset-0 w-full h-full border-0"
            title="Guacamole Console"
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}

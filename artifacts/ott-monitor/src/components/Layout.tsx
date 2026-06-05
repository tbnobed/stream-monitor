import React from "react";
import { Nav } from "./Nav";
import { SseProvider } from "@/hooks/use-sse";

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <SseProvider>
      <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
        <Nav />
        <main className="flex-1">
          {children}
        </main>
      </div>
    </SseProvider>
  );
}

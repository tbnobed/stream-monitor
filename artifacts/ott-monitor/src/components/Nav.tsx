import React from "react";
import { Link, useLocation } from "wouter";
import { useGetDashboardSummary } from "@workspace/api-client-react";
import { Activity, LayoutDashboard, Monitor, PlaySquare, AlertTriangle, Settings, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

export function Nav() {
  const [location] = useLocation();
  const { data: summary } = useGetDashboardSummary({ query: { refetchInterval: 15000 } });

  const downCount = (summary?.devices_down || 0) + (summary?.hls_down || 0);

  const links = [
    { href: "/", label: "Wall", icon: LayoutDashboard },
    { href: "/devices", label: "Devices", icon: Monitor },
    { href: "/hls-streams", label: "HLS Streams", icon: PlaySquare },
    { href: "/incidents", label: "Incidents", icon: AlertTriangle },
    { href: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <nav className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center px-4 max-w-full">
        <div className="mr-6 flex items-center space-x-2">
          <Radio className="h-5 w-5 text-primary" />
          <span className="font-bold tracking-tight text-primary uppercase">NOC Monitor</span>
        </div>
        <div className="flex flex-1 items-center space-x-6 text-sm font-medium">
          {links.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}>
              <span className={cn(
                "flex items-center space-x-2 transition-colors hover:text-foreground/80 cursor-pointer",
                location === href ? "text-foreground" : "text-foreground/60"
              )}>
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </span>
            </Link>
          ))}
        </div>
        <div className="ml-auto flex items-center space-x-4">
          <div className="flex items-center space-x-2 text-sm border rounded-md px-3 py-1 bg-card">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">System Status:</span>
            {downCount > 0 ? (
              <span className="text-status-down font-bold animate-pulse">{downCount} DOWN</span>
            ) : (
              <span className="text-status-healthy font-bold">ALL CLEAR</span>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}

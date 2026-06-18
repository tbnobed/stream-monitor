import React from "react";
import { Link, useLocation } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetDashboardSummary,
  useLogout,
  getGetCurrentUserQueryKey,
  getGetDashboardSummaryQueryKey,
} from "@workspace/api-client-react";
import {
  Activity,
  LayoutDashboard,
  Monitor,
  PlaySquare,
  AlertTriangle,
  Settings,
  Users as UsersIcon,
  LogOut,
  ShieldCheck,
  User as UserIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";

export function Nav() {
  const [location] = useLocation();
  const queryClient = useQueryClient();
  const { user, isAdmin } = useAuth();
  const { data: summary } = useGetDashboardSummary({
    query: { queryKey: getGetDashboardSummaryQueryKey(), refetchInterval: 15000 },
  });

  const downCount = (summary?.devices_down || 0) + (summary?.hls_down || 0);

  const logout = useLogout({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetCurrentUserQueryKey() });
      },
    },
  });

  const links = [
    { href: "/", label: "Wall", icon: LayoutDashboard, adminOnly: false },
    { href: "/devices", label: "Devices", icon: Monitor, adminOnly: true },
    { href: "/hls-streams", label: "HLS Streams", icon: PlaySquare, adminOnly: true },
    { href: "/incidents", label: "Incidents", icon: AlertTriangle, adminOnly: true },
    { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
    { href: "/users", label: "Users", icon: UsersIcon, adminOnly: true },
  ].filter((l) => !l.adminOnly || isAdmin);

  return (
    <nav className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center px-4 max-w-full">
        <div className="mr-6 flex items-center space-x-2">
          <img
            src={`${import.meta.env.BASE_URL}pulse-icon.png`}
            alt="Pulse"
            className="h-6 w-6 rounded"
          />
          <span className="font-bold tracking-tight text-primary">Pulse</span>
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
          {user && (
            <div className="flex items-center space-x-2 text-sm">
              {isAdmin ? (
                <ShieldCheck className="h-4 w-4 text-primary" />
              ) : (
                <UserIcon className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="hidden sm:inline text-foreground/80">{user.username}</span>
              <Button
                variant="ghost"
                size="icon"
                title="Sign out"
                onClick={() => logout.mutate()}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}

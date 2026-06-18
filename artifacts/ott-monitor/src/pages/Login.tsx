import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetAuthConfig,
  useLogin,
  getGetCurrentUserQueryKey,
} from "@workspace/api-client-react";
import { LogIn, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const SSO_LOGIN_URL = "/api/auth/sso/login";

export default function Login() {
  const queryClient = useQueryClient();
  const { data: config } = useGetAuthConfig();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ssoError =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("sso_error");

  const login = useLogin({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetCurrentUserQueryKey() });
      },
      onError: () => {
        setError("Invalid username or password.");
      },
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    login.mutate({ data: { username, password } });
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 font-sans">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <img
            src={`${import.meta.env.BASE_URL}pulse-icon.png`}
            alt="Pulse"
            className="mb-3 h-14 w-14 rounded-xl"
          />
          <h1 className="text-xl font-bold tracking-tight text-primary">
            Pulse
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to access the monitoring wall
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 shadow-sm">
          {(error || ssoError) && (
            <div className="mb-4 rounded-md border border-status-down/40 bg-status-down/10 px-3 py-2 text-sm text-status-down">
              {error ||
                (ssoError === "disabled"
                  ? "Your account is disabled. Contact an administrator."
                  : "Single sign-on failed. Please try again.")}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <LogIn className="mr-2 h-4 w-4" />
                  Sign in
                </>
              )}
            </Button>
          </form>

          {config?.sso_enabled && (
            <>
              <div className="my-4 flex items-center gap-3">
                <div className="h-px flex-1 bg-border" />
                <span className="text-xs uppercase text-muted-foreground">or</span>
                <div className="h-px flex-1 bg-border" />
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  window.location.href = SSO_LOGIN_URL;
                }}
              >
                Sign in with {config.sso_label}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

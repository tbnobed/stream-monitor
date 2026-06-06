// Helpers for the QR phone-remote feature.
//
// These talk to the token-scoped endpoints directly (not via the generated
// client) because the public phone routes use a different auth model: authority
// is the QR token, not a login session. The API is always served at `/api`
// (OpenAPI `servers.url`), routed there by the shared dev proxy / nginx.

const API_BASE = "/api";

export interface MobileRemoteSession {
  device_id: number;
  device_name: string;
  platform?: string | null;
  protocol?: string | null;
  capable: boolean;
  reachable: boolean;
  paired: boolean;
  requires_pairing: boolean;
  keys: string[];
  detail?: string | null;
}

export interface MobileToken {
  token: string;
  ttl_seconds: number;
}

export class MobileRemoteError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new MobileRemoteError(res.status, detail);
  }
  return (await res.json()) as T;
}

// --- Desktop (authenticated) side -----------------------------------------

export function createMobileToken(deviceId: number): Promise<MobileToken> {
  return request<MobileToken>(`/devices/${deviceId}/remote/mobile-token`, {
    method: "POST",
  });
}

export function heartbeatMobileToken(deviceId: number, token: string): Promise<unknown> {
  return request(`/devices/${deviceId}/remote/mobile-token/${token}/heartbeat`, {
    method: "POST",
  });
}

export function revokeMobileToken(token: string): void {
  // Prefer sendBeacon so the request survives the page/modal teardown.
  const url = `${API_BASE}/m/${token}/revoke`;
  if (typeof navigator !== "undefined" && navigator.sendBeacon) {
    navigator.sendBeacon(url);
    return;
  }
  // Fallback: best-effort fire-and-forget.
  void fetch(url, { method: "POST", credentials: "same-origin", keepalive: true });
}

// --- Phone (public, token-scoped) side ------------------------------------

export function getMobileSession(token: string): Promise<MobileRemoteSession> {
  return request<MobileRemoteSession>(`/m/${token}`);
}

export function sendMobileKey(token: string, key: string): Promise<unknown> {
  return request(`/m/${token}/key`, {
    method: "POST",
    body: JSON.stringify({ key }),
  });
}

// Build the absolute URL a phone should open for a given token. Uses the app's
// configured base path so it works under a subpath deploy too.
export function buildMobileRemoteUrl(token: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const path = `${base}m/${token}`.replace(/\/{2,}/g, "/");
  return new URL(path, window.location.origin).toString();
}

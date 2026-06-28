/** API client — thin wrapper around fetch for AgentX backend. */

import type {
  CreateSessionRequest,
  CreateSessionResponse,
  SubmitFixRequest,
  SubmitFixResponse,
  WriteOriginalRequest,
  WriteOriginalResponse,
} from "./types";

// In dev, Vite proxy forwards /api to localhost:8000
// In production, set VITE_API_URL env var
const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function createSession(req: CreateSessionRequest): Promise<CreateSessionResponse> {
  return apiFetch<CreateSessionResponse>("/api/sessions", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function submitFix(
  sessionId: string,
  req: SubmitFixRequest,
): Promise<SubmitFixResponse> {
  return apiFetch<SubmitFixResponse>(`/api/sessions/${sessionId}/fix`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}
export function submitOriginalCode(
  sessionId: string,
  req: WriteOriginalRequest,
): Promise<WriteOriginalResponse> {
  return apiFetch<WriteOriginalResponse>(`/api/sessions/${sessionId}/write`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function getSession(sessionId: string) {
  return apiFetch(`/api/sessions/${sessionId}`);
}

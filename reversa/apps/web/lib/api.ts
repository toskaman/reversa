"use client";

export function apiBase(): string {
  if (typeof window !== "undefined") {
    const custom = window.localStorage.getItem("reversa_api");
    if (custom) return custom.replace(/\/$/, "");
  }
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("reversa_token") || "";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, opts?: RequestInit): Promise<T> {
  return apiAs<T>(path, getToken(), opts);
}

export async function apiAs<T>(
  path: string, token: string, opts?: RequestInit,
): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep status text */ }
    throw new ApiError(res.status, `${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

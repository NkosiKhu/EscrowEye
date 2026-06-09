export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(errorMessage(status, body));
    this.status = status;
    this.body = body;
  }
}

function errorMessage(status: number, body: unknown) {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.error === "string") return record.error;
    if (typeof record.detail === "string") return record.detail;
  }
  return `HTTP ${status}`;
}

export async function apiRequest<T>(token: string | null, path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const hasBody = options.body !== undefined;
  if (hasBody && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("Content-Type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

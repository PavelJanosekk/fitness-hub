export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

type Options = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal };

/** JSON fetch against the FastAPI backend (same origin; Vite proxies /api in dev). */
export async function api<T>(path: string, { method = "GET", body, form, signal }: Options = {}): Promise<T> {
  const response = await fetch(path, {
    method,
    signal,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  if (response.status === 204) return undefined as T;
  const payload = response.headers.get("content-type")?.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(response.status, (payload as { detail?: unknown })?.detail ?? payload);
  return payload as T;
}

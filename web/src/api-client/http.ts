/**
 * The single place the web client talks to the backend.
 * Components never call `fetch` directly, so a contract change stays in `api-client/`.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(path, {
    method: options.method ?? "GET",
    credentials: "include",
    headers,
    body: options.formData ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
    signal: options.signal,
  });

  const data = (await response.json().catch(() => ({}))) as { detail?: string } & T;
  if (!response.ok) {
    throw new ApiError(data.detail || "Không kết nối được máy chủ. Vui lòng thử lại.", response.status);
  }
  return data;
}

/** Stable key so a retried mutation does not create a second record. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

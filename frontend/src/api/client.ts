import type { ListResponse } from './types';

const API_PREFIX = '/api/v1';
const TOKEN_KEY = 'saq_token';

// ---------------------------------------------------------------- token

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be blocked (private mode); the session then lasts until reload.
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** AuthProvider registers this; it is called on any 401 from a non-login request. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

// ---------------------------------------------------------------- errors

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const { code, message } = detail as { code?: string; message?: string };
      return new ApiError(response.status, code ?? 'error', message ?? response.statusText);
    }
    // FastAPI validation errors (422) send detail as an array.
    if (Array.isArray(detail)) {
      const message = detail
        .map((item: { loc?: unknown[]; msg?: string }) => `${item.loc?.slice(1).join('.') ?? ''}: ${item.msg ?? ''}`)
        .join('; ');
      return new ApiError(response.status, 'validation_error', message);
    }
    if (typeof detail === 'string') return new ApiError(response.status, 'error', detail);
  } catch {
    // Body is not JSON (e.g. a gateway error page); fall through to the status text.
  }
  return new ApiError(response.status, response.status >= 500 ? 'server_error' : 'error', response.statusText);
}

// ---------------------------------------------------------------- requests

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

export function buildQuery(params?: QueryParams): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  params?: QueryParams;
  /** JSON body, or FormData for multipart (the browser sets the boundary). */
  body?: unknown;
  signal?: AbortSignal;
}

async function send(path: string, options: RequestOptions = {}): Promise<Response> {
  const { method = 'GET', params, body, signal } = options;
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}${buildQuery(params)}`, { method, headers, body: payload, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'network_error', 'Network error');
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (response.status === 401 && path !== '/auth/login') unauthorizedHandler?.();
    throw error;
  }
  return response;
}

export async function api<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Authenticated binary download (evidence content, PDF). */
export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const response = await send(path, { signal });
  return response.blob();
}

/** Saves an authenticated file through a temporary object URL. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Opens an authenticated file in a new tab. */
export async function openFile(path: string): Promise<void> {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function unwrapList<T>(response: ListResponse<T>): T[] {
  return Array.isArray(response) ? response : response.items;
}

/** Builds multipart form data; skips empty values, appends arrays/files under the same key. */
export function toFormData(
  fields: Record<string, string | number | boolean | Date | File | File[] | null | undefined>,
): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const file of value) form.append(key, file);
    } else if (value instanceof File) {
      form.append(key, value);
    } else if (value instanceof Date) {
      form.append(key, value.toISOString());
    } else {
      form.append(key, String(value));
    }
  }
  return form;
}

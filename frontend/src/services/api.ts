/**
 * The one centralised HTTP client. Every feature service goes through this
 * instance so JWT attachment, error normalisation and base URL handling happen
 * in exactly one place.
 */

import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig } from "axios";

import { env } from "@/lib/env";
import { emitUnauthorized, getAccessToken } from "@/lib/session";
import type { ApiErrorEnvelope } from "@/types";

/** Normalised error surfaced to the UI. Mirrors the backend error envelope. */
export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly details: Record<string, unknown>;

  constructor(
    message: string,
    options: { code?: string; status?: number | null; details?: Record<string, unknown> } = {},
  ) {
    super(message);
    this.name = "ApiClientError";
    this.code = options.code ?? "unknown_error";
    this.status = options.status ?? null;
    this.details = options.details ?? {};
  }

  /** True when the server refused the credentials rather than the request. */
  get isAuthError(): boolean {
    return this.status === 401 || this.code === "unauthorized";
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === "not_found";
  }
}

export const api: AxiosInstance = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 60_000,
  headers: { Accept: "application/json" },
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorEnvelope | { detail?: unknown }>) => {
    const status = error.response?.status ?? null;
    const payload = error.response?.data;

    let code = "network_error";
    let message = "Unable to reach the Continuum API. Is the backend running?";
    let details: Record<string, unknown> = {};

    if (payload && typeof payload === "object" && "error" in payload && payload.error) {
      code = payload.error.code ?? code;
      message = payload.error.message ?? message;
      details = (payload.error.details as Record<string, unknown>) ?? {};
    } else if (status) {
      code = status === 401 ? "unauthorized" : "http_error";
      message = error.message || `Request failed with status ${status}.`;
    }

    if (status === 401) {
      emitUnauthorized();
    }

    return Promise.reject(new ApiClientError(message, { code, status, details }));
  },
);

/** Human-readable message for any thrown value. */
export function toErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export async function apiGet<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await api.get<T>(url, config);
  return data;
}

export async function apiPost<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const { data } = await api.post<T>(url, body, config);
  return data;
}

export async function apiPatch<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const { data } = await api.patch<T>(url, body, config);
  return data;
}

export async function apiDelete<T>(url: string, config?: AxiosRequestConfig): Promise<T | null> {
  const response = await api.delete<T>(url, config);
  return response.status === 204 ? null : response.data;
}

/**
 * Session token storage.
 *
 * The access token is kept in memory and mirrored to ``localStorage`` so a
 * refresh does not sign the user out. Tokens are opaque to this app: the
 * backend verifies them on every request, and the token itself never grants
 * anything the server does not independently re-check.
 */

const STORAGE_KEY = "continuum.access_token";

let inMemoryToken: string | null = readInitialToken();

function readInitialToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return inMemoryToken;
}

export function setAccessToken(token: string | null): void {
  inMemoryToken = token;
  try {
    if (token) window.localStorage.setItem(STORAGE_KEY, token);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode) — the in-memory copy still works */
  }
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

/** Emitted when the API rejects the current token so the UI can sign out. */
export const UNAUTHORIZED_EVENT = "continuum:unauthorized";

export function emitUnauthorized(): void {
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

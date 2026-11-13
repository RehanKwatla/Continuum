/**
 * Session token storage.
 *
 * The access token is kept in memory and mirrored to ``sessionStorage`` so a
 * refresh does not sign the user out within the same tab. ``sessionStorage`` is
 * scoped to the tab/session and is cleared when the tab closes, which shrinks
 * the window for XSS-based token exfiltration compared with ``localStorage``.
 *
 * Tokens are opaque to this app: the backend verifies them on every request,
 * and the token itself never grants anything the server does not independently
 * re-check.
 *
 * TODO: migrate to httpOnly cookies (set by the backend) so JavaScript cannot
 * read the token at all. That requires the backend to issue Set-Cookie on
 * login and the frontend to send credentials with every request.
 */

const STORAGE_KEY = "continuum.access_token";

let inMemoryToken: string | null = readInitialToken();

function readInitialToken(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
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
    if (token) window.sessionStorage.setItem(STORAGE_KEY, token);
    else window.sessionStorage.removeItem(STORAGE_KEY);
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

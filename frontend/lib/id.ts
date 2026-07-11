/**
 * Generates a client-side correlation id (React list keys, and the
 * capture_session_id that ties a consent-phrase recording to its
 * reference-sample recording). Prefers crypto.randomUUID(), but falls
 * back when it's unavailable -- it requires a secure context in real
 * browsers and isn't implemented in the jsdom test environment. Not
 * cryptographically strong, but nothing security-relevant depends on this
 * id's unpredictability: the backend independently validates
 * capture_session_id server-side (see app/routers/participants.py).
 */
export function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

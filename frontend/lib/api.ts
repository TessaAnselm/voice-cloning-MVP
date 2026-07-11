/**
 * Thin typed wrapper around the FastAPI backend. No business logic lives
 * here beyond HTTP plumbing -- every safety decision (consent, content
 * filtering, expiration) is made server-side and simply reflected in these
 * response shapes. The frontend must never assume something is allowed
 * just because a button is visible; it always asks the backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ParticipantOut {
  id: string;
  display_name: string;
  participant_token: string;
  consent_status: "none" | "granted" | "revoked";
  consent_timestamp: string | null;
  revoke_timestamp: string | null;
  has_audio_sample: boolean;
  audio_sample_expires_at: string | null;
}

export interface SessionOut {
  id: string;
  retention_ttl_seconds: number;
  expires_at: string;
  ended_at: string | null;
  created_at: string;
  is_active: boolean;
  blocked_generation_count: number;
  participants: ParticipantOut[];
}

export interface ParticipantPublicOut {
  id: string;
  session_id: string;
  display_name: string;
  consent_status: "none" | "granted" | "revoked";
  has_audio_sample: boolean;
  session_is_active: boolean;
}

export interface GenerateVoiceResponse {
  blocked: boolean;
  safety_label: string;
  blocked_reason: string | null;
  audio_url: string | null;
  provider_used: string | null;
  fallback_active: boolean;
  disclosure_text: string | null;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...(init?.headers || {}) }
        : init?.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore parse failure, use statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createSession: (retentionTtlSeconds: number) =>
    request<SessionOut>("/sessions", {
      method: "POST",
      body: JSON.stringify({ retention_ttl_seconds: retentionTtlSeconds }),
    }),

  getSession: (sessionId: string) => request<SessionOut>(`/sessions/${sessionId}`),

  endSession: (sessionId: string) =>
    request<{ status: string; session_id: string }>(`/sessions/${sessionId}`, {
      method: "DELETE",
    }),

  addParticipant: (sessionId: string, displayName: string) =>
    request<ParticipantOut>(`/sessions/${sessionId}/participants`, {
      method: "POST",
      body: JSON.stringify({ display_name: displayName }),
    }),

  getParticipantByToken: (token: string) =>
    request<ParticipantPublicOut>(`/participants/token/${token}`),

  /** Explicit consent-button click. No audio, no capture_session_id. */
  grantConsent: (participantId: string) =>
    request<ParticipantOut>(`/participants/${participantId}/consent`, { method: "POST" }),

  /** Marks the spoken consent-phrase segment of a continuous capture complete. */
  markConsentPhraseCaptured: (participantId: string, captureSessionId: string) =>
    request<ParticipantOut>(`/participants/${participantId}/consent`, {
      method: "POST",
      body: JSON.stringify({ capture_session_id: captureSessionId }),
    }),

  revokeConsent: (participantId: string) =>
    request<ParticipantOut>(`/participants/${participantId}/revoke-consent`, { method: "POST" }),

  submitAudioSample: (
    participantId: string,
    captureSessionId: string,
    blob: Blob,
    durationSeconds: number
  ) => {
    const form = new FormData();
    form.append("capture_session_id", captureSessionId);
    form.append("duration_seconds", String(durationSeconds));
    form.append("file", blob, "reference-sample.webm");
    return request<ParticipantOut>(`/participants/${participantId}/audio-sample`, {
      method: "POST",
      body: form,
    });
  },

  deleteAudioSample: (participantId: string) =>
    request<ParticipantOut>(`/participants/${participantId}/audio-sample`, { method: "DELETE" }),

  generateVoice: (sessionId: string, participantId: string, text: string) =>
    request<GenerateVoiceResponse>("/generate-voice", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, participant_id: participantId, text }),
    }),

  audioUrl: (relativeUrl: string) => `${API_URL}${relativeUrl}`,
};

export { ApiError, API_URL };

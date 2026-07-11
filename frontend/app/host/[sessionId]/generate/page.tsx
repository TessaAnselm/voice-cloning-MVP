"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, GenerateVoiceResponse, SessionOut } from "@/lib/api";
import { generateId } from "@/lib/id";

interface HistoryEntry extends GenerateVoiceResponse {
  id: string;
  requestedText: string;
  participantName: string;
  generatedAt: string;
}

export default function GenerateVoicePage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [participantId, setParticipantId] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // History of every attempt this page has made (newest first), so
  // previously generated clips stay listed and replayable instead of
  // disappearing once the host generates something new.
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSession(sessionId)
      .then((s) => {
        setSession(s);
        const firstConsenting = s.participants.find(
          (p) => p.consent_status === "granted" && p.has_audio_sample
        );
        if (firstConsenting) setParticipantId(firstConsenting.id);
      })
      .catch(() => setLoadError("Session not found or has expired."));
  }, [sessionId]);

  const eligibleParticipants =
    session?.participants.filter((p) => p.consent_status === "granted" && p.has_audio_sample) || [];

  async function handleGenerate() {
    if (!participantId || !text.trim()) return;
    const participantName =
      eligibleParticipants.find((p) => p.id === participantId)?.display_name || "participant";
    const requestedText = text.trim();
    setSubmitting(true);
    try {
      const res = await api.generateVoice(sessionId, participantId, requestedText);
      setHistory((prev) => [
        { ...res, id: generateId(), requestedText, participantName, generatedAt: new Date().toISOString() },
        ...prev,
      ]);
    } catch (e) {
      setHistory((prev) => [
        {
          blocked: true,
          safety_label: "blocked:request_error",
          blocked_reason: e instanceof Error ? e.message : "Request failed.",
          audio_url: null,
          provider_used: null,
          fallback_active: false,
          disclosure_text: null,
          id: generateId(),
          requestedText,
          participantName,
          generatedAt: new Date().toISOString(),
        },
        ...prev,
      ]);
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <main className="container">
        <div className="banner danger">{loadError}</div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="container">
        <p>Loading...</p>
      </main>
    );
  }

  return (
    <main className="container">
      <h1>Generate demo voice audio</h1>
      <p className="subtitle">
        <Link href={`/host/${sessionId}`}>&larr; Back to dashboard</Link>
      </p>

      <div className="banner warn">
        Every clip generated here is a synthetic AI voice clone built only from the selected
        participant&apos;s own recorded sample. Generated audio always includes a spoken
        disclosure identifying it as AI-generated. Do not use this to impersonate anyone or in any
        real communication.
      </div>

      {!session.is_active && (
        <div className="banner danger">This session has ended or expired. Generation is disabled.</div>
      )}

      <div className="card">
        <h2>1. Select a consenting participant</h2>
        {eligibleParticipants.length === 0 ? (
          <p className="subtitle">
            No participants are currently eligible. A participant must have granted consent and
            recorded a voice sample (and not have revoked or deleted it).
          </p>
        ) : (
          <select
            value={participantId}
            onChange={(e) => setParticipantId(e.target.value)}
            style={{
              width: "100%",
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid var(--panel-border)",
              background: "#0d0f13",
              color: "var(--text)",
              fontSize: 14,
            }}
          >
            <option value="">-- select participant --</option>
            {eligibleParticipants.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="card">
        <h2>2. Enter the text to speak</h2>
        <div className="field">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type a sentence for the demo to speak in the selected participant's voice..."
            maxLength={1000}
          />
        </div>
        <p className="subtitle" style={{ fontSize: 13 }}>
          Every request is screened by a safety filter before generation. Requests involving
          payments, one-time codes/passwords, urgent money transfers, threats, or impersonation of
          someone outside this session are blocked and logged.
        </p>
        <button
          onClick={handleGenerate}
          disabled={submitting || !session.is_active || !participantId || !text.trim()}
        >
          {submitting ? "Checking & generating..." : "Run content filter and generate"}
        </button>
      </div>

      {history.length > 0 && (
        <div className="card">
          <h2>Generated clips {history.length > 1 && "(most recent first)"}</h2>
          <p className="subtitle" style={{ fontSize: 13 }}>
            Every clip from this page stays listed below so you can replay it again -- these are
            not deleted until the session ends or expires.
          </p>
          {history.map((entry) => (
            <div
              key={entry.id}
              style={{
                borderTop: "1px solid var(--panel-border)",
                paddingTop: 16,
                marginTop: 16,
              }}
            >
              <p style={{ margin: "0 0 8px", fontSize: 13, color: "var(--text-dim)" }}>
                {new Date(entry.generatedAt).toLocaleTimeString()} &middot; {entry.participantName}
                &nbsp;&middot;&nbsp;&ldquo;{entry.requestedText}&rdquo;
              </p>
              {entry.blocked ? (
                <div className="banner danger">
                  <strong>Blocked by safety filter</strong>
                  <p style={{ margin: "8px 0 0" }}>{entry.blocked_reason}</p>
                  <p style={{ margin: "8px 0 0", fontSize: 13 }}>
                    Safety label: <code>{entry.safety_label}</code>. This attempt has been logged
                    and counted on the host dashboard.
                  </p>
                </div>
              ) : (
                <>
                  {entry.fallback_active && (
                    <div className="banner warn">
                      <strong>Fallback mode active: BrowserTTSProvider was used.</strong>
                      <p style={{ margin: "8px 0 0" }}>
                        The local voice-cloning model (LocalCloneProvider) was unavailable, so
                        this clip does <strong>not</strong> clone the participant&apos;s voice --
                        it&apos;s generic fallback speech only. See README.md to enable real local
                        cloning.
                      </p>
                    </div>
                  )}
                  <div className="banner warn">
                    This audio is an AI-generated synthetic voice clone created for this
                    cybersecurity education demo. It is not a real recording of the participant
                    saying these words.
                  </div>
                  {entry.audio_url && (
                    <audio controls src={api.audioUrl(entry.audio_url)} style={{ width: "100%" }} />
                  )}
                  <p className="subtitle" style={{ fontSize: 13 }}>
                    Provider used: <code>{entry.provider_used}</code>. Spoken disclosure embedded:
                    &ldquo;{entry.disclosure_text}&rdquo;
                  </p>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

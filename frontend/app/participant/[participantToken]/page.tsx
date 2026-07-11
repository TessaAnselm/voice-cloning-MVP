"use client";

/**
 * Single-page participant flow: consent disclosure -> explicit consent
 * button -> continuous live-microphone recording (consent phrase, then
 * reference sample) -> done. Everything happens on this one page/URL, with
 * no route navigation between steps, so a participant never has to figure
 * out where to go next.
 *
 * *** Uses the browser MediaRecorder API only. ***
 * There is no <input type="file">, no drag-and-drop zone, no "paste a
 * link" field, and no way to import a pre-existing audio file anywhere on
 * this page -- by design (safety requirement #13). The only audio that can
 * ever reach the backend from this page is whatever was just captured live
 * from getUserMedia() below.
 *
 * Safety requirement #14: the consent phrase and the reference sample are
 * recorded back-to-back from the SAME getUserMedia() stream, without ever
 * releasing the microphone or re-prompting for permission in between, and
 * both segments are tagged with the same client-generated captureSessionId.
 * The backend independently re-validates this binding (see
 * app/routers/participants.py) -- this page's job is only to make it easy
 * to do the right thing, not to be the source of truth for it.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, ParticipantPublicOut } from "@/lib/api";
import { generateId } from "@/lib/id";

const CONSENT_PHRASE =
  "I consent to this voice sample being used for this cybersecurity education demo.";

type Phase =
  | "loading"
  | "invalid"
  | "session-ended"
  | "revoked"
  | "consent" // step 1: explicit consent button not yet pressed
  | "ready-to-record" // consent granted, recording not started yet
  | "requesting-mic"
  | "recording-phrase"
  | "recording-sample"
  | "uploading"
  | "recorded"; // sample already on file (freshly recorded or from before)

export default function ParticipantPage() {
  const { participantToken } = useParams<{ participantToken: string }>();

  const [phase, setPhase] = useState<Phase>("loading");
  const [participant, setParticipant] = useState<ParticipantPublicOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [consenting, setConsenting] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const captureSessionIdRef = useRef<string | null>(null);
  const sampleStartedAtRef = useRef<number>(0);

  function phaseFromParticipant(p: ParticipantPublicOut): Phase {
    if (!p.session_is_active) return "session-ended";
    if (p.consent_status === "revoked") return "revoked";
    if (p.consent_status === "none") return "consent";
    if (p.has_audio_sample) return "recorded";
    return "ready-to-record";
  }

  async function refresh() {
    try {
      const p = await api.getParticipantByToken(participantToken);
      setParticipant(p);
      setPhase(phaseFromParticipant(p));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "This link is invalid.");
      setPhase("invalid");
    }
  }

  useEffect(() => {
    refresh();
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantToken]);

  // --- Step 1: explicit consent button --------------------------------
  async function handleConsent() {
    if (!participant) return;
    setConsenting(true);
    setError(null);
    try {
      await api.grantConsent(participant.id);
      // Stay on this same page/URL -- just move to the recording step.
      setPhase("ready-to-record");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record consent.");
    } finally {
      setConsenting(false);
    }
  }

  // --- Step 2: continuous consent-phrase + sample recording ------------
  async function startContinuousCapture() {
    setRecordError(null);
    setPhase("requesting-mic");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      captureSessionIdRef.current = generateId();
      startPhraseRecording(stream);
    } catch {
      setPhase("ready-to-record");
      setRecordError("Microphone access is required to record your consent phrase and sample.");
    }
  }

  function startPhraseRecording(stream: MediaStream) {
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = handlePhraseRecordingStopped;
    recorder.start();
    setPhase("recording-phrase");
  }

  async function handlePhraseRecordingStopped() {
    if (!participant || !captureSessionIdRef.current) return;
    try {
      // Mark the consent-phrase segment complete BEFORE starting the
      // sample segment -- the backend will refuse the sample upload later
      // if this step didn't happen first (requirement #15).
      await api.markConsentPhraseCaptured(participant.id, captureSessionIdRef.current);
      // Immediately continue on the SAME stream -- no new getUserMedia()
      // call, no permission re-prompt, no gap where the mic is released.
      startSampleRecording();
    } catch (e) {
      setPhase("ready-to-record");
      setRecordError(e instanceof Error ? e.message : "Failed to save the consent phrase step.");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    }
  }

  function startSampleRecording() {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = handleSampleRecordingStopped;
    sampleStartedAtRef.current = Date.now();
    recorder.start();
    setPhase("recording-sample");
  }

  async function handleSampleRecordingStopped() {
    if (!participant || !captureSessionIdRef.current) return;
    setPhase("uploading");
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    const durationSeconds = (Date.now() - sampleStartedAtRef.current) / 1000;
    try {
      await api.submitAudioSample(participant.id, captureSessionIdRef.current, blob, durationSeconds);
      await refresh();
    } catch (e) {
      setPhase("ready-to-record");
      setRecordError(e instanceof Error ? e.message : "Failed to upload your voice sample.");
    } finally {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  function stopCurrentRecording() {
    recorderRef.current?.stop();
  }

  // --- Revoke / delete ---------------------------------------------------
  async function handleRevoke() {
    if (!participant) return;
    if (
      !confirm(
        "Withdraw your consent? This immediately blocks any future voice generation using your voice."
      )
    ) {
      return;
    }
    setRevoking(true);
    try {
      await api.revokeConsent(participant.id);
      await refresh();
    } finally {
      setRevoking(false);
    }
  }

  async function handleDeleteSample() {
    if (!participant) return;
    if (!confirm("Delete your recorded voice sample? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteAudioSample(participant.id);
      await refresh();
    } finally {
      setDeleting(false);
    }
  }

  if (phase === "loading") {
    return (
      <main className="container">
        <p>Loading...</p>
      </main>
    );
  }

  if (phase === "invalid") {
    return (
      <main className="container">
        <div className="banner danger">{error}</div>
      </main>
    );
  }

  if (phase === "session-ended") {
    return (
      <main className="container">
        <div className="banner danger">
          This session has ended or expired. All consent records and voice data for it have been
          deleted.
        </div>
      </main>
    );
  }

  if (!participant) return null;

  return (
    <main className="container">
      <h1>Hi {participant.display_name}, you&apos;re invited to a voice demo</h1>
      <p className="subtitle">
        This is a local cybersecurity education demo showing how consent-based voice cloning
        products work.
      </p>

      <div className="card">
        <h2>What will happen if you consent</h2>
        <ul>
          <li>
            You&apos;ll record a short, uninterrupted clip using your own device&apos;s microphone,
            right here on this page. You&apos;ll first speak a consent phrase, then a short
            additional sample -- all in one continuous recording.
          </li>
          <li>
            The host can then type any sentence and generate audio of it spoken in a synthetic
            version of your voice, built only from that sample.
          </li>
          <li>
            Every generated clip includes a spoken disclosure identifying it as AI-generated, and
            requests are screened by a safety filter before generation.
          </li>
          <li>
            <strong>You can revoke your consent or delete your voice sample at any time</strong>{" "}
            from this page -- doing so immediately blocks any further use of your voice.
          </li>
          <li>
            All data (consent record, voice sample, and generated clips) is automatically deleted
            when this session ends or expires.
          </li>
          <li>There is no upload option -- only audio recorded live, right now, is ever accepted.</li>
        </ul>
      </div>

      {phase === "revoked" && (
        <div className="card">
          <div className="banner danger">
            You have revoked consent. Your voice can no longer be used to generate audio in this
            session.
          </div>
        </div>
      )}

      {phase === "consent" && (
        <div className="card">
          <h2>Your consent</h2>
          <p className="subtitle">
            Recording will not start until you press the button below. Nothing is captured before
            this.
          </p>
          {error && <div className="banner danger">{error}</div>}
          <button onClick={handleConsent} disabled={consenting}>
            {consenting ? "Recording consent..." : "I consent to this voice sample being recorded"}
          </button>
        </div>
      )}

      {(phase === "ready-to-record" ||
        phase === "requesting-mic" ||
        phase === "recording-phrase" ||
        phase === "recording-sample" ||
        phase === "uploading") && (
        <div className="card">
          <div className="banner ok">You have consented.</div>

          <div className="banner warn">
            Recording only happens live through your browser&apos;s microphone. There is no upload
            option and no way to submit a pre-existing audio file.
          </div>

          {recordError && <div className="banner danger">{recordError}</div>}

          {phase === "ready-to-record" && (
            <>
              <h2>Record your voice sample</h2>
              <p>
                This will be one continuous recording. First you&apos;ll say the consent phrase,
                then a short additional sample -- without stopping or uploading anything in
                between. When you press start, please read this phrase aloud clearly, then press
                &quot;Done saying the phrase&quot; to continue immediately to the next step:
              </p>
              <blockquote className="phrase-block">&ldquo;{CONSENT_PHRASE}&rdquo;</blockquote>
              <button onClick={startContinuousCapture}>Start continuous recording</button>
            </>
          )}

          {phase === "requesting-mic" && <p>Requesting microphone access...</p>}

          {phase === "recording-phrase" && (
            <>
              <div className="banner danger">Recording &mdash; say the consent phrase now:</div>
              <blockquote className="phrase-block">&ldquo;{CONSENT_PHRASE}&rdquo;</blockquote>
              <button onClick={stopCurrentRecording}>Done saying the phrase &rarr;</button>
            </>
          )}

          {phase === "recording-sample" && (
            <>
              <div className="banner danger">
                Recording your additional voice sample now. Speak naturally for a few seconds (for
                example, describe your day), then press stop.
              </div>
              <button onClick={stopCurrentRecording}>Stop recording</button>
            </>
          )}

          {phase === "uploading" && <p>Saving your voice sample...</p>}
        </div>
      )}

      {phase === "recorded" && (
        <div className="card">
          <div className="banner ok">
            Your voice sample has been recorded and saved. The host can now use it to generate
            demo audio -- always with a spoken AI-disclosure included.
          </div>
          <div className="row">
            <button className="danger outline" onClick={handleDeleteSample} disabled={deleting}>
              {deleting ? "Deleting..." : "Delete my voice sample"}
            </button>
            <button className="danger" onClick={handleRevoke} disabled={revoking}>
              {revoking ? "Revoking..." : "Revoke my consent"}
            </button>
          </div>
          <p className="subtitle" style={{ marginTop: 16, marginBottom: 0 }}>
            <Link href={`/host/${participant.session_id}`}>&larr; Return to dashboard</Link>
          </p>
        </div>
      )}
    </main>
  );
}

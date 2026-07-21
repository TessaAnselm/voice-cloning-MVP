"use client";

/**
 * Single-page participant flow: consent disclosure -> explicit consent
 * button -> continuous live-microphone recording (consent phrase, then
 * reference sample) -> listen back and confirm (or re-record) -> done.
 * Everything happens on this one page/URL, with no route navigation between
 * steps, so a participant never has to figure out where to go next.
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

// Keep these two in sync with the backend's equivalent guards (see
// backend/app/config.py MIN_AUDIO_SAMPLE_PEAK_DBFS) -- this is a fast,
// client-side pre-check so a participant finds out immediately if their
// mic wasn't picking up anything, without waiting on a round trip. The
// backend re-validates independently and is the actual source of truth.
const MIN_SAMPLE_PEAK_DBFS = -50;
const LIVE_METER_LOW_RMS = 0.02;
const LIVE_METER_LOW_SUSTAIN_FRAMES = 90; // ~1.5s at 60fps

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
  | "reviewing" // sample recorded, not yet submitted -- listen back / re-record
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

  const [micLevel, setMicLevel] = useState(0); // 0-100, live meter display only
  const [micTooQuiet, setMicTooQuiet] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const captureSessionIdRef = useRef<string | null>(null);
  const sampleStartedAtRef = useRef<number>(0);
  const pendingSampleRef = useRef<{
    blob: Blob;
    durationSeconds: number;
    peakDbfs: number | null;
  } | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const meterRafRef = useRef<number | null>(null);
  const lowStreakRef = useRef(0);

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
      stopLevelMeter();
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantToken]);

  // --- Live mic-level meter (visual feedback only; not the safety gate) --
  async function startLevelMeter(stream: MediaStream) {
    const AudioContextCtor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const audioCtx = new AudioContextCtor();
    // Creating this context after the getUserMedia() await above (which can
    // block on the permission prompt) can lose the browser's transient user
    // -activation window, so the context may come back suspended -- which
    // silently starves the analyser of samples and makes the meter look
    // stuck at zero / falsely report "too quiet" even while the mic is
    // capturing fine. Explicitly resume it before wiring anything up.
    if (audioCtx.state === "suspended") await audioCtx.resume();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    // An AnalyserNode with no further outgoing connection isn't reliably
    // pulled through the render graph in every browser, so it can silently
    // never process samples even though the mic and MediaRecorder are both
    // working fine -- route it through a zero-gain node into the
    // destination so it's part of the active graph without being audible.
    const silentGain = audioCtx.createGain();
    silentGain.gain.value = 0;
    analyser.connect(silentGain);
    silentGain.connect(audioCtx.destination);
    audioCtxRef.current = audioCtx;
    analyserRef.current = analyser;
    lowStreakRef.current = 0;

    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sumSquares += v * v;
      }
      const rms = Math.sqrt(sumSquares / data.length);
      setMicLevel(Math.min(100, Math.round(rms * 320)));
      lowStreakRef.current = rms < LIVE_METER_LOW_RMS ? lowStreakRef.current + 1 : 0;
      setMicTooQuiet(lowStreakRef.current > LIVE_METER_LOW_SUSTAIN_FRAMES);
      meterRafRef.current = requestAnimationFrame(tick);
    };
    tick();
  }

  function stopLevelMeter() {
    if (meterRafRef.current !== null) cancelAnimationFrame(meterRafRef.current);
    meterRafRef.current = null;
    analyserRef.current = null;
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    setMicLevel(0);
    setMicTooQuiet(false);
  }

  // Decodes the just-recorded clip and returns its peak level in dBFS, or
  // null if it couldn't be measured client-side (backend still enforces
  // the real check either way).
  async function computePeakDbfs(blob: Blob): Promise<number | null> {
    try {
      const arrayBuffer = await blob.arrayBuffer();
      const AudioContextCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioContextCtor();
      const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
      let peak = 0;
      for (let ch = 0; ch < audioBuffer.numberOfChannels; ch++) {
        const channelData = audioBuffer.getChannelData(ch);
        for (let i = 0; i < channelData.length; i++) {
          const abs = Math.abs(channelData[i]);
          if (abs > peak) peak = abs;
        }
      }
      await audioCtx.close();
      return peak <= 0 ? -Infinity : 20 * Math.log10(peak);
    } catch {
      return null;
    }
  }

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
      await startLevelMeter(stream);
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
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    const durationSeconds = (Date.now() - sampleStartedAtRef.current) / 1000;
    stopLevelMeter();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    const peakDbfs = await computePeakDbfs(blob);
    if (peakDbfs !== null && peakDbfs < MIN_SAMPLE_PEAK_DBFS) {
      setPhase("ready-to-record");
      setRecordError(
        "That recording sounds silent or extremely quiet. Check your microphone (input " +
          "device, mute, and volume) and record again, speaking clearly."
      );
      return;
    }

    // Let the participant listen back before it's submitted -- catches a
    // technically-valid (non-silent, long-enough) clip that still doesn't
    // actually sound like a usable recording (wrong input device, heavy
    // noise, clipped/garbled audio) before wasting an upload + clone attempt.
    pendingSampleRef.current = { blob, durationSeconds, peakDbfs };
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(blob);
    });
    setPhase("reviewing");
  }

  async function submitPendingSample() {
    if (!participant || !captureSessionIdRef.current || !pendingSampleRef.current) return;
    const { blob, durationSeconds, peakDbfs } = pendingSampleRef.current;
    setPhase("uploading");
    try {
      await api.submitAudioSample(
        participant.id,
        captureSessionIdRef.current,
        blob,
        durationSeconds,
        peakDbfs ?? undefined
      );
      pendingSampleRef.current = null;
      setPreviewUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return null;
      });
      await refresh();
    } catch (e) {
      // Keep the pending sample around so they can retry the upload without
      // re-recording (e.g. a transient network error).
      setPhase("reviewing");
      setRecordError(e instanceof Error ? e.message : "Failed to upload your voice sample.");
    }
  }

  function handleReRecordSample() {
    pendingSampleRef.current = null;
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    setRecordError(null);
    // Safety requirement #14 needs the phrase + sample recorded together in
    // one continuous capture, so re-recording restarts from the top rather
    // than just retrying the sample half.
    setPhase("ready-to-record");
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
        phase === "reviewing" ||
        phase === "uploading") && (
        <div className="card">
          <div className="banner ok">You have consented.</div>

          <div className="banner warn">
            Recording only happens live through your browser&apos;s microphone. There is no upload
            option and no way to submit a pre-existing audio file.
          </div>

          {recordError && <div className="banner danger">{recordError}</div>}

          {(phase === "recording-phrase" || phase === "recording-sample") && (
            <>
              <label>Microphone input level</label>
              <div className="mic-meter">
                <div
                  className={`mic-meter-fill${micTooQuiet ? " low" : ""}`}
                  style={{ width: `${micLevel}%` }}
                />
              </div>
              {micTooQuiet && (
                <div className="banner warn">
                  Your microphone seems very quiet or muted. Move closer, check your input volume,
                  or confirm the right microphone is selected.
                </div>
              )}
            </>
          )}

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

          {phase === "reviewing" && previewUrl && (
            <>
              <h2>Listen back before submitting</h2>
              <p>
                Play this back to make sure your voice was actually captured -- clear, at a normal
                volume, and not silent, muffled, or cut off. If it doesn&apos;t sound right, re-record
                instead of submitting it.
              </p>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio className="sample-preview" controls src={previewUrl} />
              <div className="row">
                <button className="secondary" onClick={handleReRecordSample}>
                  Re-record
                </button>
                <button onClick={submitPendingSample}>Use this recording</button>
              </div>
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

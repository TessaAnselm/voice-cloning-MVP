"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, SessionOut } from "@/lib/api";

function formatTime(iso: string | null) {
  if (!iso) return "--";
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString();
}

function ConsentBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

export default function HostDashboardPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [newName, setNewName] = useState("");
  const [addingParticipant, setAddingParticipant] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await api.getSession(sessionId);
      setSession(s);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setNotFound(true);
      }
    }
  }, [sessionId]);

  useEffect(() => {
    refresh();
    // Consent status, audio sample status, and blocked-attempt counts can
    // change from another browser tab (the participant's device), so the
    // host dashboard polls rather than relying on a one-time fetch.
    const interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, [refresh]);

  async function handleAddParticipant() {
    if (!newName.trim()) return;
    setAddingParticipant(true);
    setError(null);
    try {
      await api.addParticipant(sessionId, newName.trim());
      setNewName("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add participant.");
    } finally {
      setAddingParticipant(false);
    }
  }

  async function handleEndSession() {
    if (!confirm("End this session? This immediately and permanently deletes all consent records, voice samples, and generated clips for every participant.")) {
      return;
    }
    setEnding(true);
    try {
      await api.endSession(sessionId);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to end session.");
      setEnding(false);
    }
  }

  if (notFound) {
    return (
      <main className="container">
        <div className="banner danger">
          This session was not found. It may have already expired or been ended by the host --
          all of its data has been permanently deleted.
        </div>
        <Link href="/">Create a new session</Link>
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
      <h1>Host dashboard</h1>
      <p className="subtitle">
        Session <code>{session.id}</code> &middot; expires {formatTime(session.expires_at)}
      </p>

      {!session.is_active && (
        <div className="banner danger">This session has ended or expired. All data has been purged.</div>
      )}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Blocked generation attempts</h2>
          <span className="badge revoked" style={{ fontSize: 15 }}>
            {session.blocked_generation_count}
          </span>
        </div>
        <p className="subtitle" style={{ fontSize: 13, marginBottom: 0 }}>
          Every request that fails the consent check or the content filter is logged here, never
          silently dropped.
        </p>
      </div>

      <div className="card">
        <h2>Add a participant</h2>
        <p className="subtitle" style={{ fontSize: 13 }}>
          Only add people who are physically present with you right now and who will personally
          open their own link to consent and record. Do not add or record anyone else.
        </p>
        <div className="row">
          <input
            type="text"
            placeholder="Participant name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddParticipant()}
            style={{ flex: 1, minWidth: 200 }}
          />
          <button onClick={handleAddParticipant} disabled={addingParticipant || !session.is_active}>
            Add participant
          </button>
        </div>
        {error && <div className="banner danger" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      <div className="card">
        <h2>Participants</h2>
        {session.participants.length === 0 ? (
          <p className="subtitle">No participants yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Consent</th>
                <th>Voice sample</th>
                <th>Revoked</th>
                <th>Sample expires</th>
                <th>Participant link</th>
              </tr>
            </thead>
            <tbody>
              {session.participants.map((p) => (
                <tr key={p.id}>
                  <td>{p.display_name}</td>
                  <td>
                    <ConsentBadge status={p.consent_status} />
                  </td>
                  <td>{p.has_audio_sample ? "Recorded" : "Not recorded"}</td>
                  <td>{p.revoke_timestamp ? formatTime(p.revoke_timestamp) : "--"}</td>
                  <td>{formatTime(p.audio_sample_expires_at)}</td>
                  <td>
                    <div className="link-box">
                      <span>{`/participant/${p.participant_token}`}</span>
                      <a
                        href={`/participant/${p.participant_token}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <button className="secondary" style={{ padding: "4px 8px", fontSize: 12 }}>
                          Open link &rarr;
                        </button>
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="row" style={{ justifyContent: "space-between" }}>
        <Link href={`/host/${session.id}/generate`}>
          <button disabled={!session.is_active}>Go to voice generation &rarr;</button>
        </Link>
        <button className="danger" onClick={handleEndSession} disabled={ending || !session.is_active}>
          {ending ? "Ending..." : "End session (purge everything)"}
        </button>
      </div>
    </main>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

const TTL_PRESETS = [
  { label: "1 hour", seconds: 60 * 60 },
  { label: "24 hours (default)", seconds: 24 * 60 * 60 },
  { label: "3 days", seconds: 3 * 24 * 60 * 60 },
  { label: "7 days (max)", seconds: 7 * 24 * 60 * 60 },
];

export default function CreateSessionPage() {
  const router = useRouter();
  const [ttlSeconds, setTtlSeconds] = useState(24 * 60 * 60);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setLoading(true);
    setError(null);
    try {
      const session = await api.createSession(ttlSeconds);
      router.push(`/host/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session.");
      setLoading(false);
    }
  }

  return (
    <main className="container">
      <h1>Start a consent-based voice demo</h1>
      <p className="subtitle">
        This is a local, offline cybersecurity education proof-of-concept. Nothing leaves this
        machine. Every participant must explicitly consent before anything is recorded, and all
        session data is automatically deleted after the retention window below (or immediately when
        you end the session).
      </p>

      <div className="banner warn">
        This tool exists to teach how voice-cloning products work and what safeguards they need --
        not to impersonate anyone. Only add people who are physically present and who will
        personally consent on their own device. See the{" "}
        <a href="/safety">Safety &amp; Risks page</a>.
      </div>

      <div className="card">
        <h2>Data retention</h2>
        <div className="field">
          <label htmlFor="ttl">
            How long should consent records, voice samples, and generated clips be kept before
            they&apos;re automatically deleted?
          </label>
          <select
            id="ttl"
            value={ttlSeconds}
            onChange={(e) => setTtlSeconds(Number(e.target.value))}
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
            {TTL_PRESETS.map((p) => (
              <option key={p.seconds} value={p.seconds}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <p className="subtitle" style={{ fontSize: 13 }}>
          You can also end the session manually at any time from the host dashboard, which purges
          everything immediately.
        </p>

        {error && <div className="banner danger">{error}</div>}

        <button onClick={handleCreate} disabled={loading}>
          {loading ? "Creating..." : "Create session"}
        </button>
      </div>
    </main>
  );
}

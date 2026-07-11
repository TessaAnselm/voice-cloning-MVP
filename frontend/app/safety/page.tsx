export default function SafetyPage() {
  return (
    <main className="container">
      <h1>Safety &amp; risk explanation</h1>
      <p className="subtitle">
        This app is a cybersecurity education proof-of-concept. It exists to show how a
        consent-based voice-cloning product could be built, what could go wrong, and what
        safeguards are needed before this kind of technology is used for real.
      </p>

      <div className="card">
        <h2>How voice cloning can be misused</h2>
        <ul className="risk-list">
          <li>
            <strong>Scams and fraud:</strong> a cloned voice can be used to impersonate a family
            member in a fake emergency ("grandparent scam"), or a company executive authorizing a
            wire transfer.
          </li>
          <li>
            <strong>Impersonation:</strong> synthetic audio can be used to put words in someone
            else&apos;s mouth, including public figures, without their knowledge or consent.
          </li>
          <li>
            <strong>Social engineering:</strong> attackers can combine a cloned voice with urgency
            ("act now," "don&apos;t tell anyone") to bypass a target&apos;s normal skepticism.
          </li>
          <li>
            <strong>Financial fraud:</strong> voice clones can be used to authenticate to
            voice-based systems, authorize payments, or trick employees into transferring funds.
          </li>
          <li>
            <strong>Harassment and threats:</strong> a cloned voice can be used to create
            harassing, threatening, or defamatory audio attributed to someone who never said it.
          </li>
          <li>
            <strong>Misinformation:</strong> fabricated audio of public figures or officials can
            spread false statements that are hard to debunk once shared widely.
          </li>
          <li>
            <strong>Unauthorized recording:</strong> capturing someone&apos;s voice without their
            knowledge, even briefly, provides raw material for any of the above.
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>Safeguards included in this demo</h2>
        <ul className="risk-list">
          <li>Every participant must explicitly click a consent button before any recording starts.</li>
          <li>
            There is no hidden recording, no upload endpoint, and no way to import a pre-existing
            audio file -- only live, in-session microphone capture is ever accepted.
          </li>
          <li>
            The consent phrase and the reference sample are bound together as one uninterrupted
            capture (<code>capture_session_id</code>), rejected by the backend if they don&apos;t
            match.
          </li>
          <li>
            Consent, revocation, and audio-sample validity are enforced on the backend, not just
            hidden in the UI -- a modified frontend can&apos;t bypass these checks.
          </li>
          <li>
            Any generation request is passed through a content filter before reaching the voice
            provider, blocking language associated with financial fraud, one-time codes/passwords,
            urgency manipulation, threats/harassment, and impersonation of public figures or
            non-participants.
          </li>
          <li>Blocked attempts are logged and counted on the host dashboard, never silently dropped.</li>
          <li>Every generated clip includes a spoken disclosure identifying it as AI-generated.</li>
          <li>
            Participants can revoke consent or delete their voice sample at any time, immediately
            blocking further use.
          </li>
          <li>
            All session data (consent records, audio samples, generated clips) auto-expires on a
            configurable TTL and is purged immediately when the host ends the session.
          </li>
          <li>
            The fallback text-to-speech provider is clearly labeled as not cloning voices, and the
            UI warns whenever it&apos;s in use.
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>Safeguards that would still be missing in a real production system</h2>
        <ul className="risk-list">
          <li>
            <strong>The content filter here is a keyword/heuristic stub</strong>, not a
            production-grade classifier. It will miss creative phrasing, non-English text, and
            context-dependent abuse, and it is not audited by a trust &amp; safety team.
          </li>
          <li>
            <strong>No identity verification.</strong> This demo trusts that whoever is speaking
            into a participant&apos;s device is really that person -- a real product would need
            some form of liveness/identity check.
          </li>
          <li>
            <strong>No rate limiting, watermarking beyond the spoken disclosure, or provenance
            tracking</strong> (e.g. C2PA-style content credentials) that would let downstream
            systems verify a clip's synthetic origin even if the spoken disclosure is edited out.
          </li>
          <li>
            <strong>No authentication or access control</strong> on host/participant links beyond
            an unguessable token -- a real deployment would need real accounts, session
            authorization, and audit logging tied to a real identity.
          </li>
          <li>
            <strong>No abuse/appeal workflow, human review queue, or law-enforcement escalation
            path</strong> for blocked or reported misuse.
          </li>
          <li>
            <strong>No protection against the participant being coerced</strong> into pressing
            "consent" -- consent captured under duress is indistinguishable from real consent to
            this system.
          </li>
          <li>
            <strong>Local-only storage and transport are not hardened</strong> for a shared or
            multi-user server deployment (no encryption at rest, no per-tenant isolation).
          </li>
        </ul>
      </div>
    </main>
  );
}

# Security & Safety Documentation

This document describes the threat model this demo is built to teach,
the safeguards it implements, and the safeguards it deliberately does
**not** implement because they're out of scope for a local teaching tool.

If you are evaluating this codebase as a template for something you intend
to actually deploy with real people's voices: **don't**, without first
closing every gap in "Known gaps" below and getting a real security/legal
review. Voice cloning technology is directly usable for fraud,
impersonation, and harassment; treat it accordingly.

## Why this app exists

To make the mechanics of a consent-based voice-cloning product concrete
and inspectable: where consent is captured, where it's checked, where
content is filtered, where data expires, and where a fallback path is
disclosed instead of hidden. Every one of those mechanisms below is
implemented in code you can read, not just described.

## Misuse this technology enables (why the safeguards exist)

- **Scams / social engineering** -- e.g. a cloned voice used in a fake
  emergency call ("grandparent scam") or a fake executive authorizing a
  wire transfer.
- **Impersonation** -- putting fabricated words in someone's mouth,
  including public figures, without consent.
- **Financial fraud** -- voice clones used to authorize payments, bypass
  voice-based authentication, or manipulate employees into transferring
  funds.
- **Harassment / threats** -- fabricated audio attributed to someone who
  never said it.
- **Misinformation** -- fabricated statements from officials or public
  figures that are hard to debunk once shared.
- **Unauthorized recording** -- capturing someone's voice without their
  knowledge is the raw material for all of the above.

## Safeguards implemented in this codebase

Each item below names the actual enforcement point in the code, not just
a policy statement.

| Safeguard | Where it's enforced |
|---|---|
| No recording without an explicit consent click | `frontend/app/participant/[participantToken]/page.tsx` (UI gate) **and** `backend/app/routers/participants.py::submit_audio_sample` + `guards.py::require_consenting_participant` (server-side gate; UI cannot bypass this) |
| No hidden recording | The only recording UI (`.../record/page.tsx`) is only reachable after consent, uses only `MediaRecorder`, and starts recording only on an explicit button press |
| No upload / import path for voice data | No file input, no drag-and-drop, no URL/path import field anywhere in the codebase. `POST /participants/{id}/audio-sample` only accepts a live-captured multipart body. Verified by `backend/tests/test_no_upload_endpoint.py`, which walks the OpenAPI schema for forbidden route names |
| Consent phrase + reference sample bound to one continuous capture | Client generates one `capture_session_id` per continuous `getUserMedia()` session (`record/page.tsx`); backend rejects an audio-sample upload unless a `CaptureSession` row for that id + participant already has `consent_phrase_completed=True` and isn't `invalidated_at` (`participants.py::submit_audio_sample`, `models.py::CaptureSession.is_valid_for_sample`) |
| Consent enforced server-side, not just UI | `guards.py` -- every `/generate-voice` call re-validates consent, revocation, session activity, and audio-sample validity regardless of what the frontend already checked |
| Content filtering before generation | `content_filter.py::check_content()` runs before any provider call in `routers/generation.py::generate_voice`; the provider is structurally unreachable if this blocks |
| Blocked attempts logged, not dropped | Every blocked call (guard failure or filter failure) writes a `Generation` row with `blocked=True` and a reason; the host dashboard shows a live `COUNT()` of these |
| Spoken AI-disclosure on every clip | `generation_pipeline.py::run_generation()` always appends a synthesized disclosure clip after the provider output, regardless of which provider ran -- providers cannot opt out because this happens outside them |
| Revocation / deletion always available | `POST /participants/{id}/revoke-consent`, `DELETE /participants/{id}/audio-sample`; both immediately block future generation via `guards.py` |
| Provider never called without a verified reference sample | `guards.py::require_usable_audio_sample` runs before the provider is invoked; each provider also independently raises `ReferenceAudioMissingError` if the path is missing, as defense in depth |
| Fallback provider clearly labeled, never default | `BrowserTTSProvider.name = "browser_tts_fallback"`; `generation_pipeline.py` only reaches for it when `LocalCloneProvider` raises `ProviderUnavailableError`; the API response includes `fallback_active` / `provider_used`, and the generation page renders a visible warning banner when it's true |
| Data auto-expires | `cleanup.py::sweep_expired()` runs on a background loop (`main.py`) and is also checked lazily on every relevant request (`guards.py::require_active_session`) |
| Ending a session purges immediately | `DELETE /sessions/{id}` calls `cleanup.py::purge_session()`, which deletes every audio file and generated clip from disk and cascades the DB rows (participants, capture sessions, audio samples, generations) |
| No public-figure impersonation feature | The content filter blocks known public-figure/authority phrasing (`content_filter.py::_PUBLIC_FIGURE_INDICATORS`); there's no persona/celebrity selector anywhere in the UI |
| No impersonation of non-participants | The filter flags `"this is <Name>"` / `"I am <Name>"` claims where `<Name>` isn't a session participant (`content_filter.py::_mentions_non_participant_name`) |

## Known gaps (do NOT treat this as production-ready)

Be explicit about these if you use this demo to teach -- they're the
punch list a real product would have to close:

- **The content filter is a keyword/heuristic stub**, documented as such
  in `content_filter.py`. It will miss creative phrasing, non-English
  text, homoglyphs, and context-dependent abuse. It has no human-in-the-loop
  review, no ML classifier, and no maintained deny-list process.
- **No identity verification.** The app trusts that whoever presses
  "consent" on a participant's device is that person. It cannot detect
  coercion, a shared/borrowed device, or someone consenting on another
  person's behalf.
- **No watermarking or provenance signal beyond the spoken disclosure.**
  If someone clips the disclosure out of a generated file, downstream
  systems have no way to detect it's synthetic (no C2PA-style content
  credentials, no inaudible watermark).
- **No authentication.** Host and participant links are unguessable
  tokens, not real accounts. Anyone with a link has full access to that
  role's actions. There's no audit trail tied to a real identity.
- **No rate limiting or abuse monitoring** beyond the blocked-attempt
  counter -- nothing throttles a host hammering `/generate-voice`, and
  there's no alerting/escalation path for repeated blocked attempts.
- **No encryption at rest** for the SQLite DB or stored audio files, and
  no multi-tenant isolation -- this is a single-user local tool.
- **Reference audio format is not deeply validated server-side.** The
  browser typically sends `audio/webm`; the backend checks the declared
  MIME type and size but does not transcode or deeply inspect the
  container/codec. A real deployment should validate/transcode
  server-side (e.g. via `ffmpeg`) rather than trusting the browser.
- **`FORCE_FALLBACK_PROVIDER`** exists purely for deterministic testing
  and must never be set `true` in anything resembling production.

## Data lifecycle summary

- Every session has `expires_at` set from its TTL at creation
  (`retention_ttl_seconds`, default 24h, bounded 5 min - 7 days).
- A background sweep (`CLEANUP_INTERVAL_SECONDS`, default 60s) purges any
  session past `expires_at` or with `ended_at` set, deleting its DB rows
  and every audio/generated file on disk.
- Individual audio samples also carry their own `expires_at` (capped to
  the session's) and are purged the same way even if the session itself
  hasn't expired yet.
- Nothing in this app is designed to persist beyond a session's TTL. If
  you need longer retention for a legitimate purpose, that decision (and
  its consent/legal implications) needs to be made explicitly -- this
  demo intentionally does not support it.

## Responsible use

Only use this demo with people who are physically present, who
personally operate their own device to consent and record, and who
understand it's a security-education exercise. Do not attempt to record
or synthesize the voice of anyone not actively, knowingly participating.
Do not use generated audio in any real communication, and do not remove
or rely on removing the spoken disclosure.

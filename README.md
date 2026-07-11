# Consent-Based Voice Cloning Demo

A local, offline proof-of-concept showing how a **consent-based** AI
voice-cloning product could be built for a cybersecurity education
demonstration -- and, just as importantly, what safeguards it needs.

**This is not a production product.** It is a teaching tool for showing
what such a product's consent, safety-filter, and data-retention plumbing
looks like end to end. Read [SECURITY.md](./SECURITY.md) before using it
with real people, even in a classroom setting.

## About this project

This app is a proof-of-concept exploring what a single prompt can produce
when handed to an AI coding tool -- built inside Visual Studio Code for
**404 Adult Supervision, Episode 1**.

404 Adult Supervision is a 3-person team where each member gives the same
prompt to a different AI coding tool and just runs with whatever it
builds, to see what actually comes out the other end.

## What this demo does

1. A host creates a local session with a configurable data-retention TTL
   (default 24h).
2. The host adds participant names and shares each participant's private
   link.
3. Each participant opens their own link, reads a plain-language consent
   disclosure, and explicitly clicks "I consent" -- **before anything is
   recorded**.
4. The participant then does **one continuous, live browser microphone
   recording**: first speaking a fixed consent phrase, then a short
   additional voice sample. There is no upload option anywhere.
5. The host dashboard shows live consent/audio-sample/revocation status
   and a running count of blocked generation attempts.
6. The host types a sentence and picks a consenting participant. The text
   is run through a content-safety filter before anything is generated.
7. If allowed, the app generates audio using **only that participant's own
   recorded sample**, with a spoken AI-disclosure appended to every clip.
8. Participants can revoke consent or delete their sample at any time.
   Ending a session (or letting its TTL lapse) immediately deletes
   everything for it.

## Tech stack

- **Frontend:** Next.js (App Router) + TypeScript
- **Backend:** FastAPI (Python)
- **Database:** SQLite (via SQLAlchemy)
- **Audio capture:** Browser `MediaRecorder` API only -- no file upload
  endpoint exists anywhere in the codebase
- **Voice generation:** `VoiceCloneProvider` interface with two
  implementations:
  - `LocalCloneProvider` (default): local, open-source zero-shot voice
    cloning via [Coqui XTTS-v2](https://github.com/coqui-ai/TTS). **Not
    installed by default** (heavy: torch + several GB of model weights) --
    see "Enabling real local voice cloning" below.
  - `BrowserTTSProvider` (fallback only, clearly labeled "does not clone
    voices" everywhere in the UI/logs): used automatically, with a visible
    warning, whenever `LocalCloneProvider` can't run.

## Project layout

```
voice_cloning/
  backend/
    app/
      main.py                    FastAPI app, CORS, background cleanup loop
      config.py                  All env-driven settings
      database.py, models.py     SQLAlchemy setup + tables
      schemas.py                 Pydantic request/response models
      content_filter.py          Keyword/heuristic safety filter (stub)
      guards.py                  Consent / audio-sample / session guards
      generation_pipeline.py     Wraps provider calls with disclosure embedding
      cleanup.py                 TTL expiration + purge-on-end logic
      speech.py, audio_utils.py  TTS + WAV helpers (stdlib-only)
      path_safety.py             Filesystem path-containment checks (CWE-23 hardening)
      serializers.py             DB row -> API response shaping
      providers/                 VoiceCloneProvider interface + 2 impls
      routers/                   sessions / participants / generation / health
    tests/  pytest suite (see "Tests" below)
    requirements.txt, .env.example, pytest.ini
  frontend/
    app/
      page.tsx                                 Create-session page
      host/[sessionId]/page.tsx                Host dashboard
      host/[sessionId]/generate/page.tsx       Voice generation page
      participant/[participantToken]/page.tsx  Consent + continuous recording (single page)
      safety/page.tsx                          Safety & risk explanation
    lib/api.ts  Typed API client
    lib/id.ts   crypto.randomUUID() fallback helper
    __tests__/  Jest/RTL safety-flow tests
  README.md, SECURITY.md
```

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional, defaults are already safe for local use
uvicorn app.main:app --reload --port 8000
```

The SQLite DB file and `storage/` directory are created automatically on
first run. Visit `http://localhost:8000/docs` for interactive API docs.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm run dev
```

Visit `http://localhost:3000`.

### 3. Try the flow

1. On `/`, create a session (pick a TTL or use the 24h default).
2. On the host dashboard, add one or more participants and copy each
   participant's link.
3. Open each participant link in a **separate browser tab/profile you
   control**, or on another device you own -- consent must always be given
   in person by the actual participant. Click "I consent," then record the
   consent phrase and a short sample back-to-back.
4. Back on the host dashboard, watch consent/audio status update, then go
   to "Voice generation," pick a participant, type a sentence, and
   generate.
5. Listen to the result -- note the spoken AI-disclosure at the end, and
   the on-screen warning if the fallback provider was used.
6. End the session (or let it expire) to see everything get purged.

### Out of the box, expect `BrowserTTSProvider` fallback

`LocalCloneProvider` (real voice cloning) requires the optional, heavy
`TTS` (Coqui) package and model weights, which are **not installed by
default**. Without them, every generation automatically and visibly falls
back to `BrowserTTSProvider`, which does **not** clone the participant's
voice -- it's generic placeholder speech, clearly labeled as such in the
UI, logs, and API response (`fallback_active: true`). This is intentional:
the app must never silently claim to be cloning a voice when it isn't.

### Enabling real local voice cloning (optional, verified working)

```bash
pip install torch torchaudio
pip install "coqui-tts[codec]"
pip install "transformers==4.57.6"   # see note below -- must run AFTER coqui-tts
```

Notes, in case your install hits the same snags this one did:

- `coqui-tts` does not pull in `torch`/`torchaudio` itself (platform-specific
  wheels vary too much), so install those first.
- `coqui-tts` needs the `[codec]` extra (pulls in `torchcodec`) for audio
  I/O on recent PyTorch versions, or `TTS.api` fails to import at all.
- As of coqui-tts 0.27.x, the XTTS code imports a helper
  (`isin_mps_friendly`) that was removed in `transformers>=5.0`. Pin
  `transformers==4.57.6` (or another `4.57.x` release) explicitly *after*
  installing `coqui-tts`, or `TTS.api` will raise `ImportError` on import.

On first `POST /generate-voice` call, Coqui will download the XTTS-v2
model weights (~1.9GB) to its local cache -- this can take a minute or two
and only happens once. The first download requires accepting Coqui's model
license non-interactively; if it hangs waiting for input, set
`COQUI_TOS_AGREED=1` in the backend's environment before starting
`uvicorn`. No audio or text ever leaves the machine either way. Once
installed, `LocalCloneProvider` becomes usable automatically -- no code
changes needed, and the generation response's `provider_used` field will
read `"local_clone"` instead of `"browser_tts_fallback"`.

### Spoken disclosure / fallback speech engine

The spoken disclosure appended to every clip (and `BrowserTTSProvider`'s
placeholder speech) tries, in order: the macOS `say` command, then the
optional `pyttsx3` package (Windows SAPI5 / Linux espeak), then a
non-speech tone placeholder if neither is available. The app never
crashes for lack of a TTS engine -- see `backend/app/speech.py`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # 25 tests
cd frontend && npx jest                           # safety-flow UI tests
```

The backend suite proves (among other things): generation is blocked
without consent / after revocation / without a sample; audio-sample
submission is rejected without a matching completed consent-phrase
capture; there is no upload/import endpoint; fraud/impersonation text is
blocked before the provider is called; blocked attempts are logged;
`LocalCloneProvider` is always tried first (never `BrowserTTSProvider` by
default); the fallback flag is surfaced in the API response; and session
data is fully purged both on TTL expiration and on host-initiated end.

## Safety

See [SECURITY.md](./SECURITY.md) for the full threat model, the
safeguards this demo implements, and what's still missing for real-world
production use.

## License

This project's own code (everything under `backend/app/`, `backend/tests/`,
`frontend/app/`, `frontend/lib/`, and `frontend/__tests__/`) is licensed
under the MIT license -- see [LICENSE](./LICENSE).

That code depends on third-party open-source libraries (FastAPI, Next.js,
React, Coqui TTS, PyTorch, and others) and, when `LocalCloneProvider` is
enabled, downloads the pretrained XTTS-v2 model. **The model weights are
covered by Coqui's own Public Model License (CPML), not this project's
MIT license, and CPML restricts commercial use.** See
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) for the full list of
dependencies, their licenses, and what each one is used for -- read that
before considering any use of this project beyond a local, educational
demo.

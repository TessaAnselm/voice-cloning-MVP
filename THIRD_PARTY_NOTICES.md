# Third-Party Notices

This project's own application code (session management, consent capture,
audio-capture flow, content filtering, guards, API routes, database
models, and the frontend UI) is original code written for this project
and is licensed under the MIT license in [LICENSE](./LICENSE).

That code depends on a number of third-party, open-source packages to do
its actual work -- there is no built-in web server, database engine,
audio toolkit, or machine-learning engine written from scratch here. This
file lists what those dependencies are, what they're used for, and under
what license each is distributed, so it's clear which parts of this
project are original and which are provided by other projects.

**The most important thing on this page** is the distinction in
["The voice-cloning model"](#the-voice-cloning-model) below: the
`coqui-tts` *code* is open source (MPL-2.0), but the *pretrained XTTS-v2
model weights* it downloads and runs are covered by a separate,
non-standard license (CPML) that restricts commercial use. Read that
section before using this project as the basis for anything beyond a
local, educational demo.

Versions below reflect what this project was built and tested against
(see `backend/requirements.txt`, `backend/requirements-lock.txt`, and
`frontend/package-lock.json` for exact pinned versions).

## Backend (Python)

| Package | Version | License | Purpose in this project |
|---|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | 0.139.0 | MIT | Web framework -- defines and serves every `/sessions`, `/participants`, `/generate-voice` route |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.13.4 | MIT | Validates request/response shapes (`app/schemas.py`) |
| [SQLAlchemy](https://www.sqlalchemy.org) | 2.0.51 | MIT | ORM for the SQLite database (`app/models.py`, `app/database.py`) |
| [Uvicorn](https://uvicorn.dev) | 0.51.0 | BSD-3-Clause | ASGI server that runs the FastAPI app locally |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.32 | Apache-2.0 | Parses the multipart form upload used for live-recorded audio samples |
| [pytest](https://docs.pytest.org) | 9.1.1 | MIT | Backend test suite (`backend/tests/`) |
| [httpx](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | HTTP client used by FastAPI's `TestClient` in tests |
| [pyttsx3](https://github.com/nateshmbhat/pyttsx3) | 2.99 | MPL-2.0 | Wraps the OS's built-in TTS engine; renders the spoken AI-disclosure and `BrowserTTSProvider`'s (non-cloning) fallback speech |

## The voice-cloning model

| Component | Version | License | Purpose in this project |
|---|---|---|---|
| [Coqui TTS](https://github.com/idiap/coqui-ai-TTS) (`coqui-tts` package) | 0.27.5 | MPL-2.0 | Software that loads and runs the XTTS-v2 model; `LocalCloneProvider` calls its `tts_to_file()` API with the participant's own reference sample |
| **XTTS-v2 model weights** | (downloaded at runtime) | **Coqui Public Model License (CPML)** | The pretrained neural network that actually performs zero-shot voice cloning |

This project did not create or train XTTS-v2 -- it integrates an
existing pretrained model via the open-source `coqui-tts` package. The
division of responsibility is:

- **This project's code** controls sessions, participants, consent,
  recording capture, the content-safety filter, disclosure embedding,
  and the UI/API around all of that.
- **`coqui-tts`** (open-source, MPL-2.0) is the software that loads a
  model and runs inference.
- **XTTS-v2's weights** (downloaded automatically the first time
  `LocalCloneProvider` runs, cached locally, never uploaded anywhere) are
  what actually performs the cloning -- and they are **not** covered by
  the same permissive license as the code around them.

**Read this before any deployment beyond a local demo:** the XTTS-v2
weights are distributed under Coqui's CPML, which restricts commercial
use of the model. Depending on the exact license terms in force at the
time (subject to change by Coqui -- check the current terms at the
model's [Hugging Face page](https://huggingface.co/coqui/XTTS-v2) before
relying on this), that can mean selling access to this application,
running it as a paid service, embedding it in a commercial product, or
using it for internal commercial operations may require a separate
commercial license from Coqui, even though `coqui-tts`'s own code is
freely open source. Using this project as a local, non-commercial,
educational demonstration -- which is what it's built for -- is a very
different situation from commercial deployment. Review the current CPML
terms yourself before doing the latter.

## Backend: supporting ML/audio libraries

These are transitive dependencies of `coqui-tts`, pulled in automatically
-- not something this project installs or configures directly, but part
of what actually runs when `LocalCloneProvider` generates audio.

| Package | Version | License | Purpose |
|---|---|---|---|
| [PyTorch](https://pytorch.org) | 2.13.0 | BSD-3-Clause (with some BSD/MIT/Apache-2.0 components) | Runs the neural network computation for XTTS-v2 |
| [torchaudio](https://github.com/pytorch/audio) | 2.11.0 | BSD-2-Clause | Audio I/O/processing that works with PyTorch tensors |
| [Hugging Face Transformers](https://github.com/huggingface/transformers) | 4.57.6 | Apache-2.0 | Provides model-loading components XTTS-v2 is built on |
| [librosa](https://librosa.org) | 0.11.0 | ISC | Audio loading, resampling, and feature extraction |
| [NumPy](https://numpy.org) | 2.4.6 | BSD-3-Clause | Array/numeric operations underlying the audio and model pipeline |
| [SciPy](https://scipy.org) | 1.18.0 | BSD-3-Clause | Scientific computing routines used by librosa/coqui-tts |

## Frontend (TypeScript/React)

| Package | Version | License | Purpose in this project |
|---|---|---|---|
| [Next.js](https://nextjs.org) | 14.2.35 | MIT | App Router, routing, dev server, and build pipeline for every page |
| [React](https://react.dev) | 18.3.1 | MIT | Renders the session/consent/recording/generation UI |
| [TypeScript](https://www.typescriptlang.org) | 5.9.3 | Apache-2.0 | Static typing across `lib/api.ts` and every page component |
| [Jest](https://jestjs.io) | 29.7.0 | MIT | Frontend test runner |
| [Testing Library](https://testing-library.com) (`@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`) | 16.3.2 / 6.9.1 / 14.6.1 | MIT | Renders components and simulates user interaction in `frontend/__tests__/` |

## What is NOT open source

- **macOS `say`** -- proprietary Apple system software, included with
  macOS. Used only as an optional first-choice tier for generating the
  spoken AI-disclosure and `BrowserTTSProvider`'s fallback speech (see
  `backend/app/speech.py`). It is not bundled with this project, not
  required for the core cloning feature, and simply isn't available on
  Windows/Linux -- the app falls back to `pyttsx3`, then a tone
  placeholder, on those platforms.
- **Snyk** -- a proprietary security-scanning SaaS product used during
  development to check this project's own code and dependencies for
  vulnerabilities. It is a development-time tool only; it is not a
  runtime dependency and is not part of what actually runs when someone
  uses the app.

## A note on provenance

This project's application code was generated specifically from the
requirements supplied in `prompt.txt` (preserved in this repo's git
history) and this conversation's follow-up requests -- it was not cloned
or forked from an existing voice-cloning application. That said, AI-
generated code reflects common patterns learned from public code and
documentation; "written from scratch for this project" describes how the
code was produced, not a formal guarantee of unique provenance for every
line. If that distinction matters for your use case (e.g. a legal
review), treat this as a starting point for that review, not a
substitute for it.

# Testing Findings

## Finding 1: Content filter false positive on "prime minister"

![Blocked by safety filter: message appears to impersonate a public figure or official authority, which this demo disallows. Safety label: blocked:public_figure_impersonation.](findings_media/false-positive-public-figure-filter.png)

**What happened:**
A generation request was blocked with safety_label
`blocked:public_figure_impersonation`. The blocked text was not an attempt
to impersonate anyone -- it was a participant telling a story that
happened to be offensive in content, not an impersonation attempt.

**Why it was a false positive:**
The content filter (`backend/app/content_filter.py`) matches text against
a hardcoded list of public-figure/authority phrases
(`_PUBLIC_FIGURE_INDICATORS`), which includes the raw pattern
`\bprime minister\b` with no surrounding context requirement (no "I am,"
"this is," or similar impersonation-claim wording needed). The blocked
sentence simply contained the words "prime minister" as part of a
story/narrative, not as a claim of being the prime minister. Because the
filter is a blunt keyword match rather than an impersonation-intent
check, any mention of that phrase -- descriptive, quoted, or narrative --
trips the same block as an actual impersonation attempt.

This is expected/documented behavior for a keyword-heuristic stub (see
the module docstring in `content_filter.py` and the "Known gaps" section
of `SECURITY.md`: "will miss creative phrasing... and context-dependent
abuse"), but it's worth recording as a concrete, reproduced example of
that limitation rather than just a theoretical caveat.

## Finding 2: No filtering for offensive language

The content filter has no category for offensive, vulgar, or otherwise
inappropriate language. Its categories only cover: financial/payment
requests, credential/OTP requests, urgency-manipulation phrasing,
threats/harassment, and public-figure or non-participant impersonation
(see `_CATEGORY_PATTERNS` in `content_filter.py`). Text that is offensive
in content but doesn't match one of those specific categories -- e.g. a
story or statement using offensive language, insults, or crude content
that isn't a threat and doesn't name a public figure -- passes through
the filter unblocked and can be sent to the voice provider and spoken in
the participant's cloned voice.

This is a real gap for the stated use case: the app currently only
screens for fraud/impersonation-shaped abuse, not general offensive or
inappropriate content, even though the generated audio speaks in a real
person's cloned voice.

## Finding 3: First recorded voice sample produced gibberish output, twice

**What happened:**
For one participant, the first recorded reference sample produced
unintelligible/gibberish cloned audio when used for generation. The
participant re-recorded their consent phrase + sample from scratch, and
the second attempt *also* produced gibberish. It only worked after
re-recording a third time.

**Likely cause:**
Not yet root-caused, but the most probable factors given how
`LocalCloneProvider` uses the sample (see
`backend/app/providers/local_clone.py`):
- The reference sample recorded by the browser (`audio/webm`, Opus) is
  passed to XTTS-v2 as `speaker_wav` completely unmodified -- there is no
  server-side validation of clip duration, silence trimming, or audio
  quality before it's used as a conditioning clip (see the "Known gaps"
  note in `SECURITY.md`: "Reference audio format is not deeply validated
  server-side"). A sample that's too short, has excess leading/trailing
  silence, or was captured at low volume/with background noise can produce
  a poor speaker embedding, which XTTS renders as garbled speech.
- Since consent-phrase + sample are recorded back-to-back in one
  continuous capture, background noise or a rushed/quiet delivery on the
  additional-sample segment specifically (as opposed to the phrase) isn't
  caught by anything -- there's no minimum-duration or audio-level check
  before the sample is accepted and marked usable.

**Gap this points to:**
The app currently accepts any live-recorded clip as a valid reference
sample as long as it's non-empty audio content under the size limit --
there is no minimum duration, silence/level check, or post-recording
preview/re-record prompt if the sample sounds unusable. A production
version should validate sample quality (minimum duration, non-silence)
before marking `sample_completed`, and ideally let the participant listen
back to their own recording before submitting it.

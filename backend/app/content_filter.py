"""
Content filter for host-submitted generation text.

*** THIS IS A KEYWORD/HEURISTIC STUB, NOT PRODUCTION-GRADE. ***
A real deployment would need an ML-based classifier, allow/deny lists
maintained by a trust & safety team, per-language coverage, and human
review of edge cases. This module exists to demonstrate WHERE such a
filter must sit in the pipeline (before the provider is ever called),
not to be a robust moderation system.

Safety requirement #16: this module is the single choke point every
generation request must pass through before app.providers is invoked.
Safety requirement #17: callers are responsible for logging blocked
attempts using the reason this module returns.
"""
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class FilterResult:
    blocked: bool
    label: str  # "ok" or "blocked:<category>"
    reason: Optional[str] = None


# --- Category keyword lists -------------------------------------------------
# Deliberately broad/blunt for a demo -- false positives are an acceptable
# trade-off for a safety stub; a production filter would need to be far
# more precise.

_FINANCIAL_PATTERNS = [
    r"\bwire transfer\b",
    r"\bwire (the|it|money|funds)\b",
    r"\brouting number\b",
    r"\baccount number\b",
    r"\bbank account\b",
    r"\bsend money\b",
    r"\bsend (\$|usd|cash)\b",
    r"\btransfer \$?\d",
    r"\bpayment authoriz",
    r"\bauthorize (the |a )?payment\b",
    r"\bgift card(s)?\b",
    r"\bcrypto(currency)? (wallet|transfer|payment)\b",
    r"\bvenmo\b|\bzelle\b|\bcash app\b|\bpaypal\b",
]

_CREDENTIAL_PATTERNS = [
    r"\bone[- ]time (code|password|pin)\b",
    r"\botp\b",
    r"\bverification code\b",
    r"\bpin (code|number)\b",
    r"\bpassword is\b",
    r"\byour password\b",
    r"\bsecurity code\b",
    r"\bssn\b|\bsocial security number\b",
]

_URGENCY_PATTERNS = [
    r"\bsend money now\b",
    r"\bact now\b",
    r"\bright away\b.*\b(money|payment|transfer|funds)\b",
    r"\burgent(ly)?\b.*\b(money|payment|transfer|wire|funds)\b",
    r"\bdo (this|it) immediately\b",
    r"\bdon'?t tell (anyone|him|her|them)\b",
]

_THREAT_HARASSMENT_PATTERNS = [
    r"\bi will (hurt|kill|find) you\b",
    r"\byou will pay\b",
    r"\bi know where you live\b",
    r"\bthreaten",
    r"\bharass",
    r"\bblackmail\b",
    r"\bexpose you\b",
]

# A small illustrative list of public-figure indicators. Not exhaustive --
# a real system would use a maintained named-entity list.
_PUBLIC_FIGURE_INDICATORS = [
    r"\bthe president\b",
    r"\bpresident (biden|trump|obama)\b",
    r"\bprime minister\b",
    r"\bthe pope\b",
    r"\belon musk\b",
    r"\bceo of (apple|google|microsoft|amazon|tesla|meta)\b",
    r"\bthis is (the )?(fbi|irs|police|911|the government)\b",
]

_CATEGORY_PATTERNS = [
    ("financial", _FINANCIAL_PATTERNS,
     "Message appears to request a financial transaction or payment authorization."),
    ("credentials", _CREDENTIAL_PATTERNS,
     "Message appears to request a one-time code, PIN, password, or similar secret."),
    ("urgency_manipulation", _URGENCY_PATTERNS,
     "Message uses urgent 'act now / send money' social-engineering language."),
    ("threat_harassment", _THREAT_HARASSMENT_PATTERNS,
     "Message appears to contain a threat or harassment."),
    ("public_figure_impersonation", _PUBLIC_FIGURE_INDICATORS,
     "Message appears to impersonate a public figure or official authority, which this demo disallows."),
]


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _mentions_non_participant_name(text: str, participant_names: List[str]) -> Optional[str]:
    """
    Heuristic: if the text says "I am <Name>" / "this is <Name>" for a name
    that is not one of the session's actual participants, flag it as an
    impersonation attempt. This is intentionally narrow (regex, not NLP) --
    see module docstring.
    """
    claim_patterns = [
        r"\bthis is ([A-Z][a-zA-Z]+)\b",
        r"\bi am ([A-Z][a-zA-Z]+)\b",
        r"\bi'm ([A-Z][a-zA-Z]+)\b",
        r"\bmy name is ([A-Z][a-zA-Z]+)\b",
    ]
    known_first_names = {n.strip().split()[0].lower() for n in participant_names if n.strip()}
    for pattern in claim_patterns:
        for match in re.finditer(pattern, text):
            claimed = match.group(1).strip().lower()
            if claimed and claimed not in known_first_names:
                return claimed
    return None


def check_content(text: str, session_participant_names: Optional[List[str]] = None) -> FilterResult:
    """
    Run `text` through the heuristic safety filter.

    session_participant_names lets the filter flag "this is <name>" claims
    for names that are not part of the demo session (requirement #16:
    "Attempts to impersonate someone who is not in the session participant
    list").
    """
    session_participant_names = session_participant_names or []
    normalized = text.strip()

    if not normalized:
        return FilterResult(blocked=True, label="blocked:empty", reason="Input text is empty.")

    for category, patterns, reason in _CATEGORY_PATTERNS:
        if _matches_any(normalized, patterns):
            return FilterResult(blocked=True, label=f"blocked:{category}", reason=reason)

    claimed_name = _mentions_non_participant_name(normalized, session_participant_names)
    if claimed_name:
        return FilterResult(
            blocked=True,
            label="blocked:non_participant_impersonation",
            reason=(
                f"Message claims an identity ('{claimed_name}') that is not a "
                "consenting participant in this session."
            ),
        )

    return FilterResult(blocked=False, label="ok", reason=None)

"""Pure quiz logic: request validation, qualification scoring, consent shape, event ids, hashing.
No I/O here; funnel/app.py wires it to the warehouse RPCs, CAPI, and Turnstile."""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from jsonschema import Draft202012Validator

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[a-z]{2,24}$", re.I)
EVENT_NAMES = ("QuizStart", "QuizComplete", "Schedule")
CONSENT_KEYS = ("tracking", "marketing", "verbatim_use")

# CRUCIBLE A12: disposable-email rejection on the quiz. Extend from the warehouse once abuse rows exist.
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.de", "sharklasers.com", "10minutemail.com",
    "10minutemail.net", "yopmail.com", "yopmail.fr", "tempmail.com", "temp-mail.org", "throwawaymail.com",
    "getnada.com", "dispostable.com", "trashmail.com", "maildrop.cc", "fakeinbox.com", "mailnesia.com",
    "tempr.email", "discard.email", "mohmal.com", "emailondeck.com", "spamgourmet.com", "mytemp.email",
})

_UTM_FIELDS = ("source", "medium", "campaign", "content", "term")

START_SCHEMA = {
    "type": "object",
    "required": ["client", "consent", "turnstile_token"],
    "additionalProperties": False,
    "properties": {
        "client": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_-]{0,63}$"},
        "consent": {
            "type": "object",
            "required": ["tracking", "marketing", "verbatim_use"],
            "additionalProperties": False,
            "properties": {k: {"type": "boolean"} for k in CONSENT_KEYS},
        },
        "utm": {
            "type": "object",
            "additionalProperties": False,
            "properties": {k: {"type": "string", "maxLength": 200} for k in _UTM_FIELDS},
        },
        "fbclid": {"type": ["string", "null"], "maxLength": 512},
        "turnstile_token": {"type": "string", "minLength": 1, "maxLength": 4096},
    },
}

COMPLETE_SCHEMA = {
    "type": "object",
    "required": ["client", "lead_id", "answers", "contact", "turnstile_token"],
    "additionalProperties": False,
    "properties": {
        "client": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_-]{0,63}$"},
        "lead_id": {"type": "string", "pattern": UUID_RE.pattern},
        "answers": {"type": "object", "additionalProperties": {"type": "string", "maxLength": 200}, "maxProperties": 10},
        "contact": {
            "type": "object",
            "required": ["email"],
            "additionalProperties": False,
            "properties": {
                "email": {"type": "string", "maxLength": 254},
                "name": {"type": ["string", "null"], "maxLength": 120},
                "phone": {"type": ["string", "null"], "maxLength": 40},
            },
        },
        "turnstile_token": {"type": "string", "minLength": 1, "maxLength": 4096},
    },
}

_START = Draft202012Validator(START_SCHEMA)
_COMPLETE = Draft202012Validator(COMPLETE_SCHEMA)


class Invalid(ValueError):
    """A request body failed validation. The message is safe to return to the browser (no PII echoed)."""


def _first_error(validator: Draft202012Validator, body: Any) -> str | None:
    err = next(iter(sorted(validator.iter_errors(body), key=lambda e: list(e.path))), None)
    if err is None:
        return None
    where = "/".join(str(p) for p in err.path) or "body"
    return f"{where}: {err.validator} check failed"


def validate_start(body: Any) -> dict[str, Any]:
    msg = _first_error(_START, body)
    if msg:
        raise Invalid(msg)
    return body


def validate_complete(body: Any, quiz_config: dict[str, Any]) -> dict[str, Any]:
    """Shape check, then every configured question answered with one of its options and nothing else.
    Quiz answers are untrusted text (SKILL.md §4 rule 7): only whitelisted option strings reach the warehouse."""
    msg = _first_error(_COMPLETE, body)
    if msg:
        raise Invalid(msg)
    questions = {q["id"]: q for q in quiz_config.get("questions", []) if isinstance(q, dict) and "id" in q}
    answers = body["answers"]
    extra = sorted(set(answers) - set(questions))
    if extra:
        raise Invalid(f"answers/{extra[0]}: unknown question")
    for qid, q in questions.items():
        if qid not in answers:
            raise Invalid(f"answers/{qid}: missing")
        if answers[qid] not in q.get("options", []):
            raise Invalid(f"answers/{qid}: not one of the options")
    email = normalise_email(body["contact"]["email"])
    if not EMAIL_RE.match(email):
        raise Invalid("contact/email: not an email address")
    if email.rsplit("@", 1)[1] in DISPOSABLE_DOMAINS:
        raise Invalid("contact/email: disposable addresses are not accepted")
    body["contact"]["email"] = email
    return body


def normalise_email(email: str) -> str:
    return email.strip().lower()


def qualification_score(answers: dict[str, str], quiz_config: dict[str, Any]) -> float:
    """Sum of quiz_config.qualification[question_id][answer]; unlisted answers score 0 (FR-35)."""
    table = quiz_config.get("qualification") or {}
    total = 0.0
    for qid, answer in answers.items():
        weights = table.get(qid) or {}
        value = weights.get(answer, 0)
        total += float(value) if isinstance(value, (int, float)) else 0.0
    return total


def hard_mode(quiz_config: dict[str, Any]) -> tuple[bool, float]:
    """(enabled, threshold). Off unless `qualification_mode` is exactly 'hard' (FR-35: default off)."""
    enabled = quiz_config.get("qualification_mode") == "hard"
    threshold = quiz_config.get("qualification_threshold", 0)
    return enabled, float(threshold) if isinstance(threshold, (int, float)) else 0.0


def qualifies(score: float, quiz_config: dict[str, Any]) -> bool:
    enabled, threshold = hard_mode(quiz_config)
    return True if not enabled else score >= threshold


def event_id(lead_id: str, event_name: str) -> str:
    """One id per (lead, event): the browser pixel and the server both use it, so Meta deduplicates."""
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unknown event {event_name!r}")
    return f"{lead_id}:{event_name}"


def hash_fbclid(fbclid: str | None) -> str | None:
    """sha256 hex of the raw fbclid; the raw value is never stored (DR-4). Case is significant, so no lowercasing."""
    if not fbclid:
        return None
    return hashlib.sha256(fbclid.strip().encode()).hexdigest()


def fbc_param(fbclid: str | None, now_ms: int) -> str | None:
    """Meta's `fbc` user_data field: fb.1.<creation ms>.<fbclid>, sent in-flight to CAPI, never stored."""
    return f"fb.1.{now_ms}.{fbclid.strip()}" if fbclid else None


def utm_from_query(query: dict[str, str]) -> dict[str, str]:
    return {k: query[f"utm_{k}"][:200] for k in _UTM_FIELDS if query.get(f"utm_{k}")}


def consent_record(consent: dict[str, Any], notice_version: str) -> dict[str, Any]:
    return {**{k: bool(consent.get(k)) for k in CONSENT_KEYS}, "notice_version": notice_version}


def cal_signature(secret: str, raw_body: bytes) -> str:
    """Cal.com signs the raw body with HMAC-SHA256 of the webhook secret, hex, in X-Cal-Signature-256."""
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def cal_signature_ok(secret: str, raw_body: bytes, header: str | None) -> bool:
    if not header or not secret:
        return False
    return hmac.compare_digest(cal_signature(secret, raw_body), header.strip().lower())


def booking_lead_id(payload: dict[str, Any]) -> str | None:
    """The lead id travels in the booking link (`?metadata[lead_id]=<uuid>`) and comes back in
    payload.metadata; a booking-question response named lead_id is accepted as a fallback."""
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    candidates = []
    meta = body.get("metadata")
    if isinstance(meta, dict):
        candidates.append(meta.get("lead_id"))
    responses = body.get("responses")
    if isinstance(responses, dict):
        r = responses.get("lead_id")
        candidates.append(r.get("value") if isinstance(r, dict) else r)
    for c in candidates:
        if isinstance(c, str) and UUID_RE.match(c):
            return c.lower()
    return None


def booking_link(calendar_url: str | None, lead_id: str) -> str | None:
    if not calendar_url or not calendar_url.startswith(("http://", "https://")):
        return None
    sep = "&" if "?" in calendar_url else "?"
    return f"{calendar_url}{sep}metadata[lead_id]={lead_id}"

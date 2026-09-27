from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from recrbro.config import SESSION_TTL_HOURS, TURNSTILE_SECRET_KEY
from recrbro.db import create_session, create_user, get_user_by_email
from recrbro.models import User

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TERMS_VERSION = "2026-09-27"
PRIVACY_POLICY_VERSION = "2026-09-27"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return "scrypt$16384$8$1$" + base64.b64encode(salt + derived).decode("ascii")


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$"):
        return False
    try:
        _, n, r, p, payload = encoded.split("$", 4)
        decoded = base64.b64decode(payload)
        salt, expected = decoded[:16], decoded[16:]
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    create_session(
        user_id,
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
        datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
    )
    return token


def register_user(name: str, email: str, password: str) -> tuple[str, User]:
    normalized_email = email.strip().casefold()
    if "@" not in normalized_email:
        raise ValueError("Enter a valid email address.")
    if get_user_by_email(normalized_email):
        raise ValueError("An account with this email already exists.")
    user = create_user(
        name.strip(),
        normalized_email,
        hash_password(password),
        terms_version=TERMS_VERSION,
        privacy_policy_version=PRIVACY_POLICY_VERSION,
    )
    return issue_session(user.id), user


def login_user(email: str, password: str) -> tuple[str, User]:
    user_and_hash = get_user_by_email(email.strip().casefold(), include_password=True)
    if user_and_hash is None or not verify_password(password, user_and_hash[1]):
        raise ValueError("Invalid email or password.")
    user, _ = user_and_hash
    return issue_session(user.id), user


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    if not TURNSTILE_SECRET_KEY:
        raise RuntimeError("CAPTCHA verification is not configured.")
    fields = {"secret": TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    request = Request(
        TURNSTILE_VERIFY_URL,
        data=urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        JSONDecodeError,
        UnicodeError,
    ) as error:
        raise RuntimeError(
            "CAPTCHA verification is temporarily unavailable."
        ) from error
    if not isinstance(result, dict):
        raise RuntimeError("CAPTCHA verification returned an invalid response.")
    return result.get("success") is True and result.get("action") == "register"

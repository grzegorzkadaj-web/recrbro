from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from recrbro.config import (
    APP_SECRET,
    FRONTEND_ORIGIN,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    SESSION_TTL_HOURS,
)
from recrbro.db import (
    create_session,
    create_user,
    get_user_by_email,
    set_google_identity,
)
from recrbro.models import User


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
    user = create_user(name.strip(), normalized_email, hash_password(password))
    return issue_session(user.id), user


def login_user(email: str, password: str) -> tuple[str, User]:
    user_and_hash = get_user_by_email(email.strip().casefold(), include_password=True)
    if user_and_hash is None or not verify_password(password, user_and_hash[1]):
        raise ValueError("Invalid email or password.")
    user, _ = user_and_hash
    return issue_session(user.id), user


def google_authorization_url(state: str) -> str:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Google sign-in is not configured.")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )


def create_oauth_state() -> str:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    nonce = secrets.token_urlsafe(16)
    value = f"{timestamp}.{nonce}"
    signature = hmac.new(
        APP_SECRET.encode(), value.encode(), hashlib.sha256
    ).hexdigest()
    return f"{value}.{signature}"


def verify_oauth_state(state: str) -> bool:
    try:
        timestamp, nonce, signature = state.split(".", 2)
        value = f"{timestamp}.{nonce}"
        expected = hmac.new(
            APP_SECRET.encode(), value.encode(), hashlib.sha256
        ).hexdigest()
        age = datetime.now(timezone.utc).timestamp() - int(timestamp)
    except (ValueError, TypeError):
        return False
    return 0 <= age <= 600 and hmac.compare_digest(signature, expected)


def authenticate_google(code: str) -> tuple[str, User]:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Google sign-in is not configured.")
    token_request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(token_request, timeout=20) as response:
        access_token = json.load(response)["access_token"]
    user_request = Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urlopen(user_request, timeout=20) as response:
        identity = json.load(response)
    if not identity.get("email") or not identity.get("email_verified"):
        raise ValueError("Google did not return a verified email address.")
    user = set_google_identity(
        str(identity["sub"]),
        str(identity.get("name") or identity["email"].split("@", 1)[0]),
        str(identity["email"]).casefold(),
    )
    return issue_session(user.id), user


def google_success_redirect(token: str) -> str:
    return f"{FRONTEND_ORIGIN}/#session={token}"

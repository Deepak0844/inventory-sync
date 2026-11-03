"""Reading the cookies out of a Chromium profile a person just logged in with.

Chromium keeps cookies that have no expiry on disk but throws them away when the profile is
opened again, and many Supplier logins use exactly those. So the cookie file is read
directly. Only Linux Chromium with `--password-store=basic` is supported: that store uses a
fixed key, which is why no keyring is needed. Not responsible for starting the browser
(`app.worker.real`) or for deciding whether the login worked.
"""

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_EPOCH_GAP_S = 11_644_473_600  # seconds from 1601 (Chromium's clock) to 1970 (Unix)
_SAMESITE = {0: "None", 1: "Lax", 2: "Strict"}  # -1 means "unspecified": leave it out
_QUERY = (
    "select host_key, name, value, encrypted_value, path, expires_utc, is_secure, "
    "is_httponly, has_expires, samesite from cookies"
)


class ProfileCookieError(Exception):
    """The profile's cookies could not be read or decrypted."""


def read_cookies(profile_dir: Path) -> list[dict[str, Any]]:
    """Return the profile's unexpired cookies in the shape Playwright's `add_cookies` takes.

    Cookies with no expiry are returned with `expires: -1` (a session cookie).

    Raises:
        ProfileCookieError: if there is no cookie file or a value cannot be decrypted.
    """
    path = profile_dir / "Default" / "Cookies"
    if not path.is_file():
        raise ProfileCookieError(f"no cookie file in the browser profile ({path.name})")
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = db.execute(_QUERY).fetchall()
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise ProfileCookieError("could not read the browser profile's cookie file") from exc
    now = time.time()
    cookies = []
    for host, name, plain, encrypted, cookie_path, expires, secure, httponly, has_exp, same in rows:
        expires_s = expires / 1_000_000 - _EPOCH_GAP_S if has_exp else -1
        if has_exp and expires_s <= now:
            continue
        cookie: dict[str, Any] = {
            "name": name,
            "value": _decrypt(encrypted, host) if encrypted else plain,
            "domain": host, "path": cookie_path, "expires": expires_s,
            "httpOnly": bool(httponly), "secure": bool(secure),
        }
        if same in _SAMESITE:
            cookie["sameSite"] = _SAMESITE[same]
        cookies.append(cookie)
    return cookies


def _decrypt(encrypted: bytes, host: str) -> str:
    """Decrypt one cookie value: `v10` + AES-128-CBC with Chromium's fixed "peanuts" key.

    Chromium 130+ puts a SHA-256 of the cookie's host in front of the value; it is dropped here.
    """
    if not encrypted.startswith(b"v10"):
        raise ProfileCookieError("could not decrypt a cookie (unknown encryption version)")
    try:
        key = PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1).derive(b"peanuts")
        decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
        padded = decryptor.update(encrypted[3:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
    except (ValueError, InvalidKey) as exc:
        raise ProfileCookieError("could not decrypt a cookie") from exc
    host_hash = hashlib.sha256(host.encode()).digest()
    if plain.startswith(host_hash):
        plain = plain[len(host_hash):]
    try:
        return plain.decode()
    except UnicodeDecodeError as exc:
        raise ProfileCookieError("could not decrypt a cookie (unreadable value)") from exc

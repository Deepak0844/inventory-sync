"""Reading a Linux Chromium profile's cookies, including the ones with no expiry."""

import hashlib
import sqlite3
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.flows.chromium_cookies import ProfileCookieError, read_cookies

EPOCH_GAP_S = 11_644_473_600  # seconds between 1601 (Chromium) and 1970 (Unix)


def encrypt(value: str, host: str, with_host_hash: bool = True) -> bytes:
    """Chromium's Linux "basic" store: v10 + AES-128-CBC, key from the fixed password "peanuts"."""
    key = PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1).derive(b"peanuts")
    plain = (hashlib.sha256(host.encode()).digest() if with_host_hash else b"") + value.encode()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + encryptor.update(padded) + encryptor.finalize()


def profile_with(tmp_path: Path, rows: list[tuple[object, ...]]) -> Path:
    (tmp_path / "Default").mkdir(parents=True)
    db = sqlite3.connect(tmp_path / "Default" / "Cookies")
    db.execute(
        "create table cookies (host_key text, name text, value text, encrypted_value blob, "
        "path text, expires_utc integer, is_secure integer, is_httponly integer, "
        "has_expires integer, samesite integer)")
    db.execute("create table meta (key text, value text)")
    db.execute("insert into meta values ('version', '24')")
    db.executemany("insert into cookies values (?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()
    return tmp_path


def in_one_hour() -> int:
    return int((time.time() + 3600 + EPOCH_GAP_S) * 1_000_000)


def test_a_cookie_with_no_expiry_is_read_as_a_session_cookie(tmp_path: Path) -> None:
    profile = profile_with(tmp_path, [
        (".shop.test", "session", "", encrypt("tok123", ".shop.test"), "/", 0, 1, 1, 0, 1)])
    [cookie] = read_cookies(profile)
    assert cookie == {"name": "session", "value": "tok123", "domain": ".shop.test", "path": "/",
                      "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax"}


def test_an_expiring_cookie_keeps_its_expiry_as_unix_seconds(tmp_path: Path) -> None:
    profile = profile_with(tmp_path, [
        ("shop.test", "keep", "", encrypt("v", "shop.test"), "/", in_one_hour(), 0, 0, 1, -1)])
    [cookie] = read_cookies(profile)
    assert abs(cookie["expires"] - (time.time() + 3600)) < 5
    assert "sameSite" not in cookie


def test_an_expired_cookie_is_left_out(tmp_path: Path) -> None:
    long_ago = int((time.time() - 3600 + EPOCH_GAP_S) * 1_000_000)
    profile = profile_with(tmp_path, [
        ("shop.test", "old", "", encrypt("v", "shop.test"), "/", long_ago, 0, 0, 1, -1)])
    assert read_cookies(profile) == []


def test_a_plain_value_and_an_older_chromium_without_the_host_hash_are_read(
    tmp_path: Path,
) -> None:
    profile = profile_with(tmp_path, [
        ("a.test", "plain", "visible", b"", "/", 0, 0, 0, 0, 0),
        ("b.test", "old", "", encrypt("legacy", "b.test", with_host_hash=False),
         "/", 0, 0, 0, 0, 2),
    ])
    by_name = {c["name"]: c for c in read_cookies(profile)}
    assert by_name["plain"]["value"] == "visible" and by_name["plain"]["sameSite"] == "None"
    assert by_name["old"]["value"] == "legacy" and by_name["old"]["sameSite"] == "Strict"


def test_a_profile_without_cookies_says_so(tmp_path: Path) -> None:
    with pytest.raises(ProfileCookieError, match="no cookie file"):
        read_cookies(tmp_path)


def test_a_value_that_cannot_be_decrypted_is_a_named_error(tmp_path: Path) -> None:
    profile = profile_with(tmp_path, [
        ("shop.test", "bad", "", b"v11notreallyencrypted....", "/", 0, 1, 1, 0, 1)])
    with pytest.raises(ProfileCookieError, match="decrypt"):
        read_cookies(profile)

import pytest

from app.core.encryption import DecryptionError, SecretBox, generate_key
from app.core.masking import mask_secrets


def test_encrypted_secret_round_trips() -> None:
    box = SecretBox(generate_key())
    assert box.decrypt(box.encrypt("hunter2")) == "hunter2"


def test_ciphertext_does_not_contain_plaintext() -> None:
    box = SecretBox(generate_key())
    assert "hunter2" not in box.encrypt("hunter2")


def test_decrypting_with_wrong_key_raises_specific_error() -> None:
    token = SecretBox(generate_key()).encrypt("hunter2")
    with pytest.raises(DecryptionError):
        SecretBox(generate_key()).decrypt(token)


def test_invalid_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        SecretBox("not-a-key")


def test_mask_secrets_replaces_every_occurrence() -> None:
    assert mask_secrets("login hunter2 then hunter2", ["hunter2"]) == "login *** then ***"


def test_mask_secrets_ignores_empty_secret() -> None:
    assert mask_secrets("abc", [""]) == "abc"


def test_mask_secrets_hides_longer_secret_that_contains_a_shorter_one() -> None:
    assert mask_secrets("token abcdef", ["abc", "abcdef"]) == "token ***"

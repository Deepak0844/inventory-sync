"""System-wide settings (one row). Secrets are encrypted and never in `SettingsRecord`."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.models import AppSettings

_PLAIN = {"shop_domain", "client_id", "mailbox_host", "mailbox_user", "kill_switch_percent",
          "kill_switch_max_flips", "sold_out_window_h", "order_poll_min"}


@dataclass(frozen=True)
class SettingsRecord:
    shop_domain: str
    client_id: str
    has_client_secret: bool
    mailbox_host: str
    mailbox_user: str
    has_mailbox_password: bool
    kill_switch_percent: float
    kill_switch_max_flips: int
    sold_out_window_h: int
    order_poll_min: int


@dataclass(frozen=True)
class SettingsSecrets:
    client_secret: str | None
    mailbox_password: str | None


class SettingsRepo:
    """The single `app_settings` row."""

    def __init__(self, session: Session, box: SecretBox) -> None:
        self._s = session
        self._box = box

    def get(self) -> SettingsRecord:
        """Return the settings, creating the row with defaults on first use."""
        r = self._row()
        return SettingsRecord(
            r.shop_domain, r.client_id, r.client_secret_enc is not None, r.mailbox_host,
            r.mailbox_user, r.mailbox_password_enc is not None, r.kill_switch_percent,
            r.kill_switch_max_flips, r.sold_out_window_h, r.order_poll_min)

    def update(self, **fields: Any) -> None:
        """Change the given fields. `client_secret` and `mailbox_password` are stored
        encrypted; leaving them out (or passing None) keeps the stored value.

        Raises:
            ValueError: for an unknown field.
        """
        row = self._row()
        for key, value in fields.items():
            if key == "client_secret" and value is not None:
                row.client_secret_enc = self._box.encrypt(value)
            elif key == "mailbox_password" and value is not None:
                row.mailbox_password_enc = self._box.encrypt(value)
            elif key in _PLAIN:
                setattr(row, key, value)
            elif key not in ("client_secret", "mailbox_password"):
                raise ValueError(f"unknown setting {key}")
        self._s.commit()

    def get_secrets(self) -> SettingsSecrets:
        """Decrypt the secrets for the Shopify client and the mailbox reader."""
        r = self._row()
        return SettingsSecrets(
            None if r.client_secret_enc is None else self._box.decrypt(r.client_secret_enc),
            None if r.mailbox_password_enc is None else self._box.decrypt(r.mailbox_password_enc))

    def _row(self) -> AppSettings:
        row = self._s.get(AppSettings, 1)
        if row is None:
            row = AppSettings(id=1)
            self._s.add(row)
            self._s.flush()
        return row

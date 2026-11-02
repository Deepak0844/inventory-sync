"""Reading recent mail from the dedicated mailbox over IMAP.

Not responsible for choosing which message holds the code (`app.mail.codes`).
Only the dedicated mailbox is ever opened, never the owner's own inbox.
"""

from datetime import UTC, datetime, timedelta

from imap_tools import AND, MailBox

from app.mail.codes import MailMessage


class MailboxError(Exception):
    """The mailbox could not be read."""


class ImapMailbox:
    """Fetches the last few minutes of mail with an app password."""

    def __init__(self, host: str, user: str, password: str, lookback: timedelta) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._lookback = lookback

    def recent_messages(self) -> list[MailMessage]:
        """Return messages received within the lookback window.

        Raises:
            MailboxError: if login or fetching fails. The password is never
                included in the message.
        """
        since = (datetime.now(UTC) - self._lookback).date()
        try:
            with MailBox(self._host).login(self._user, self._password) as mailbox:
                return [
                    MailMessage(
                        sender=message.from_,
                        body=message.text or message.html,
                        received_at=message.date.timestamp(),
                    )
                    for message in mailbox.fetch(AND(date_gte=since), mark_seen=False)
                ]
        except Exception as exc:  # imap_tools raises several unrelated types
            raise MailboxError(f"could not read mailbox {self._user}@{self._host}") from exc

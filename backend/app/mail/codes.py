"""Finding a Login Code in Supplier emails.

Not responsible for connecting to the mailbox; callers pass messages in.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from email.utils import parseaddr


class MailboxError(Exception):
    """The mailbox could not be read."""


@dataclass(frozen=True)
class MailMessage:
    """One email, reduced to what code extraction needs."""

    sender: str
    body: str
    received_at: float


def extract_login_code(
    messages: Iterable[MailMessage], sender: str, pattern: str, requested_at: float
) -> str | None:
    """Return the Login Code from the newest acceptable message, or None.

    A message is acceptable only if it is from `sender` and was received after
    `requested_at`, which stops an old code from being reused. `pattern` is the
    Supplier's regex; its first group is the code.
    """
    regex = re.compile(pattern)
    wanted = parseaddr(sender)[1].lower()
    for message in sorted(messages, key=lambda m: m.received_at, reverse=True):
        if parseaddr(message.sender)[1].lower() != wanted or message.received_at <= requested_at:
            continue
        match = regex.search(message.body)
        if match:
            return match.group(1)
    return None

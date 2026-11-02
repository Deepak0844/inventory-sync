"""Masking helper so secrets never reach logs, errors or screenshots' captions.

Not responsible for knowing which values are secret; callers pass them in.
"""

from collections.abc import Iterable

MASK = "***"


def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Return `text` with every occurrence of each secret replaced by `***`.

    Empty secrets are ignored, since replacing "" would mangle the text.
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, MASK)
    return text

"""What to do after a login attempt (PLAN.md section 4).

Pure function. Not responsible for pausing the Supplier or raising the
notification; callers act on the verdict.
"""

from dataclasses import dataclass
from enum import Enum
from typing import assert_never

from app.flows.results import LoginResult


class LoginAction(Enum):
    """The next step for the run."""

    DONE = "done"
    RETRY = "retry"
    PAUSE = "pause"
    CANCEL = "cancel"
    STOP = "stop"


@dataclass(frozen=True)
class LoginVerdict:
    """The action and the failed-attempt count to store."""

    failed_attempts: int
    action: LoginAction


def judge_login(result: LoginResult, failed_attempts: int, max_failed: int = 2) -> LoginVerdict:
    """Decide what follows a login result.

    Args:
        result: How the login ended.
        failed_attempts: Failed attempts so far in this run.
        max_failed: Failed attempts after which the Supplier is paused.

    Returns:
        DONE resets the count. A wrong code counts, and pauses at `max_failed`.
        Bad credentials count and pause at once, since retrying a wrong password
        risks a lockout. An unanswered prompt cancels the run without a failed
        attempt ("Needs code"). Blocked and browser or flow failures stop the
        run without a failed attempt; the Listings become Unknown.
    """
    match result:
        case LoginResult.LOGGED_IN | LoginResult.SESSION_REUSED:
            return LoginVerdict(0, LoginAction.DONE)
        case LoginResult.WRONG_CODE:
            count = failed_attempts + 1
            action = LoginAction.PAUSE if count >= max_failed else LoginAction.RETRY
            return LoginVerdict(count, action)
        case LoginResult.BAD_CREDENTIALS:
            return LoginVerdict(failed_attempts + 1, LoginAction.PAUSE)
        case LoginResult.CODE_TIMEOUT:
            return LoginVerdict(failed_attempts, LoginAction.CANCEL)
        case LoginResult.BLOCKED | LoginResult.BROWSER_ERROR | LoginResult.FLOW_FAILURE:
            return LoginVerdict(failed_attempts, LoginAction.STOP)
        case _:
            assert_never(result)

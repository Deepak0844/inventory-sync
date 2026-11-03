import pytest

from app.engine.login_policy import LoginAction, judge_login
from app.flows.results import LoginResult as R

EXPECTED: dict[R, LoginAction] = {
    R.LOGGED_IN: LoginAction.DONE,
    R.SESSION_REUSED: LoginAction.DONE,
    R.CODE_TIMEOUT: LoginAction.CANCEL,
    R.BLOCKED: LoginAction.STOP,
    R.BROWSER_ERROR: LoginAction.STOP,
    R.FLOW_FAILURE: LoginAction.STOP,
}


def test_every_login_result_has_a_verdict() -> None:
    for result in R:
        judge_login(result, 0)  # must not raise for a member added later


@pytest.mark.parametrize(("result", "action"), list(EXPECTED.items()))
def test_results_that_never_count_a_failed_attempt(result: R, action: LoginAction) -> None:
    verdict = judge_login(result, 1)
    assert verdict.action is action
    # Only success resets the count; the others leave it as it was.
    assert verdict.failed_attempts == (0 if action is LoginAction.DONE else 1)


def test_the_table_covers_every_result_except_the_two_that_count() -> None:
    assert set(EXPECTED) | {R.WRONG_CODE, R.BAD_CREDENTIALS} == set(R)


def test_first_wrong_code_retries() -> None:
    v = judge_login(R.WRONG_CODE, 0)
    assert (v.action, v.failed_attempts) == (LoginAction.RETRY, 1)


def test_second_wrong_code_pauses_the_supplier() -> None:
    v = judge_login(R.WRONG_CODE, 1)
    assert (v.action, v.failed_attempts) == (LoginAction.PAUSE, 2)


def test_max_failed_is_editable() -> None:
    assert judge_login(R.WRONG_CODE, 1, max_failed=3).action is LoginAction.RETRY


def test_bad_credentials_pause_at_once_and_count() -> None:
    v = judge_login(R.BAD_CREDENTIALS, 0)
    assert (v.action, v.failed_attempts) == (LoginAction.PAUSE, 1)


def test_success_resets_the_failed_attempts() -> None:
    assert judge_login(R.LOGGED_IN, 1).failed_attempts == 0


def test_unanswered_prompt_is_not_a_failed_attempt() -> None:
    assert judge_login(R.CODE_TIMEOUT, 1).failed_attempts == 1

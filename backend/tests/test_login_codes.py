from app.flows.login_codes import MailboxCodeSource, PastedCodeSource, await_login_code
from app.mail.codes import MailMessage, extract_login_code
from tests.fakes import FakeClock

SENDER = "no-reply@supplier.test"
PATTERN = r"code is (\d{6})"


def mail(body: str, at: float, sender: str = SENDER) -> MailMessage:
    return MailMessage(sender=sender, body=body, received_at=at)


def test_extracts_code_from_message_after_the_request() -> None:
    code = extract_login_code([mail("Your code is 111111", 105.0)], SENDER, PATTERN, 100.0)
    assert code == "111111"


def test_ignores_an_old_email_from_before_the_request() -> None:
    assert extract_login_code([mail("Your code is 111111", 90.0)], SENDER, PATTERN, 100.0) is None


def test_ignores_other_senders() -> None:
    other = mail("Your code is 111111", 105.0, sender="phisher@evil.test")
    assert extract_login_code([other], SENDER, PATTERN, 100.0) is None


def test_ignores_messages_without_a_code() -> None:
    assert extract_login_code([mail("Welcome!", 105.0)], SENDER, PATTERN, 100.0) is None


def test_newest_matching_message_wins() -> None:
    messages = [mail("Your code is 111111", 101.0), mail("Your code is 222222", 110.0)]
    assert extract_login_code(messages, SENDER, PATTERN, 100.0) == "222222"


def test_pasted_code_is_returned_once_then_never_reused() -> None:
    source = PastedCodeSource()
    source.submit("654321")
    assert source.poll(0.0) == "654321"
    assert source.poll(0.0) is None


def test_first_code_to_arrive_wins_and_the_other_is_discarded() -> None:
    clock = FakeClock()
    pasted = PastedCodeSource()
    pasted.submit("654321")
    mailbox = MailboxCodeSource(lambda: [mail("Your code is 111111", 5.0)], SENDER, PATTERN)
    result = await_login_code([pasted, mailbox], clock, requested_at=0.0, timeout=600, interval=5)
    assert result == "654321"


def test_code_arriving_later_is_found_on_a_later_poll() -> None:
    clock = FakeClock()
    inbox: list[MailMessage] = []

    def arriving() -> list[MailMessage]:
        if clock.now() >= 15:
            inbox.append(mail("Your code is 111111", clock.now()))
        return inbox

    mailbox = MailboxCodeSource(arriving, SENDER, PATTERN)
    result = await_login_code([mailbox], clock, requested_at=0.0, timeout=600, interval=5)
    assert result == "111111"
    assert clock.now() == 15


def test_returns_none_when_nothing_arrives_before_the_timeout() -> None:
    clock = FakeClock()
    sources = [PastedCodeSource()]
    result = await_login_code(sources, clock, requested_at=0.0, timeout=600, interval=5)
    assert result is None
    assert clock.now() >= 600

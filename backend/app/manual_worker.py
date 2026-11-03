"""Dedicated visible-browser worker for short manual login sessions."""

import logging
import signal
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.encryption import SecretBox
from app.worker.deps import Deps
from app.worker.jobs import Handler, run_once
from app.worker.manual_login import handle_manual_login
from app.worker.real import (
    RealShopifyFactory,
    chromium,
    headless_profile,
    imap_fetch,
    plain_chromium,
)

HANDLERS: dict[str, Handler] = {"manual_login": handle_manual_login}


def main() -> None:
    """Poll only manual-login jobs; the normal worker continues scheduled work."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    clock = SystemClock()
    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    deps = Deps(
        session_factory=sessionmaker(bind=engine),
        box=SecretBox(settings.encryption_key.get_secret_value()),
        clock=clock,
        browser=chromium,
        shopify=RealShopifyFactory(clock),
        mail=imap_fetch,
        manual_browser=plain_chromium,
        profile_browser=headless_profile,
        data_dir=settings.data_dir,
    )
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    logging.getLogger(__name__).info("manual browser worker started")
    while not stop.is_set():
        if not run_once(deps, HANDLERS):
            stop.wait(1.0)
    engine.dispose()


if __name__ == "__main__":
    main()

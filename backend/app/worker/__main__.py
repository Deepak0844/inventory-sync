"""`python -m app.worker`: run the scheduler and the job loop until told to stop."""

import logging
import signal
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.encryption import SecretBox
from app.worker.deps import Deps
from app.worker.jobs import serve
from app.worker.real import RealShopifyFactory, chromium, imap_fetch


def main() -> None:
    """Build the real dependencies and serve; SIGTERM or Ctrl-C finish the current job and exit."""
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
        data_dir=settings.data_dir,
    )
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    logging.getLogger(__name__).info("worker started")
    serve(deps, stop)
    logging.getLogger(__name__).info("worker stopped")


if __name__ == "__main__":
    main()

"""Command line tools. `python -m app.cli create-admin` makes the one dashboard login.

Not responsible for anything the running API does.
"""

import argparse
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import PostgresDatabase
from app.core.encryption import SecretBox
from app.services.auth import create_admin


def main(argv: list[str] | None = None) -> int:
    """Run a command. Returns the process exit code."""
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create the dashboard login")
    admin.add_argument("--username", default="owner")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        if len(password) < 12:
            print("Use a password of at least 12 characters.", file=sys.stderr)
            return 1
        settings = get_settings()
        database = PostgresDatabase(settings.database_url.get_secret_value())
        box = SecretBox(settings.encryption_key.get_secret_value())
        with sessionmaker(database.engine)() as session:
            setup = create_admin(session, box, args.username, password, datetime.now(UTC))
        print(f"TOTP secret (shown once): {setup.totp_secret}")
        print(f"Authenticator link: {setup.otpauth_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from app.core.database import PostgresDatabase


def test_ping_reports_false_when_database_is_unreachable() -> None:
    # Port 1 refuses connections immediately, so no server is needed.
    database = PostgresDatabase("postgresql+psycopg://u:p@127.0.0.1:1/x")
    assert database.ping() is False

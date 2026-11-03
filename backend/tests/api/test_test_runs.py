from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.repos.test_runs import FlowTestRunRepo
from tests.api.conftest import T0
from tests.fakes import sample_flow_dict

NEW = {"name": "Supplier A", "site_url": "https://a.example", "interval_min": 120}


def supplier(client: TestClient, *, credentials: bool = True, flow: bool = True) -> int:
    sid: int = client.post("/api/suppliers", json=NEW).json()["id"]
    if credentials:
        assert client.put(f"/api/suppliers/{sid}/credentials",
                          json={"username": "owner", "password": "s3cret"}).status_code == 204
    if flow:
        assert client.put(f"/api/suppliers/{sid}/flow", json=sample_flow_dict()).status_code == 200
    return sid


def post(client: TestClient, sid: int, **body: Any) -> Any:
    return client.post("/api/test-runs", json={"supplier_id": sid, "mode": "login", **body})


def jobs(factory: sessionmaker[Session]) -> list[tuple[str, int | None, dict[str, Any]]]:
    with factory() as session:
        rows = session.execute(text("SELECT kind, supplier_id, payload FROM jobs")).all()
    return [(r[0], r[1], r[2]) for r in rows]


def test_test_runs_need_a_session(client: TestClient) -> None:
    assert client.post("/api/test-runs", json={}).status_code == 401
    assert client.get("/api/test-runs/1").status_code == 401
    assert client.get("/api/test-runs/1/files/step-1.png").status_code == 401


def test_starting_a_run_queues_a_test_run_job(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    response = post(auth, sid)
    assert response.status_code == 202
    run_id = response.json()["id"]
    assert jobs(factory) == [("test_run", sid, {"test_run_id": run_id})]
    body = auth.get(f"/api/test-runs/{run_id}").json()
    assert body["state"] == "queued" and body["mode"] == "login" and body["steps"] == []
    assert body["wrote_to_shopify"] is False


def test_an_unknown_supplier_is_404(auth: TestClient) -> None:
    assert post(auth, 999).status_code == 404


def test_credentials_are_needed(auth: TestClient) -> None:
    response = post(auth, supplier(auth, credentials=False))
    assert response.status_code == 422 and "credentials" in str(response.json()).lower()


def test_a_flow_is_needed_from_the_draft_or_the_saved_one(auth: TestClient) -> None:
    sid = supplier(auth, flow=False)
    assert post(auth, sid).status_code == 422
    assert post(auth, sid, flow=sample_flow_dict()).status_code == 202


def test_an_invalid_draft_lists_every_problem_and_queues_nothing(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    draft = sample_flow_dict()
    draft["nodes"][1]["value"] = "{{credentials.usernam}}"
    del draft["nodes"][-1]
    response = post(auth, sid, flow=draft)
    assert response.status_code == 422
    assert len(response.json()["detail"]) >= 1
    assert jobs(factory) == []


def test_the_draft_is_what_the_worker_will_run(auth: TestClient) -> None:
    sid = supplier(auth)
    draft = sample_flow_dict()
    draft["extract"]["stock_selector"] = "#draft-only"
    run_id = post(auth, sid, flow=draft).json()["id"]
    with auth.app.state.session_factory() as session:  # type: ignore[attr-defined]
        run = FlowTestRunRepo(session).get(run_id)
    assert run is not None and run.request["flow"]["extract"]["stock_selector"] == "#draft-only"


def test_up_to_a_node_that_is_not_in_the_flow_is_rejected(auth: TestClient) -> None:
    response = post(auth, supplier(auth), up_to_node_id="nope")
    assert response.status_code == 422 and "nope" in str(response.json())


def test_up_to_a_real_node_is_accepted(auth: TestClient) -> None:
    sid = supplier(auth)
    assert post(auth, sid, up_to_node_id="n4").status_code == 202


def test_extract_needs_a_listing_url(auth: TestClient) -> None:
    sid = supplier(auth)
    assert post(auth, sid, mode="extract").status_code == 422
    assert post(auth, sid, mode="extract", listing_url="https://a.example/p/1").status_code == 202


def test_an_unknown_mode_is_rejected(auth: TestClient) -> None:
    assert post(auth, supplier(auth), mode="write-to-shopify").status_code == 422


def test_a_second_start_while_one_is_open_is_refused_with_the_open_runs_id(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    first = post(auth, sid).json()["id"]
    again = post(auth, sid, up_to_node_id="n4")
    assert again.status_code == 409
    assert again.json() == {"detail": "A test run is already in progress for this Supplier.",
                            "run_id": first}
    assert len(jobs(factory)) == 1


def test_a_bad_draft_is_a_422_even_while_a_run_is_open(auth: TestClient) -> None:
    sid = supplier(auth)
    assert post(auth, sid).status_code == 202
    assert post(auth, sid, flow={"supplier": ""}).status_code == 422


def test_a_run_stuck_open_for_over_30_minutes_does_not_block_a_new_one(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    first = post(auth, sid).json()["id"]
    with factory() as session:
        session.execute(
            text("UPDATE test_runs SET created_at = created_at - interval '31 minutes'"))
        session.commit()
    second = post(auth, sid)
    assert second.status_code == 202 and second.json()["id"] != first


def test_after_a_run_finishes_a_new_one_can_start(
    auth: TestClient, factory: sessionmaker[Session]
) -> None:
    sid = supplier(auth)
    first = post(auth, sid).json()["id"]
    with factory() as session:
        FlowTestRunRepo(session).finish(first, "done", T0)
    assert post(auth, sid).json()["id"] != first


def test_an_unknown_run_is_404(auth: TestClient) -> None:
    assert auth.get("/api/test-runs/999").status_code == 404


def finished_run(auth: TestClient, factory: sessionmaker[Session], data_dir: Path) -> int:
    sid = supplier(auth)
    run_id: int = post(auth, sid).json()["id"]
    folder = data_dir / "test-runs" / str(run_id)
    folder.mkdir(parents=True)
    (folder / "step-1.png").write_bytes(b"\x89PNG-step")
    (folder / "snapshot.png").write_bytes(b"\x89PNG-snap")
    (folder / "snapshot.html").write_text("<p>cleaned</p>")
    (data_dir / "secret.txt").write_text("not for the browser")
    url = f"/api/test-runs/{run_id}/files"
    with factory() as session:
        repo = FlowTestRunRepo(session)
        repo.add_step(run_id, {"node_id": "n1", "type": "goto", "ok": True, "error": None,
                               "screenshot_url": f"{url}/step-1.png", "at": T0.isoformat()})
        repo.finish(run_id, "done", T0, login_result="logged_in",
                    snapshot={"screenshot_url": f"{url}/snapshot.png",
                              "html_url": f"{url}/snapshot.html"},
                    reading={"result": "in_stock", "error_kind": None, "quantity": 3,
                             "matched_rule": "in_stock_if"})
    return run_id


def test_a_finished_run_reports_everything_the_contract_lists(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path
) -> None:
    run_id = finished_run(auth, factory, data_dir)
    body = auth.get(f"/api/test-runs/{run_id}").json()
    assert set(body) == {"id", "state", "mode", "steps", "snapshot", "reading", "login_result",
                         "error", "wrote_to_shopify"}
    assert body["steps"][0]["node_id"] == "n1" and body["login_result"] == "logged_in"
    assert body["reading"]["matched_rule"] == "in_stock_if"
    assert body["snapshot"]["html_url"].endswith("/snapshot.html")


def test_a_screenshot_is_served_as_a_png(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path
) -> None:
    run_id = finished_run(auth, factory, data_dir)
    response = auth.get(f"/api/test-runs/{run_id}/files/step-1.png")
    assert response.status_code == 200 and response.content == b"\x89PNG-step"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_the_snapshot_html_is_served_sandboxed(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path
) -> None:
    run_id = finished_run(auth, factory, data_dir)
    response = auth.get(f"/api/test-runs/{run_id}/files/snapshot.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    csp = response.headers["content-security-policy"]
    assert csp == "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name", [
    "secret.txt", "..%2fsecret.txt", "%2e%2e%2fsecret.txt", "step-1.png%2f..%2f..%2fsecret.txt",
    "step-2.png", "snapshot", "", "step-1.PNG", "step-1.png%00.txt",
])
def test_only_recorded_file_names_are_served(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path, name: str
) -> None:
    run_id = finished_run(auth, factory, data_dir)
    response = auth.get(f"/api/test-runs/{run_id}/files/{name}")
    assert response.status_code in (404, 422)
    assert b"not for the browser" not in response.content


def test_a_file_that_is_recorded_but_missing_on_disk_is_404(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path
) -> None:
    run_id = finished_run(auth, factory, data_dir)
    (data_dir / "test-runs" / str(run_id) / "step-1.png").unlink()
    assert auth.get(f"/api/test-runs/{run_id}/files/step-1.png").status_code == 404


def test_one_runs_files_are_not_served_under_another_runs_id(
    auth: TestClient, factory: sessionmaker[Session], data_dir: Path
) -> None:
    finished_run(auth, factory, data_dir)
    other_supplier = auth.post("/api/suppliers", json={**NEW, "name": "Supplier B"}).json()["id"]
    with factory() as session:
        other = FlowTestRunRepo(session).create(other_supplier, "login", {}, T0)
    assert auth.get(f"/api/test-runs/{other}/files/step-1.png").status_code == 404


def bare_draft() -> dict[str, Any]:
    """A fresh outline: nothing picked yet, so no stock selector."""
    draft = sample_flow_dict()
    draft["extract"]["stock_selector"] = ""
    return draft


def test_a_snapshot_of_the_first_page_needs_neither_credentials_nor_a_stock_selector(
    auth: TestClient,
) -> None:
    sid = supplier(auth, credentials=False, flow=False)
    assert post(auth, sid, flow=bare_draft(), up_to_node_id="n1").status_code == 202


def test_a_snapshot_after_a_step_that_types_the_password_still_needs_credentials(
    auth: TestClient,
) -> None:
    sid = supplier(auth, credentials=False, flow=False)
    response = post(auth, sid, flow=bare_draft(), up_to_node_id="n3")
    assert response.status_code == 422 and "credentials" in str(response.json()).lower()


def test_testing_a_listing_needs_the_stock_selector(auth: TestClient) -> None:
    sid = supplier(auth, flow=False)
    response = post(auth, sid, flow=bare_draft(), mode="extract",
                    listing_url="https://a.example/p/1")
    assert response.status_code == 422 and "stock element" in str(response.json()).lower()

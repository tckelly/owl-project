"""Rolling deploy: the previous step's code must serve correct traffic against this
step's schema, side by side with this step's code, on one database.

The DB is seeded (and so migrated to head) by *this* checkout; the previous step's
API runs from a git worktree. Each version's writes must read back correctly through
the other. Fields are compared on the step-0 API contract; commitments are compared
by parsed value, since later steps may normalise the text.
"""
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from app.commitment import parse_commitment

PREVIOUS_STEP = "main"

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
STEP0_FIELDS = (
    "fund_id", "fund_name", "manager", "strategy",
    "vintage_year", "commitment", "reported_at",
)


def free_port():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def serve(checkout, database_url):
    """Start `make serve` in a checkout; yield its base URL until torn down."""
    port = free_port()
    process = subprocess.Popen(
        ["make", "serve", f"PORT={port}", f"PY={PYTHON}"],
        cwd=checkout,
        env={**os.environ, "DATABASE_URL": database_url},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://localhost:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{url}/funds", timeout=1)
            return process, url
        except httpx.TransportError:
            time.sleep(0.1)
    os.killpg(process.pid, signal.SIGTERM)
    raise RuntimeError(f"API in {checkout} did not start")


@pytest.fixture
def previous_checkout(tmp_path):
    checkout = tmp_path / "previous"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(checkout), PREVIOUS_STEP],
        cwd=ROOT, check=True, capture_output=True,
    )
    yield checkout
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(checkout)],
        cwd=ROOT, check=True, capture_output=True,
    )


@pytest.fixture
def apis(seeded_db, previous_checkout):
    servers = [serve(previous_checkout, seeded_db), serve(ROOT, seeded_db)]
    yield tuple(httpx.Client(base_url=url) for _, url in servers)
    for process, _ in servers:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait()


def contract(fund):
    view = {field: fund[field] for field in STEP0_FIELDS}
    view["commitment"] = parse_commitment(view["commitment"])
    return view


def funds_by_id(api):
    response = api.get("/funds")
    assert response.status_code == 200
    return {fund["fund_id"]: contract(fund) for fund in response.json()}


def fund(fund_id, commitment):
    return {
        "fund_id": fund_id,
        "fund_name": f"Fund {fund_id}",
        "manager": "Rolling Advisors",
        "strategy": "Buyout",
        "vintage_year": 2024,
        "commitment": commitment,
        "reported_at": "2026-01-15",
    }


def test_previous_and_current_code_agree_on_one_database(apis):
    previous, current = apis
    assert funds_by_id(previous) == funds_by_id(current)
    assert len(funds_by_id(previous)) == 500

    writes = [
        (previous, "post", "/funds", fund("F-9001", "$2,500,000 USD")),
        (current, "post", "/funds", fund("F-9002", "£750,000.50 GBP")),
        (previous, "put", "/funds/F-1001", fund("F-1001", "EUR 3,000,000")),
        (current, "put", "/funds/F-1002", fund("F-1002", "~$9,000,000")),
        (current, "put", "/funds/F-1003", fund("F-1003", "Not reported")),
    ]
    for api, method, path, body in writes:
        response = getattr(api, method)(path, json=body)
        assert response.status_code in (200, 201), response.text

    expected = {body["fund_id"]: contract(body) for *_, body in writes}
    for api in (previous, current):
        listed = funds_by_id(api)
        assert len(listed) == 502
        for fund_id, view in expected.items():
            assert listed[fund_id] == view


def test_previous_step_is_found_in_a_fresh_clone(tmp_path):
    """A fresh clone has only the checked-out branch locally; others are origin/*."""
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--quiet")
    git("-c", "user.name=test", "-c", "user.email=test@example.com",
        "commit", "--allow-empty", "--quiet", "-m", "start")
    git("branch", "local-step")
    git("update-ref", "refs/remotes/origin/remote-step", "HEAD")

    assert branch_ref(tmp_path, "local-step") == "local-step"
    assert branch_ref(tmp_path, "remote-step") == "origin/remote-step"

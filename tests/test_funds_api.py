import csv
from pathlib import Path

from app.commitment import format_commitment, parse_commitment

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "funds.csv"


def csv_rows():
    with CSV_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


def as_served(fund):
    """The API serves commitment re-formatted from the parsed columns, plus both."""
    cents, currency = parse_commitment(fund["commitment"])
    return {
        **fund,
        "commitment": format_commitment(cents, currency),
        "commitment_cents": cents,
        "currency": currency,
    }


def test_list_funds_serves_every_csv_row_from_parsed_commitment_columns(client):
    response = client.get("/funds")

    assert response.status_code == 200
    funds = {fund["fund_id"]: fund for fund in response.json()}
    rows = csv_rows()
    assert len(funds) == len(rows) == 500
    for row in rows:
        assert funds[row["fund_id"]] == as_served({
            "fund_id": row["fund_id"],
            "fund_name": row["fund_name"],
            "manager": row["manager"],
            "strategy": row["strategy"],
            "vintage_year": int(row["vintage_year"]),
            "commitment": row["commitment"],
            "reported_at": row["reported_at"],
        })


NEW_FUND = {
    "fund_id": "F-9001",
    "fund_name": "Test Fund I",
    "manager": "Test Advisors",
    "strategy": "Buyout",
    "vintage_year": 2024,
    "commitment": "$2,500,000 USD",
    "reported_at": "2026-01-15",
}


def test_create_fund_stores_commitment_text_and_lists_it(client):
    response = client.post("/funds", json=NEW_FUND)

    assert response.status_code == 201
    assert response.json() == as_served(NEW_FUND)
    listed = {f["fund_id"]: f for f in client.get("/funds").json()}
    assert listed["F-9001"] == as_served(NEW_FUND)


def test_create_fund_with_existing_id_is_a_conflict(client):
    response = client.post("/funds", json={**NEW_FUND, "fund_id": "F-1001"})

    assert response.status_code == 409


def test_update_fund_replaces_its_fields(client):
    changes = {**NEW_FUND, "fund_id": "F-1001", "commitment": "£3,000,000 GBP"}

    response = client.put("/funds/F-1001", json=changes)

    assert response.status_code == 200
    assert response.json() == as_served(changes)
    listed = {f["fund_id"]: f for f in client.get("/funds").json()}
    assert listed["F-1001"] == as_served(changes)


def test_update_unknown_fund_is_not_found(client):
    response = client.put("/funds/F-0000", json={**NEW_FUND, "fund_id": "F-0000"})

    assert response.status_code == 404


def test_update_cannot_change_fund_id(client):
    response = client.put("/funds/F-1001", json={**NEW_FUND, "fund_id": "F-1002"})

    assert response.status_code == 422


def stored_commitment(database_url, fund_id):
    import psycopg

    with psycopg.connect(database_url) as conn:
        return conn.execute(
            "SELECT commitment, commitment_cents, currency FROM funds WHERE fund_id = %s",
            (fund_id,),
        ).fetchone()


def test_create_fund_dual_writes_commitment_text_and_parsed_columns(client, seeded_db):
    client.post("/funds", json={**NEW_FUND, "commitment": "~£1,250,000.50 gbp"})

    assert stored_commitment(seeded_db, "F-9001") == (
        "~£1,250,000.50 gbp", 125_000_050, "GBP",
    )


def test_update_fund_dual_writes_commitment_text_and_parsed_columns(client, seeded_db):
    client.put("/funds/F-1001", json={**NEW_FUND, "fund_id": "F-1001", "commitment": "JPY 5,000"})

    assert stored_commitment(seeded_db, "F-1001") == ("JPY 5,000", 500_000, "JPY")


def test_missing_commitment_dual_writes_nulls(client, seeded_db):
    client.post("/funds", json={**NEW_FUND, "commitment": "TBD"})

    assert stored_commitment(seeded_db, "F-9001") == ("TBD", None, None)


def test_create_fund_rejects_unparseable_commitment(client, seeded_db):
    response = client.post("/funds", json={**NEW_FUND, "commitment": "about 5m"})

    assert response.status_code == 422
    assert stored_commitment(seeded_db, "F-9001") is None


def test_update_fund_rejects_unparseable_commitment(client, seeded_db):
    response = client.put(
        "/funds/F-1001", json={**NEW_FUND, "fund_id": "F-1001", "commitment": "£1 USD"}
    )

    assert response.status_code == 422
    assert stored_commitment(seeded_db, "F-1001")[0] == "USD 10,000,000"


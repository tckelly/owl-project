import csv
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "funds.csv"


def csv_rows():
    with CSV_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


def test_list_funds_returns_every_csv_row_with_commitment_as_raw_text(client):
    response = client.get("/funds")

    assert response.status_code == 200
    funds = {fund["fund_id"]: fund for fund in response.json()}
    rows = csv_rows()
    assert len(funds) == len(rows) == 500
    for row in rows:
        assert funds[row["fund_id"]] == {
            "fund_id": row["fund_id"],
            "fund_name": row["fund_name"],
            "manager": row["manager"],
            "strategy": row["strategy"],
            "vintage_year": int(row["vintage_year"]),
            "commitment": row["commitment"],
            "reported_at": row["reported_at"],
        }

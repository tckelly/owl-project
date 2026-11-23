from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from app import db
from app.commitment import parse_commitment

app = FastAPI(title="Funds")


class Fund(BaseModel):
    fund_id: str
    fund_name: str
    manager: str
    strategy: str
    vintage_year: int
    commitment: str
    reported_at: date

    @field_validator("commitment")
    @classmethod
    def commitment_must_parse(cls, value):
        parse_commitment(value)  # ValueError -> 422
        return value


@app.get("/funds", response_model=list[Fund])
def list_funds():
    return db.list_funds()


@app.post("/funds", response_model=Fund, status_code=201)
def create_fund(fund: Fund):
    created = db.create_fund(fund.model_dump())
    if created is None:
        raise HTTPException(409, f"Fund {fund.fund_id} already exists")
    return created


@app.put("/funds/{fund_id}", response_model=Fund)
def update_fund(fund_id: str, fund: Fund):
    if fund.fund_id != fund_id:
        raise HTTPException(422, "fund_id in body must match the URL")
    updated = db.update_fund(fund.model_dump())
    if updated is None:
        raise HTTPException(404, f"Fund {fund_id} not found")
    return updated

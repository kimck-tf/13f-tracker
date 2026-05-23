"""JSON contract SSOT — Pydantic models shared by exporter and FastAPI server."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QuarterEntry(BaseModel):
    key: str        # "2024Q2"
    label: str      # "Q2'24"
    date: str       # "2024-06-30" (ISO)


class Manager(BaseModel):
    id: str
    name: str
    firm: str
    style: str
    color: str
    avatar: str
    note: str = ""


class Stock(BaseModel):
    t: str
    n: str
    s: str
    i: str | None = None
    mc: float | None = None
    px: list[float | None]
    yld: float | None = None


class Meta(BaseModel):
    generated_at: datetime
    latest_period: str
    data_version: str
    mgr_count: int
    stock_count: int
    llm_available: bool

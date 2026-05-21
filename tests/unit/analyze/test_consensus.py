from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    # 거장 3명, 같은 분기, 2명 신규 매수 + 1명 보유
    for cik in ("0000000001", "0000000002", "0000000003"):
        upsert_manager(c, {"cik": cik, "name": cik, "label": cik, "fund": "F",
                           "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    upsert_filing(c, {"accession_no": "a1", "cik": "0000000001", "form_type": "13F-HR",
                      "period_of_report": date(2024,3,31), "filed_at": date(2024,5,15),
                      "is_amendment": False})
    upsert_filing(c, {"accession_no": "a2", "cik": "0000000002", "form_type": "13F-HR",
                      "period_of_report": date(2024,3,31), "filed_at": date(2024,5,15),
                      "is_amendment": False})
    upsert_filing(c, {"accession_no": "a3", "cik": "0000000003", "form_type": "13F-HR",
                      "period_of_report": date(2024,3,31), "filed_at": date(2024,5,15),
                      "is_amendment": False})
    h = {"name_of_issuer": "Apple", "title_of_class": "COM", "value_usd": 1000,
         "shares": 10, "share_type": "SH", "put_call": ""}
    upsert_holdings(c, "a1", [{**h, "cusip": "037833100"}])
    upsert_holdings(c, "a2", [{**h, "cusip": "037833100"}])
    upsert_holdings(c, "a3", [{**h, "cusip": "037833100"}])
    # signals_quarterly에 가짜 change_type 데이터
    c.executemany(
        """INSERT INTO signals_quarterly
           (cik, cusip, period_of_report, change_type, weight_pct, conviction_score, continuity_score)
           VALUES (?, '037833100', DATE '2024-03-31', ?, 1.0, 1.0, 0.5)""",
        [("0000000001", "new"), ("0000000002", "new"), ("0000000003", "hold")],
    )
    yield c
    c.close()


def test_consensus_holder_count(conn):
    n = compute_consensus(conn)
    row = conn.execute(
        "SELECT holder_count, new_buy_count FROM consensus_quarterly WHERE cusip='037833100'"
    ).fetchone()
    assert row[0] == 3
    assert row[1] == 2  # 신규 매수 2명


def test_consensus_holder_ciks(conn):
    compute_consensus(conn)
    row = conn.execute(
        "SELECT holder_ciks FROM consensus_quarterly WHERE cusip='037833100'"
    ).fetchone()
    ciks = sorted(row[0].split(","))
    assert ciks == ["0000000001", "0000000002", "0000000003"]

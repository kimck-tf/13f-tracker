"""Resolve manager CIK from company_tickers.json. Spec §5.1-1b."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def resolve_cik_by_name(query: str, company_tickers: dict[str, Any]) -> str | None:
    """Case-insensitive substring match against company titles.
    Returns 10-digit zero-padded CIK or None.
    """
    q = query.upper()
    candidates: list[tuple[int, str]] = []  # (cik, title)
    for entry in company_tickers.values():
        title = (entry.get("title") or "").upper()
        if q in title:
            candidates.append((int(entry["cik_str"]), title))

    if not candidates:
        return None

    if len(candidates) > 1:
        # 정확 일치 우선
        exact = [(c, t) for c, t in candidates if t == q]
        if exact:
            candidates = exact
        else:
            logger.warning(
                "CIK resolve: '%s' matched %d entries; using first. Verify in managers.yaml.",
                query,
                len(candidates),
            )

    cik = candidates[0][0]
    return str(cik).zfill(10)


def resolve_missing_ciks(
    managers_yaml_path: Path, company_tickers: dict[str, Any]
) -> int:
    """managers.yaml에서 cik=null 항목을 in-place 해석. 해석된 항목 수 반환."""
    with managers_yaml_path.open("r", encoding="utf-8") as f:
        managers = yaml.safe_load(f)

    resolved = 0
    for m in managers:
        cik = m.get("cik")
        for value in [cik, *(m.get("extra_ciks") or [])]:
            if value and not isinstance(value, str):
                # YAML 1.1은 따옴표 없는 0~7 숫자열(0001061165)을 8진수 int로 읽는다.
                # 이 상태로 safe_dump하면 원래 CIK가 사라지므로 파일을 쓰기 전에 중단.
                raise ValueError(
                    f"managers.yaml {m.get('label')}: cik가 문자열이 아닌 {value!r}로 읽힘 — "
                    "따옴표로 감싼 10자리 문자열로 입력하세요 (예: cik: '0001061165')"
                )
        if cik:
            continue
        query = m.get("fund") or m.get("name")
        cik = resolve_cik_by_name(query, company_tickers)
        if cik:
            m["cik"] = cik
            resolved += 1
            logger.info("Resolved CIK for %s → %s", m["label"], cik)
        else:
            logger.warning("Could not resolve CIK for %s (query=%r)", m["label"], query)

    with managers_yaml_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(managers, f, allow_unicode=True, sort_keys=False)
    return resolved

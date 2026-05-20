"""13F information table XML parser. Spec §5.1-1d, §5.3."""
from __future__ import annotations

from datetime import date
from typing import Any

from lxml import etree


_UNIT_CHANGE_DATE = date(2023, 1, 3)  # Spec §5.3


def normalize_value(value_str: str, filed_at: date) -> int:
    """SEC 2023-01-03 경계로 천 달러 → 달러 정규화."""
    raw = int(value_str.strip())
    if filed_at < _UNIT_CHANGE_DATE:
        return raw * 1000
    return raw


def _lname(tag: str) -> str:
    """{ns}foo → foo 추출 (namespace 무시)."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _child_text(node, local_name: str) -> str | None:
    for child in node:
        if _lname(child.tag) == local_name:
            return (child.text or "").strip()
    return None


def _shrs_prn(node) -> tuple[int, str]:
    for child in node:
        if _lname(child.tag) == "shrsOrPrnAmt":
            shares = int((_child_text(child, "sshPrnamt") or "0").strip())
            stype = _child_text(child, "sshPrnamtType") or "SH"
            return shares, stype
    return 0, "SH"


def parse_information_table(xml_bytes: bytes, filed_at: date) -> list[dict[str, Any]]:
    """Parse 13F information table XML.

    Returns list of holding dicts with keys:
      cusip, name_of_issuer, title_of_class, value_usd, shares, share_type, put_call.
    """
    root = etree.fromstring(xml_bytes)
    out: list[dict[str, Any]] = []
    for info in root:
        if _lname(info.tag) != "infoTable":
            continue
        value_str = _child_text(info, "value") or "0"
        shares, stype = _shrs_prn(info)
        out.append(
            {
                "name_of_issuer": _child_text(info, "nameOfIssuer") or "",
                "title_of_class": (_child_text(info, "titleOfClass") or "").strip() or "",
                "cusip": (_child_text(info, "cusip") or "").strip(),
                "value_usd": normalize_value(value_str, filed_at),
                "shares": shares,
                "share_type": stype,
                "put_call": (_child_text(info, "putCall") or "").strip(),
            }
        )
    return out

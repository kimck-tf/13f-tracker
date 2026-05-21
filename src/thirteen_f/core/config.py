"""Settings loader — .env 기반 환경 변수 로딩."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_DEFAULT_GOOGLE_MODEL = "gemini-3-flash-preview"


def _parse_bool(val: str, default: bool) -> bool:
    """'true'/'1'/'yes'/'on' → True. 'false'/'0'/'no'/'off' → False. 비어있으면 default."""
    s = val.strip().strip('"').lower()
    if not s:
        return default
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class Settings:
    sec_user_agent: str
    openfigi_api_key: str
    duckdb_path: Path
    google_api_key: str = ""
    google_model: str = _DEFAULT_GOOGLE_MODEL
    gemini_thinking: bool = True


def load_settings() -> Settings:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    ua = os.environ.get("SEC_USER_AGENT", "").strip().strip('"')
    if not ua:
        raise ValueError(
            "SEC_USER_AGENT 미설정. .env에 'Name email@domain.com' 형식으로 입력하세요. "
            "(Spec §5.4: User-Agent 누락 시 SEC 403)"
        )
    return Settings(
        sec_user_agent=ua,
        openfigi_api_key=os.environ.get("OPENFIGI_API_KEY", "").strip().strip('"'),
        duckdb_path=Path(os.environ.get("DUCKDB_PATH", "data/13f.duckdb").strip().strip('"')),
        google_api_key=os.environ.get("GOOGLE_API_KEY", "").strip().strip('"'),
        google_model=(os.environ.get("GOOGLE_MODEL", "").strip().strip('"') or _DEFAULT_GOOGLE_MODEL),
        gemini_thinking=_parse_bool(os.environ.get("GEMINI_THINKING", ""), default=True),
    )

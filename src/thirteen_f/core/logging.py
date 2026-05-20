"""Rich console logger + file handler."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from rich.logging import RichHandler


def get_logger(name: str = "thirteen_f", log_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
    rich_handler.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(rich_handler)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / f"{date.today().isoformat()}.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(file_handler)
    return logger

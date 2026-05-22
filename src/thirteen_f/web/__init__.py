"""Web frontend backend module — FastAPI server + DuckDB→JSON exporter."""
from .queries import (
    backtest_curves_df,
    backtest_metrics_df,
    get_read_only_conn,
    latest_period,
    manager_history,
    manager_list,
    top_scores,
)

__all__ = [
    "latest_period",
    "manager_list",
    "top_scores",
    "manager_history",
    "backtest_curves_df",
    "backtest_metrics_df",
    "get_read_only_conn",
]

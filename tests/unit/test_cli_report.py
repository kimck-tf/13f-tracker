import importlib.util
import shutil

from typer.testing import CliRunner

from thirteen_f.cli import app


def test_report_exits_2_when_quarto_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    r = CliRunner().invoke(app, ["report", "--latest"])
    assert r.exit_code == 2 and "winget" in r.output


def test_report_exits_2_when_report_extra_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "C:/quarto/quarto.exe")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    r = CliRunner().invoke(app, ["report", "--latest"])
    assert r.exit_code == 2 and "--extra report" in r.output

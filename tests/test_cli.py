from typer.testing import CliRunner
from uspto.cli import app


runner = CliRunner()


def test_help_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "backfill" in result.stdout
    assert "monitor" in result.stdout
    assert "report" in result.stdout


def test_monitor_help_lists_format_flag():
    result = runner.invoke(app, ["monitor", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.stdout

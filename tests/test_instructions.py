"""HANDLE_INSTRUCTIONS_FILE: the household's own instructions after the built-in ones."""

import subprocess
import sys


def _server_instructions(env: dict) -> subprocess.CompletedProcess:
    code = "from handle_mcp.app import mcp; print(mcp.instructions)"
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_household_instructions_are_appended(tmp_path):
    rules = tmp_path / "instructions.md"
    rules.write_text("Shopping lists live in KitchenOwl.\n", encoding="utf-8")
    result = _server_instructions({"HANDLE_INSTRUCTIONS_FILE": str(rules), "PATH": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Tools for Danish grocery stores")
    assert result.stdout.rstrip().endswith("\n\nShopping lists live in KitchenOwl.")


def test_an_unreadable_instructions_file_stops_the_server(tmp_path):
    result = _server_instructions({"HANDLE_INSTRUCTIONS_FILE": str(tmp_path / "missing.md")})
    assert result.returncode != 0
    assert "HANDLE_INSTRUCTIONS_FILE=" in result.stderr and "kan ikke læses" in result.stderr


def test_no_instructions_file_keeps_the_built_in_ones():
    result = _server_instructions({})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("Show that sum.")

"""SessionStart hook (T11, FR-48): registered in .claude/settings.json, runs clean as a remote session, prepares
Python deps, Chromium, secrets (names only), and the dev database, and never prints a secret value."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
HOOK = REPO / ".claude" / "hooks" / "session-start.sh"
SETTINGS = REPO / ".claude" / "settings.json"


def test_hook_is_registered_and_executable():
    settings = json.loads(SETTINGS.read_text())
    commands = [h["command"] for group in settings["hooks"]["SessionStart"] for h in group["hooks"]]
    assert commands == ["$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"]
    assert os.access(HOOK, os.X_OK)
    assert subprocess.run(["bash", "-n", str(HOOK)]).returncode == 0
    src = HOOK.read_text()
    for step in ("requirements.txt", "playwright", ".env.example", "dev_db.sh", "CLAUDE_CODE_REMOTE"):
        assert step in src
    # names only: no secret variable is ever expanded into output
    assert not any(f"${{{n}}}" in src or f"${n}" in src for n in ("ANTHROPIC_API_KEY", "META_ACCESS_TOKEN", "GEMINI_API_KEY", "META_CAPI_TOKEN"))


def test_hook_outside_a_remote_session_only_touches_the_plugin(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO)}
    env.pop("CLAUDE_CODE_REMOTE", None)
    res = subprocess.run([str(HOOK)], env=env, capture_output=True, text=True)
    assert res.returncode == 0 and "not a remote session" in res.stdout


@pytest.mark.skipif(os.environ.get("CLAUDE_CODE_REMOTE") != "true", reason="the full hook installs deps and starts Postgres; run it in the remote container")
def test_hook_runs_clean_remotely_and_reports_secrets_by_name_only(tmp_path):
    env_file = tmp_path / "env"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO), "CLAUDE_ENV_FILE": str(env_file), "META_ACCESS_TOKEN": "hook-test-secret-xyz"}
    res = subprocess.run([str(HOOK)], env=env, capture_output=True, text=True, timeout=600)
    out = res.stdout + res.stderr
    assert res.returncode == 0 and "session-start: done" in out, out
    assert "hook-test-secret-xyz" not in out and "hook-test-secret-xyz" not in env_file.read_text()
    assert "secrets from the host store: " in out and "META_ACCESS_TOKEN" in out.split("secrets from the host store:")[1].splitlines()[0]
    assert "dev database ready" in out and "PLAYWRIGHT_BROWSERS_PATH" in env_file.read_text()
    assert (REPO / "marketing-engineer" / ".env").exists()

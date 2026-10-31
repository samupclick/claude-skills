"""SessionStart hook (T11, FR-48): registered in .claude/settings.json, runs clean as a remote session, prepares
Python deps, Chromium, secrets (names only), and the dev database, and never prints a secret value."""
from __future__ import annotations

import json
import os
import re
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


LIVE = {"ANTHROPIC_API_KEY": "sk-ant-hook-1", "META_ACCESS_TOKEN": "meta-hook-2", "META_READ_TOKEN": "meta-read-hook-3",
        "SUPABASE_STORAGE_PASSWORD": "sb-hook-4", "REDDIT_CLIENT_SECRET": "reddit-hook-5", "TURNSTILE_SECRET_KEY": "ts-hook-6",
        "WAREHOUSE_URL_WORKER": "postgresql://worker_rw:pw-hook-7@db.example.invalid:6543/postgres",
        "META_SOMETHING_NEW": "meta-new-hook-8", "CHECKIN_TO": "sam-hook-9@example.invalid"}


PIPELINE_VAR = re.compile(r"^(WAREHOUSE_URL_|ANTHROPIC_API_KEY|SUPABASE_|SCRAPECREATORS_|GEMINI_|REDDIT_|META_|TURNSTILE_|CAL_|CHECKIN_"
                          r"|MODEL_ID|IMAGE_MODEL|FUNNEL_HOST|EMAIL_QUEUE_DIR|[A-Z]+_BACKEND$)")


def report(env_extra: dict[str, str]) -> str:
    """`session-start.sh --report-env` with the pipeline's variables taken from `env_extra` only (pytest may have loaded .env)."""
    env = {k: v for k, v in os.environ.items() if not PIPELINE_VAR.match(k)}
    env.update(env_extra)
    res = subprocess.run([str(HOOK), "--report-env"], env={**env, "CLAUDE_PROJECT_DIR": str(REPO)}, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout + res.stderr


def line(out: str, label: str) -> list[str]:
    return out.split(f"session-start: {label}:", 1)[1].splitlines()[0].split()


def test_hook_reports_live_backend_variables_by_name_only():
    out = report({**LIVE, "EMAIL_BACKEND": "gmail_connector", "META_BACKEND": "fake", "MODEL_BACKEND": "fixture",
                  "META_FAKE_SEED": "7", "ANTHROPIC_BASE_URL": "https://proxy.example.invalid"})
    assert set(line(out, "secrets from the host store")) == set(LIVE)
    assert line(out, "live backends selected") == ["EMAIL_BACKEND"]
    assert "META_FAKE_SEED" not in out and "ANTHROPIC_BASE_URL" not in out
    assert not any(v in out for v in LIVE.values()) and "proxy.example.invalid" not in out
    assert "GEMINI_API_KEY" in line(out, "not provided (dev defaults or unset)")
    assert "dev database: local only" not in out


def test_hook_report_in_a_dev_only_container():
    out = report({"EMAIL_BACKEND": "file", "MODEL_BACKEND": "fixture"})
    assert line(out, "secrets from the host store") == ["none"] and line(out, "live backends selected") == ["none"]
    assert "dev database: local only" in out


@pytest.mark.skipif(os.environ.get("CLAUDE_CODE_REMOTE") != "true" or os.geteuid() != 0,
                    reason="runs dev_db.sh against the local cluster as root, like the remote container")
def test_hook_gives_a_fresh_container_a_working_dev_database(tmp_path):
    """A fresh container: pgvector not installed and an empty apt index until `apt-get update` (stubbed, so nothing is
    installed); node and the plugin stubbed. scripts/dev_db.sh refreshes the index once and the hook ends with a dev
    database the five roles connect to."""
    stubs = tmp_path / "bin"
    stubs.mkdir()
    log = tmp_path / "apt.log"
    scripts = {
        "dpkg": f'if [ "$1" = "-s" ] && [ "$2" = "postgresql-16-pgvector" ]; then [ -f {tmp_path}/installed ]; exit; fi\nexec /usr/bin/dpkg "$@"',
        "apt-get": (f'echo "$*" >> {log}\ncase "$1" in update) touch {tmp_path}/updated ;;'
                    f' install) [ -f {tmp_path}/updated ] || exit 100; touch {tmp_path}/installed ;; esac'),
        "npm": f'[ "$1 $2" = "root -g" ] && echo {tmp_path}/node && exit 0\nexit 0',
        "npx": "exit 0",
        "claude": 'echo "mattpocock-skills@claude-plugins-official"',
    }
    for name, body in scripts.items():
        (stubs / name).write_text(f"#!/bin/bash\n{body}\n")
        (stubs / name).chmod(0o755)
    (tmp_path / "node" / "playwright").mkdir(parents=True)
    (tmp_path / "browsers" / "chromium-1").mkdir(parents=True)
    env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}", "CLAUDE_PROJECT_DIR": str(REPO), "CLAUDE_CODE_REMOTE": "true",
           "CLAUDE_ENV_FILE": str(tmp_path / "env"), "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "browsers"), "TMPDIR": str(tmp_path),
           "META_ACCESS_TOKEN": "hook-fresh-secret"}
    res = subprocess.run([str(HOOK)], env=env, capture_output=True, text=True, timeout=600)
    out = res.stdout + res.stderr
    assert res.returncode == 0 and "session-start: done" in out, out
    assert log.read_text().splitlines() == ["install -y -q postgresql-16-pgvector", "update -qq", "install -y -q postgresql-16-pgvector"]
    assert "dev database ready" in out and "five roles connect" in out, (tmp_path / "session-start-dev_db.log").read_text()
    assert "seed skipped" in out                                   # a live variable is present: the local database is not seeded
    assert "hook-fresh-secret" not in out and "hook-fresh-secret" not in (tmp_path / "env").read_text()


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

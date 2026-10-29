"""scripts/env_from_keychain.sh, sourced in bash and zsh against a stub `security`: exports values, prints names only,
loads the Meta write token only with --with-meta-write, loads a named subset, and refuses to run unsourced."""
import shutil
import subprocess
from pathlib import Path

import pytest

ME_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ME_DIR / "scripts" / "env_from_keychain.sh"
SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]


def sentinel(service, account):
    return f"SENTINEL-{service}-{account}-value"


@pytest.fixture
def stub_path(tmp_path):
    """A `security` that answers find-generic-password -s S -a A -w with a sentinel, and fails for unknown items."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    known = {("aeo-pipeline-v3", "anthropic"), ("aeo-pipeline-v3", "gemini"),
             ("marketing-engineer", "META_ACCESS_TOKEN"), ("marketing-engineer", "META_READ_TOKEN")}
    cases = "\n".join(f'  "{s}|{a}") echo "{sentinel(s, a)}" ;;' for s, a in known)
    (bin_dir / "security").write_text(f"""#!/bin/sh
[ "$1" = find-generic-password ] || exit 1
svc=""; acct=""; w=0
shift
while [ $# -gt 0 ]; do
  case "$1" in -s) svc="$2"; shift ;; -a) acct="$2"; shift ;; -w) w=1 ;; esac
  shift
done
[ "$w" = 1 ] || exit 1
case "$svc|$acct" in
{cases}
  *) echo "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain." >&2; exit 44 ;;
esac
""")
    (bin_dir / "security").chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def source(shell, stub_path, *args, then="env"):
    cmd = f'source "{SCRIPT}" {" ".join(args)}; rc=$?; echo "rc=$rc"; {then}'
    return subprocess.run([shell, "-c", cmd], env={"PATH": stub_path, "HOME": "/nonexistent"},
                          capture_output=True, text=True)


@pytest.mark.parametrize("shell", SHELLS)
def test_exports_mapped_values_and_prints_only_names(shell, stub_path):
    res = source(shell, stub_path, then='echo "A=$ANTHROPIC_API_KEY"; echo "G=$GEMINI_API_KEY"; echo "W=${META_ACCESS_TOKEN:-unset}"')
    lines = res.stdout.splitlines()
    assert "rc=0" in lines, res.stdout + res.stderr
    assert f"A={sentinel('aeo-pipeline-v3', 'anthropic')}" in lines
    assert f"G={sentinel('aeo-pipeline-v3', 'gemini')}" in lines
    assert "W=unset" in lines
    report = res.stdout.split("rc=")[0] + res.stderr
    assert "SENTINEL" not in report
    assert "ANTHROPIC_API_KEY" in report and "GEMINI_API_KEY" in report and "META_READ_TOKEN" in report
    assert "not in keychain:" in report and "SCRAPECREATORS_API_KEY" in report
    assert "META_ACCESS_TOKEN" in report and "--with-meta-write" in report


@pytest.mark.parametrize("shell", SHELLS)
def test_meta_write_token_only_with_the_flag(shell, stub_path):
    res = source(shell, stub_path, "--with-meta-write", then='echo "W=$META_ACCESS_TOKEN"')
    assert "rc=0" in res.stdout, res.stdout + res.stderr
    assert f"W={sentinel('marketing-engineer', 'META_ACCESS_TOKEN')}" in res.stdout.splitlines()
    assert "SENTINEL" not in res.stdout.split("rc=")[0] + res.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_named_subset_loads_only_those(shell, stub_path):
    res = source(shell, stub_path, "ANTHROPIC_API_KEY", then='echo "G=${GEMINI_API_KEY:-unset}"; echo "R=${META_READ_TOKEN:-unset}"')
    assert "rc=0" in res.stdout, res.stdout + res.stderr
    assert "G=unset" in res.stdout and "R=unset" in res.stdout
    report = res.stdout.split("rc=")[0]
    assert "loaded: ANTHROPIC_API_KEY" in report and "GEMINI_API_KEY" not in report


@pytest.mark.parametrize("shell", SHELLS)
def test_naming_the_write_token_still_needs_the_flag(shell, stub_path):
    res = source(shell, stub_path, "META_ACCESS_TOKEN", then='echo "W=${META_ACCESS_TOKEN:-unset}"')
    assert "W=unset" in res.stdout
    assert "--with-meta-write" in res.stdout.split("rc=")[0]


@pytest.mark.parametrize("shell", SHELLS)
def test_unknown_name_or_option_fails_without_exiting_the_shell(shell, stub_path):
    res = source(shell, stub_path, "NOT_A_PIPELINE_VAR", then='echo "still-here"')
    assert "rc=2" in res.stdout and "still-here" in res.stdout
    assert "NOT_A_PIPELINE_VAR" in res.stderr
    res = source(shell, stub_path, "--bogus", then='echo "still-here"')
    assert "rc=2" in res.stdout and "still-here" in res.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_leaves_no_helper_names_behind(shell, stub_path):
    res = source(shell, stub_path, then="set | grep -c '^_me_kc' || true")
    assert res.stdout.strip().splitlines()[-1] == "0", res.stdout


def test_refuses_to_run_unsourced(stub_path):
    res = subprocess.run(["bash", str(SCRIPT)], env={"PATH": stub_path}, capture_output=True, text=True)
    assert res.returncode == 2
    assert "source" in res.stderr and "SENTINEL" not in res.stdout + res.stderr


def test_mapping_holds_no_secret_and_names_every_keychain_variable():
    text = SCRIPT.read_text()
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SCRAPECREATORS_API_KEY", "META_ACCESS_TOKEN", "META_READ_TOKEN",
                "META_AD_ACCOUNT_ID", "META_PAGE_ID", "META_PIXEL_ID", "META_CAPI_TOKEN", "SUPABASE_URL",
                "SUPABASE_PUBLISHABLE_KEY", "TURNSTILE_SECRET_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                "CAL_WEBHOOK_SECRET"):
        assert var in text, var
    assert "-w" in text and "find-generic-password" in text
    for shape in ("sk-ant-", "AIza", "EAA", "sb_publishable_", "sb_secret_"):
        assert shape not in text, shape

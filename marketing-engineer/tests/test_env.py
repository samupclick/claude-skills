import os

import pytest

from adapters.env import MissingEnvVar, UnknownBackend, choose_backend, load_env, require


def test_load_env_reads_the_given_file_without_overriding(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("T0_FROM_FILE=file-value\nT0_ALREADY=file-value\n")
    monkeypatch.delenv("T0_FROM_FILE", raising=False)
    monkeypatch.setenv("T0_ALREADY", "shell-value")
    assert load_env(env_file) == env_file
    assert os.environ["T0_FROM_FILE"] == "file-value"
    assert os.environ["T0_ALREADY"] == "shell-value"


def test_load_env_returns_none_when_file_missing(tmp_path):
    assert load_env(tmp_path / "nope.env") is None


def test_require_names_the_missing_variable_and_never_a_value(monkeypatch):
    monkeypatch.setenv("T0_PRESENT", "s3cret-value")
    monkeypatch.delenv("T0_ABSENT", raising=False)
    with pytest.raises(MissingEnvVar) as exc:
        require("pull_inspo", "T0_PRESENT", "T0_ABSENT")
    assert "T0_ABSENT" in str(exc.value)
    assert "pull_inspo" in str(exc.value)
    assert "s3cret-value" not in str(exc.value)
    assert require("pull_inspo", "T0_PRESENT") == {"T0_PRESENT": "s3cret-value"}


def test_choose_backend_unknown_value_names_the_variable(monkeypatch):
    monkeypatch.setenv("T0_BACKEND", "bogus")
    with pytest.raises(UnknownBackend) as exc:
        choose_backend("T0_BACKEND", {"local": lambda: "L"})
    assert "T0_BACKEND" in str(exc.value)
    monkeypatch.setenv("T0_BACKEND", "local")
    assert choose_backend("T0_BACKEND", {"local": lambda: "L"}) == "L"

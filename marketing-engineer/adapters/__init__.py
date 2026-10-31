"""Adapter package: every external service behind an interface chosen by an env var.

Workers import factories from here and never a vendor SDK (FR-49). See references/dev-mode.md
for the env var per service and what each dev backend does.
"""
from adapters.env import MissingEnvVar, UnknownBackend, dev_root, load_env, require  # noqa: F401

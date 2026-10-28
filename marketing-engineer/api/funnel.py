"""Vercel entrypoint for the quiz funnel (FR-32 to FR-35, DR-4): the WSGI `app` the Python runtime loads. vercel.json
routes GET /quiz/config, POST /quiz/start, POST /quiz and POST /cal-webhook here and serves funnel/static/ itself; the
route logic is funnel/app.py's handle(), adapted by funnel/wsgi.py. Role `app` through WAREHOUSE_URL_APP only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from funnel.wsgi import make_app, serverless_deps  # noqa: E402

app = make_app(serverless_deps)

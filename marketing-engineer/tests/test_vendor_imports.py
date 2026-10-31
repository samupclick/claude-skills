"""FR-49: vendor SDKs are imported only inside the adapter package."""
import re
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent
VENDORS = re.compile(r"^\s*(import|from)\s+(facebook_business|google\.generativeai|google\.genai|supabase|anthropic)\b", re.M)


def test_no_vendor_sdk_import_outside_adapters():
    offenders = []
    for py in ME_DIR.rglob("*.py"):
        rel = py.relative_to(ME_DIR)
        if rel.parts[0] in ("adapters", ".dev") or "__pycache__" in rel.parts:
            continue
        if VENDORS.search(py.read_text()):
            offenders.append(str(rel))
    assert offenders == []

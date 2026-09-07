"""scripts/seed.py parsing: families.md is read as-is and cross-kind name reuse is reported, not hidden."""
import importlib.util
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("seed", ME_DIR / "scripts" / "seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def test_parse_families_reads_all_three_kinds_from_the_draft():
    fams = seed.parse_families((ME_DIR / "references" / "families.md").read_text())
    kinds = {k for _, k in fams}
    assert kinds == {"format", "hook_type", "angle"}
    assert ("job_photo_bubble", "format") in fams and ("number", "hook_type") in fams and ("pain_led", "angle") in fams
    assert len([f for f in fams if f[1] == "format"]) == 15


def test_name_conflicts_reports_names_used_for_two_kinds():
    fams = [("pain", "hook_type"), ("contrarian", "hook_type"), ("contrarian", "angle"), ("pain_led", "angle")]
    assert seed.name_conflicts(fams) == {"contrarian": ["hook_type", "angle"]}
    assert seed.name_conflicts([("a", "format")]) == {}

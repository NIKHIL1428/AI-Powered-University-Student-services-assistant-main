"""Annex A resolution order — pure unit tests on the engine."""
from datetime import date

from app.precedence.engine import resolve
from app.precedence.models import SourceCandidate as C


def cand(key, doc, lvl, eff, value, section="1", sup=(), to=None, progs="ALL", batches="ALL"):
    return C(key=key, doc_id=doc, section=section, authority_level=lvl, effective_from=date.fromisoformat(eff),
             effective_to=date.fromisoformat(to) if to else None, supersedes=list(sup),
             scope_programmes=progs, scope_batches=batches, topic="min_attendance_pct", value=value)


def annex_a3():
    return [cand("REG", "ACAD-REG-2024", 1, "2024-07-01", "75", section="7.2"),
            cand("CIRC", "ACAD-2026-08", 2, "2026-08-01", "80", sup=["ACAD-REG-2024#7.2"]),
            cand("FAQ", "DEPT-FAQ", 4, "2026-09-15", "65")]


def test_annex_a3_worked_example():
    r = resolve(annex_a3(), date(2026, 10, 6))
    assert r.status == "resolved" and [w.value for w in r.winners] == ["80"]
    reasons = {c.key: why for c, why in r.overridden}
    assert reasons["REG"].startswith("step 2")
    assert reasons["FAQ"].startswith("step 3")


def test_not_yet_effective_is_upcoming():
    r = resolve(annex_a3(), date(2026, 7, 15))
    assert [w.value for w in r.winners] == ["75"]
    assert {c.key for c in r.upcoming} == {"CIRC", "FAQ"}


def test_level3_cannot_supersede():
    cs = [cand("REG", "REG", 1, "2024-07-01", "75", section="7.2"),
          cand("NOTICE", "DEPT", 3, "2026-09-01", "85", sup=["REG#7.2"])]
    r = resolve(cs, date(2026, 10, 6))
    assert [w.key for w in r.winners] == ["REG"]
    assert any("only level 1-2 may supersede" in n for n in r.notes)


def test_same_level_recency():
    cs = [cand("A", "C1", 2, "2025-01-01", "70"), cand("B", "C2", 2, "2026-01-01", "72")]
    r = resolve(cs, date(2026, 10, 6))
    assert [w.key for w in r.winners] == ["B"]
    assert r.overridden[0][1].startswith("step 4")


def test_same_level_same_date_conflict():
    cs = [cand("A", "C1", 2, "2026-01-01", "70"), cand("B", "C2", 2, "2026-01-01", "72")]
    r = resolve(cs, date(2026, 10, 6))
    assert r.status == "conflict" and {w.key for w in r.winners} == {"A", "B"}


def test_same_value_tie_is_not_conflict():
    cs = [cand("A", "C1", 2, "2026-01-01", "70"), cand("B", "C2", 2, "2026-01-01", "70")]
    assert resolve(cs, date(2026, 10, 6)).status == "resolved"


def test_programme_scope_mismatch_dropped():
    cs = [cand("REG", "REG", 1, "2024-07-01", "75"), cand("IT", "IT-REG", 1, "2026-01-01", "90", progs="B.Tech IT")]
    r = resolve(cs, date(2026, 10, 6), {"programme": "B.Tech CSE", "batch_year": 2023})
    assert [w.key for w in r.winners] == ["REG"] and r.dropped[0][0].key == "IT"


def test_batch_scope_mismatch_dropped():
    cs = [cand("REG", "REG", 1, "2024-07-01", "75"), cand("NEW", "NEW", 1, "2026-01-01", "80", batches="2023+")]
    r = resolve(cs, date(2026, 10, 6), {"programme": "B.Tech CSE", "batch_year": 2022})
    assert [w.key for w in r.winners] == ["REG"]


def test_general_question_keeps_scoped_docs():
    cs = [cand("NEW", "NEW", 1, "2026-01-01", "80", batches="2023+")]
    assert resolve(cs, date(2026, 10, 6), None).status == "resolved"


def test_level5_informational_only():
    r = resolve([cand("FORUM", "FORUM", 5, "2026-01-01", "60")], date(2026, 10, 6))
    assert r.status == "none" and [c.key for c in r.informational] == ["FORUM"]


def test_expired_dropped():
    cs = [cand("OLD", "OLD", 1, "2020-01-01", "60", to="2024-06-30"), cand("REG", "REG", 1, "2024-07-01", "75")]
    r = resolve(cs, date(2026, 10, 6))
    assert [w.key for w in r.winners] == ["REG"]


def test_clause_prefix_does_not_overmatch():
    cs = [cand("C72", "REG", 1, "2024-07-01", "75", section="7.2"),
          cand("C720", "REG", 1, "2024-07-01", "75", section="7.20"),
          cand("CIRC", "CIRC", 2, "2026-01-01", "80", sup=["REG#7.2"])]
    r = resolve(cs, date(2026, 10, 6))
    removed = {c.key for c, why in r.overridden if why.startswith("step 2")}
    assert removed == {"C72"}

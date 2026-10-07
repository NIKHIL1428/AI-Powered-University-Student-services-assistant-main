"""Annex A Source Precedence Policy — pure Python, no LLM.

Order: 1 applicability -> 2 explicit supersession (level 1-2 only) -> 3 authority -> 4 recency -> 5 unresolved.
Used for both rule-registry rows (grouped by `topic` = parameter) and retrieved text chunks.
"""
import re
from collections import defaultdict
from datetime import date

from app.precedence.models import Resolution, SourceCandidate
from app.precedence.scope import batch_in_scope, programme_in_scope


def normalize_section(s: str | None) -> str:
    s = (s or "").strip()
    s = re.sub(r"^(clause|section|sec\.?|para|rule|§)\s*", "", s, flags=re.I)
    return s.strip(" .")


def parse_supersedes(raw: str | list | None) -> list[str]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else re.split(r"[;,]", raw)
    return [i.strip() for i in items if i and i.strip()]


def _matches(target: str, cand: SourceCandidate) -> bool:
    doc, _, clause = target.partition("#")
    if doc.strip() != cand.doc_id:
        return False
    clause = normalize_section(clause)
    if not clause:
        return True
    sec = normalize_section(cand.section)
    return sec == clause or sec.startswith(clause + ".")


def _fmt(c: SourceCandidate) -> str:
    return f"{c.doc_id}#{c.section}" if c.section else c.doc_id


def resolve(cands: list[SourceCandidate], as_of: date, student: dict | None = None) -> Resolution:
    res = Resolution()
    if not cands:
        return res

    # ---- Step 1: applicability ----
    live: list[SourceCandidate] = []
    for c in cands:
        if c.effective_from and c.effective_from > as_of:
            res.upcoming.append(c)
            continue
        if c.effective_to and c.effective_to < as_of:
            res.dropped.append((c, f"step 1: {c.doc_id} expired on {c.effective_to}"))
            continue
        if student and not (programme_in_scope(student.get("programme"), c.scope_programmes)
                            and batch_in_scope(student.get("batch_year"), c.scope_batches)):
            res.dropped.append((c, f"step 1: {c.doc_id} scope ({c.scope_programmes}/{c.scope_batches}) "
                                   f"does not cover this student"))
            continue
        if c.authority_level >= 5:
            res.informational.append(c)
            continue
        live.append(c)
    for c in res.upcoming:
        res.notes.append(f"step 1: {_fmt(c)} not yet effective (from {c.effective_from}) -> upcoming change")
    res.notes += [r for _, r in res.dropped]
    if res.informational:
        res.notes.append("level 5 sources are informational only and never override: "
                         + ", ".join(sorted({c.doc_id for c in res.informational})))

    # ---- Step 2: explicit supersession (only by level 1-2 issuers) ----
    removed: set[str] = set()
    for sup in live:
        targets = parse_supersedes(sup.supersedes)
        if not targets:
            continue
        if sup.authority_level > 2:
            res.notes.append(f"step 2: {sup.doc_id} (level {sup.authority_level}) claims to supersede "
                             f"{';'.join(targets)} but only level 1-2 may supersede -> ignored")
            continue
        for t in targets:
            for c in live:
                if c.key in removed or c.doc_id == sup.doc_id:
                    continue
                if _matches(t, c):
                    removed.add(c.key)
                    reason = f"step 2: {sup.doc_id} explicitly supersedes {_fmt(c)}"
                    res.overridden.append((c, reason))
                    if reason not in res.notes:
                        res.notes.append(reason)
    live = [c for c in live if c.key not in removed]

    # ---- Text chunks (no topic): order by authority, recency, score ----
    untopical = [c for c in live if not c.topic]
    untopical.sort(key=lambda c: (c.authority_level, -(c.effective_from or date.min).toordinal(), -c.score))

    # ---- Steps 3-5 per topic (rules) ----
    groups: dict[str, list[SourceCandidate]] = defaultdict(list)
    for c in live:
        if c.topic:
            groups[c.topic].append(c)

    winners: list[SourceCandidate] = []
    conflict = False
    for topic, group in groups.items():
        best_level = min(c.authority_level for c in group)
        for c in group:
            if c.authority_level > best_level:
                top = next(x for x in group if x.authority_level == best_level)
                reason = (f"step 3: {_fmt(top)} (level {best_level}) outranks {_fmt(c)} "
                          f"(level {c.authority_level})")
                res.overridden.append((c, reason))
                res.notes.append(reason)
        same = [c for c in group if c.authority_level == best_level]
        latest = max((c.effective_from or date.min) for c in same)
        for c in same:
            if (c.effective_from or date.min) < latest:
                top = next(x for x in same if (x.effective_from or date.min) == latest)
                reason = f"step 4: {_fmt(top)} (effective {latest}) is newer than {_fmt(c)} ({c.effective_from})"
                res.overridden.append((c, reason))
                res.notes.append(reason)
        tied = [c for c in same if (c.effective_from or date.min) == latest]
        if len({(c.value or "").strip().lower() for c in tied}) > 1:
            conflict = True
            res.notes.append(f"step 5: unresolved conflict on {topic}: "
                             + " vs ".join(f"{_fmt(c)}={c.value}" for c in tied))
        winners.extend(tied)

    res.winners = winners + untopical
    if conflict:
        res.status = "conflict"
    elif res.winners:
        res.status = "resolved"
    return res

"""Build the NSUT corpus (data/documents/<category>/) and data/source_register.csv from the raw download folder.

  python scripts/prepare_corpus.py --raw ../data/data

- Every document gets Annex B metadata from MANIFEST below (dates read from the notice; where the OCR'd date was
  illegible the date in the downloaded file name was used - marked "date from file name" in provenance).
- Documents containing student lists (names / roll numbers) are NOT copied. Only a redacted text rendering
  (app/guardrails/pii.py: list removed, page numbers preserved) is stored, as the guide requires.
- Exact duplicate downloads are skipped (same SHA-256).
"""
import argparse
import csv
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.guardrails.pii import redact_pages  # noqa: E402
from app.ingestion.document_loader import extract_pages  # noqa: E402

SRC = "https://www.nsut.ac.in (official notices; downloaded by the team)"
ACAD = "Office of the Dean (Academics), NSUT"
LIB = "Central Library, NSUT"
TNP = "Training and Placement Section, NSUT"

# raw path (relative to --raw) -> (category, doc_id, title, issuer, level, doc_type, effective_from, supersedes, note)
MANIFEST = [
    ("attendence/attendance regulaion.pdf", "attendance", "NSUT-ACAD-RULES-ATT",
     "Academic Rules and Regulations of NSUT - Clause 11 Attendance and Detention (enclosed with attendance notification)",
     ACAD, 1, "regulation", "2026-09-15", "", "regulation clause enclosed with notification dated 15.09.2026"),
    ("attendence/attendance notification 7 feb 26.pdf", "attendance", "NSUT-ATT-NOTIF-2026-02",
     "Attendance notification: check CUMS entries; medical certificates via HoD", ACAD, 2, "circular", "2026-02-07", "", ""),
    ("attendence/attandence notification.pdf", "attendance", "NSUT-ATT-NOTIF-2025-10",
     "Notification: attendance entries on CUMS, portal lock 14.11.2025", ACAD, 2, "circular", "2025-10-30", "", ""),
    ("attendence/attendence portal notification.pdf", "attendance", "NSUT-ATT-PORTAL-2025-11",
     "Notification: attendance portal update deadline for faculty", ACAD, 2, "circular", "2025-11-18", "", ""),
    ("attendence/SHORT OF ATTENDANCE -1 19 nov 25.pdf", "attendance", "NSUT-SHORTATT-I-2025",
     "Notification regarding short of attendance - I (B.Tech; list redacted)", ACAD, 2, "circular", "2025-11-19", "", ""),
    ("attendence/SHORT OF ATTENDANCE -II 19 nov 25.pdf", "attendance", "NSUT-SHORTATT-II-2025",
     "Notification regarding short of attendance - II (B.Arch/B.Des/BBA; list redacted)", ACAD, 2, "circular",
     "2025-11-19", "", ""),
    ("attendence/SHORT OF ATTENDANCE -III 19 nov 25.pdf", "attendance", "NSUT-SHORTATT-III-2025",
     "Notification regarding short of attendance - III (PG; list redacted)", ACAD, 2, "circular", "2025-11-19", "", ""),
    ("attendence/SHORT OF ATTENDANCE -IV 19 nov 25.pdf", "attendance", "NSUT-SHORTATT-IV-2025",
     "Notification regarding short of attendance - IV (B.Tech lateral entry; list redacted)", ACAD, 2, "circular",
     "2025-11-19", "", ""),
    ("attendence/SHORT OF ATTENDANCE -III Sem 20 nov 25.pdf", "attendance", "NSUT-SHORTATT-IIISEM-2025",
     "Notification regarding short of attendance of III & VII semester (list redacted)", ACAD, 2, "circular",
     "2025-11-20", "NSUT-SHORTATT-I-2025;NSUT-SHORTATT-II-2025", "states it supersedes notifications 1616 & 1617"),
    ("examination/FINAL detention list  21 nov 25.pdf", "examination", "NSUT-DETENTION-2025-11",
     "Final notification of students detained for short attendance, Nov-Dec 2025 (list redacted)", ACAD, 2, "circular",
     "2025-11-21", "NSUT-SHORTATT-I-2025;NSUT-SHORTATT-II-2025;NSUT-SHORTATT-III-2025;NSUT-SHORTATT-IV-2025;"
                   "NSUT-SHORTATT-IIISEM-2025", "issued in supersession of all previous short-attendance notifications"),
    ("examination/make up examination.pdf", "examination", "NSUT-MAKEUP-2026",
     "Notification regarding conduct of Make-up Examinations (list redacted)", ACAD, 2, "circular", "2026-01-19", "",
     "date approximated from referenced notification of 19.01.2026"),
    ("Academic regulation/academic calender 2026 odd sem.pdf", "academic", "NSUT-ACADCAL-ODD-2026",
     "Academic / Activity Calendar July-December 2026 (Odd Semester)", ACAD, 2, "circular", "2026-06-15", "",
     "date approximated (illegible in scan)"),
    ("Academic regulation/academic calender 2026 odd sem 23 Mar 2026 5-19 pm.pdf", "academic", "NSUT-ACADCAL-ADD-2026-03",
     "Addendum to the Academic Calendar (Even Semester 2026)", ACAD, 2, "circular", "2026-03-23", "",
     "date from file name"),
    ("Academic regulation/Registration of Even Semester 2026_compressed.pdf", "academic", "NSUT-REG-EVEN-2026",
     "Registration for Even Semester 2025-26 - registration officers and schedule", ACAD, 2, "circular", "2025-12-15", "",
     "date approximated (registration held 01.01.2026)"),
    ("Academic regulation/id card 13 may.pdf", "academic", "NSUT-IDCARD-2026",
     "Notification: students must carry NSUT identity cards on campus", ACAD, 2, "circular", "2026-05-13", "",
     "date from file name"),
    ("Academic regulation/notice regarding suspensionm of class 28 oct 25.pdf", "academic", "NSUT-CLASS-SUSP-2025-10",
     "Notification: classes suspended on 03-04.11.2025 (Innovision)", ACAD, 2, "circular", "2025-10-28", "", ""),
    ("Academic regulation/ufm during nptel.pdf", "academic", "NSUT-UFM-NPTEL-2025",
     "Notice: unfair means in NPTEL submissions (list redacted)", ACAD, 2, "notice", "2025-12-05", "", ""),
    ("Academic regulation/year back students 25 mar 26.pdf", "academic", "NSUT-YEARBACK-2026",
     "Notification: students not promoted (year back) - re-registration (list redacted)", ACAD, 2, "circular",
     "2026-03-25", "", "date from file name"),
    ("Academic regulation/Notice of Gold Medalist  2025_compressed.pdf", "academic", "NSUT-GOLDMEDAL-2025",
     "Gold medalists for the 3rd Convocation 2025 and guidelines for award of medals (list redacted)", ACAD, 2,
     "circular", "2025-11-15", "", "date approximated (convocation 11.12.2025)"),
    ("fees/fee structure 14 may.pdf", "fees", "NSUT-FEE-STRUCT-2026",
     "Annual fee of all programmes for students admitted in Academic Session 2026-27", ACAD, 2, "circular",
     "2026-05-14", "", "date from file name"),
    ("fees/fee structuree n6 Aug 2026 5-09 pm.pdf", "fees", "NSUT-FEE-CORR-2026-08",
     "Corrigendum: fee structure of Integrated BBA+MBA (IEV)", ACAD, 2, "circular", "2026-08-06", "", ""),
    ("fees/dasa students fee structure 21 july.pdf", "fees", "NSUT-FEE-DASA-2026",
     "Annual fee structure for B.Tech DASA students, Academic Session 2026-27", ACAD, 2, "circular", "2026-07-21", "",
     "date from file name"),
    ("fees/ACE 20 august.pdf", "fees", "NSUT-FEE-VERIFY-2026-08",
     "Verification of balance annual fee payment, 2022-2026 batch (list redacted)", ACAD, 2, "circular", "2026-08-20",
     "", ""),
    ("fees/Non payment of Second Installment 19 nov 25.pdf", "fees", "NSUT-FEE-2NDINST-2025-11",
     "Notice: non-payment of second installment of annual fee 2025 (list redacted)", ACAD, 2, "notice", "2025-11-19", "",
     "date from file name"),
    ("fees/Extension in application submission for refund of summer semester fee 2025.pdf", "fees",
     "NSUT-FEE-SUMMER-REFUND-2025", "Extension of last date for refund of summer semester fee 2025", ACAD, 2,
     "circular", "2025-10-01", "", "date approximated (refers to 26.09.2025; new deadline 17.10.2025)"),
    ("fees/Notices for Ph.D fees and Registration 22 dec 25.pdf", "fees", "NSUT-PHD-FEE-2025-12",
     "Notification: Ph.D. annual fees and mandatory registration", ACAD, 2, "circular", "2025-12-22", "", ""),
    ("placement/Placement Policy.pdf", "placement", "NSUT-TNP-POLICY-2025-26",
     "Placement Policy 2025-26 (Students)", TNP, 2, "circular", "2025-07-01", "",
     "season 2025-26; effective date approximated to start of season"),
    ("library/Book Bank Service 6 jan 26.pdf", "library", "NSUT-LIB-BOOKBANK-2026-01",
     "Book Bank services during January 2026", LIB, 3, "notice", "2026-01-06", "", ""),
    ("library/Lending_Service21Apr2026.pdf", "library", "NSUT-LIB-LENDING-2026-04",
     "Library notice: restricted book-lending hours till 22.04.2026", LIB, 3, "notice", "2026-04-21", "", ""),
    ("library/Library Notice 16 Aug 2023.pdf", "library", "NSUT-LIB-SATURDAY-2023",
     "Library notice: Central Library open on Saturdays", LIB, 3, "notice", "2023-08-16", "", ""),
    ("library/Suspension on saturday 2 jan 2026.pdf", "library", "NSUT-LIB-CLOSED-2026-01",
     "Suspension of Central Library services on 03.01.2026", LIB, 3, "notice", "2026-01-02", "", ""),
    ("library/library extnesion hour notice 23 april 2026.pdf", "library", "NSUT-LIB-EXTHOURS-2026-04",
     "Extension of Central Library opening hours during End-Semester exam, April-May 2026", LIB, 3, "notice",
     "2026-04-23", "", ""),
    ("scholarship/NSP 11 jun 26.pdf", "scholarships", "NSUT-SCH-NSP-2026",
     "Notification regarding activation of National Scholarship Portal 2026-27", ACAD, 2, "circular", "2026-06-01",
     "", ""),
    ("scholarship/extension of nsp date 15.12.2025.pdf", "scholarships", "NSUT-SCH-NSP-EXT-2025-12",
     "Extension of NSP application deadline to 15.12.2025 (list redacted)", ACAD, 2, "circular", "2025-12-03", "", ""),
    ("scholarship/SC merit cum discrepancy notice 1 dec 25.pdf", "scholarships", "NSUT-SCH-SC-MERIT-2025",
     "Central Sector Scholarship for SC students - provisional list notice (list redacted)", ACAD, 2, "circular",
     "2025-12-01", "", ""),
    ("scholarship/pm yasasvi notification 2 feb 2026.pdf", "scholarships", "NSUT-SCH-PMYASASVI-2026-02",
     "PM YASASVI (OBC/EBC/DNT): students granted lesser amount", ACAD, 2, "circular", "2026-02-02", "", ""),
    ("scholarship/edistrict order 6 march.pdf", "scholarships", "NSUT-SCH-EDISTRICT-2026-03",
     "E-District scholarship notification (SC/ST/OBC merit scholarship, State Topper Award)", ACAD, 2, "circular",
     "2026-03-06", "", ""),
    ("scholarship/Edistrict 30 sept 2026.pdf", "scholarships", "NSUT-SCH-EDISTRICT-2026-09",
     "Endorsement: E-District timeline for post-matric scholarships (SC/OBC) on NSP", ACAD, 2, "circular",
     "2026-09-30", "", "date from file name"),
    ("scholarship/aicte_sarswati 1 jul.pdf", "scholarships", "NSUT-SCH-AICTE-2026",
     "AICTE YASHASVI and SARSWATI scholarship scheme", ACAD, 2, "circular", "2026-07-01", "", "date from file name"),
    ("scholarship/KOTAK 7 septn 26.pdf", "scholarships", "NSUT-SCH-KOTAK-2026",
     "Endorsement: Kotak Kanya Scholarship 2026-27", ACAD, 2, "circular", "2026-09-07", "", "date from file name"),
    ("scholarship/SDA 27 aug 26.pdf", "scholarships", "NSUT-SCH-SDEF-2026",
     "Endorsement: Swami Dayanand Education Foundation India Scholarship 2026-27", ACAD, 2, "circular", "2026-08-27",
     "", ""),
    ("scholarship/siemen 30 sept 26.pdf", "scholarships", "NSUT-SCH-SIEMENS-2026",
     "Endorsement: Siemens Energy Energy4Good student scholarship", ACAD, 2, "circular", "2026-09-30", "", ""),
]
DUPLICATES = {"examination/dettention list 21 nov .pdf": "NSUT-DETENTION-2025-11",
              "scholarship/nsp notice 11 jun  26.pdf": "NSUT-SCH-NSP-2026"}
FIELDS = ["doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from", "effective_to",
          "supersedes", "scope_programmes", "scope_batches", "provenance", "retrieved_on", "synthetic", "file_name"]


def _resolve(raw: Path, rel: str) -> Path:
    """Exact path, else match ignoring unicode whitespace variants (downloads contain U+202F before 'pm')."""
    p = raw / rel
    if p.exists():
        return p
    norm = lambda s: " ".join(s.replace(" ", " ").replace(" ", " ").split()).lower()
    for cand in p.parent.iterdir():
        if norm(cand.name) == norm(p.name):
            return cand
    raise FileNotFoundError(p)


def main(raw: Path, docs: Path, register: Path) -> list[str]:
    log = []
    rows = []
    seen = {}
    for rel, cat, doc_id, title, issuer, lvl, dtype, eff, sup, note in MANIFEST:
        src = _resolve(raw, rel)
        data = src.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        if h in seen:
            log.append(f"skip duplicate {rel} (= {seen[h]})")
            continue
        seen[h] = doc_id
        warns: list[str] = []
        pages = extract_pages(src, data, warns)
        redacted, pii = redact_pages([p.text for p in pages])
        (docs / cat).mkdir(parents=True, exist_ok=True)
        if pii["flagged"]:
            out = docs / cat / f"{doc_id}.redacted.txt"
            out.write_text("\f".join(redacted), encoding="utf-8")       # \f = page break -> citations keep pages
            prov = f"{SRC}; original '{Path(rel).name}' NOT stored - student list removed " \
                   f"({pii['rolls_before']} roll numbers), text rendering kept"
            log.append(f"REDACTED {rel} -> {out.relative_to(docs)} ({pii['rolls_before']} roll numbers removed)")
        else:
            out = docs / cat / f"{doc_id}.pdf"
            shutil.copyfile(src, out)
            prov = f"{SRC}; original file '{Path(rel).name}'"
            log.append(f"copied   {rel} -> {out.relative_to(docs)}")
        if note:
            prov += f"; {note}"
        rows.append({"doc_id": doc_id, "title": title, "issuer": issuer, "authority_level": lvl, "doc_type": dtype,
                     "version": "1.0", "effective_from": eff, "effective_to": "", "supersedes": sup,
                     "scope_programmes": "ALL", "scope_batches": "ALL", "provenance": prov,
                     "retrieved_on": "2026-10-06", "synthetic": "N", "file_name": out.relative_to(docs).as_posix()})
    for rel, dup in DUPLICATES.items():
        log.append(f"skip duplicate {rel} (identical to {dup})")
    # keep synthetic rows that are already in the register
    if register.exists():
        rows += [r for r in csv.DictReader(register.open(encoding="utf-8-sig")) if r.get("synthetic") == "Y"]
    with register.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log.append(f"{len(rows)} rows written to {register}")
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT.parent / "data" / "data"))
    ap.add_argument("--docs", default=str(ROOT / "data" / "documents"))
    ap.add_argument("--register", default=str(ROOT / "data" / "source_register.csv"))
    a = ap.parse_args()
    print("\n".join(main(Path(a.raw), Path(a.docs), Path(a.register))))

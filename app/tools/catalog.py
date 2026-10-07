"""Fixed vocabularies: rule parameters the tools read, and the tool allowlist per intent.

Tools only ever read these parameters from rule_registry; the rule extractor only ever writes them.
"""

# parameter -> (operator, human description, plausible value range for validation)
PARAMETERS: dict[str, dict] = {
    "min_attendance_pct": {"operator": ">=", "desc": "Minimum attendance % to appear in end-semester exam",
                           "range": (40, 100), "keywords": ["attendance"], "unit": "%"},
    "min_total_marks_pct": {"operator": ">=", "desc": "Minimum total marks % to pass a course",
                            "range": (20, 60), "keywords": ["pass", "passing", "minimum marks"], "unit": "%"},
    "supplementary_allowed_results": {"operator": "in", "desc": "Results that allow a supplementary exam",
                                      "range": None, "keywords": ["supplementary"], "unit": ""},
    "placement_min_cgpa": {"operator": ">=", "desc": "Minimum CGPA to register for placement",
                           "range": (4, 10), "keywords": ["cgpa", "placement"], "unit": ""},
    "placement_max_backlogs": {"operator": "<=", "desc": "Maximum active backlogs allowed for placement",
                               "range": (0, 10), "keywords": ["backlog", "placement"], "unit": ""},
    "attendance_relaxation_dean_pct": {"operator": "<=", "desc": "Attendance relaxation the Dean Academics may allow",
                                       "range": (0, 30), "keywords": ["relaxation"], "unit": "%"},
    "attendance_relaxation_committee_pct": {"operator": "<=",
                                            "desc": "Further attendance relaxation under exceptional circumstances",
                                            "range": (0, 30), "keywords": ["relax"], "unit": "%"},
    "min_attendance_after_relaxation_pct": {"operator": ">=",
                                            "desc": "Minimum attendance after all relaxations (absolute floor)",
                                            "range": (30, 100), "keywords": ["after relaxation"], "unit": "%"},
    "max_attendance_relaxations": {"operator": "<=", "desc": "Maximum number of attendance relaxations per programme",
                                   "range": (0, 10), "keywords": ["maximum of", "times"], "unit": ""},
}

TOOLS = [
    "find_course", "get_student_profile", "get_attendance", "get_results", "resolve_rule",
    "check_exam_eligibility", "check_supplementary_eligibility", "check_placement_eligibility",
]

PERSONAL_TOOLS = {t for t in TOOLS if t not in {"resolve_rule"}}

# intent -> ordered default plan (steps are tools or the pseudo-step "retrieve")
INTENT_ALLOWLIST: dict[str, list[str]] = {
    "policy_fact": ["retrieve", "resolve_rule"],
    "procedure": ["retrieve"],
    "personal_data": ["find_course", "get_student_profile", "get_attendance", "get_results"],
    "personal_eligibility": ["find_course", "get_student_profile", "get_attendance", "get_results",
                             "resolve_rule", "check_exam_eligibility", "check_supplementary_eligibility",
                             "check_placement_eligibility", "retrieve"],
    "multi_step": ["find_course", "get_student_profile", "get_attendance", "get_results", "resolve_rule",
                   "check_exam_eligibility",
                   "check_supplementary_eligibility", "check_placement_eligibility", "retrieve"],
    "out_of_scope": ["retrieve"],
}

PERSONAL_INTENTS = {"personal_data", "personal_eligibility", "multi_step"}

# which parameter each eligibility tool depends on (used to pick the clause to cite)
TOOL_PARAMETERS = {
    "check_exam_eligibility": ["min_attendance_pct"],   # relaxation rules are read too, cited when used
    "check_supplementary_eligibility": ["supplementary_allowed_results", "min_total_marks_pct"],
    "check_placement_eligibility": ["placement_min_cgpa", "placement_max_backlogs"],
}

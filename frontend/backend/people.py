import re

OWNER_PATS  = [r"owner", r"resp", r"assign", r"engineer", r"in[\s_-]?charge", r"\bperson\b", r"\bby\b"]
DEPT_PATS   = [r"dept", r"department", r"section", r"discipline", r"\bteam\b", r"service group"]
EMAIL_PATS  = [r"e[\s_-]?mail"]
STATUS_PATS = [r"status", r"state", r"stage", r"progress"]
DATE_PATS   = [r"date", r"\bdue\b", r"target", r"\bplan", r"actual", r"completion"]

_TOTAL_ROW = re.compile(r"^\s*(grand\s+total|sub\s*total|total)\s*$", re.I)


def _find(names, pats):
    for n in names:
        ln = str(n).lower()
        if any(re.search(p, ln) for p in pats):
            return n
    return None


def column_map(columns):
    names = [c.get("name") if isinstance(c, dict) else c for c in (columns or [])]
    return {
        "owner":  _find(names, OWNER_PATS),
        "dept":   _find(names, DEPT_PATS),
        "email":  _find(names, EMAIL_PATS),
        "status": _find(names, STATUS_PATS),
        "date":   _find(names, DATE_PATS),
    }


def _is_total(row):
    for v in row.values():
        if isinstance(v, str) and _TOTAL_ROW.match(v):
            return True
    return False


def extract_people(sheets):
    """Return (people[], departments[]) derived from sheet rows."""
    people, depts = {}, set()
    for sh in sheets or []:
        cm = column_map(sh.get("columns", []))
        if not (cm["owner"] or cm["dept"] or cm["email"]):
            continue
        for r in sh.get("rows", []):
            if _is_total(r):
                continue
            name  = str(r.get(cm["owner"]) or "").strip() if cm["owner"] else ""
            dept  = str(r.get(cm["dept"])  or "").strip() if cm["dept"]  else ""
            email = str(r.get(cm["email"]) or "").strip() if cm["email"] else ""
            if dept:
                depts.add(dept)
            if name or email:
                key = (email or name).lower()
                people.setdefault(key, {"name": name or email, "email": email, "department": dept})
    return list(people.values()), sorted(depts)

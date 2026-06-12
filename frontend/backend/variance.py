"""Multi-sheet variance analysis."""
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import math
import re
import statistics
from difflib import SequenceMatcher

NUMERIC_FIELDS = ["tat", "days_taken", "overdue_days"]
TEXT_FIELDS = ["status", "criticality", "responsible_person", "stage", "reason_class"]


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _fuzzy(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def column_similarity(headers_a: List[str], headers_b: List[str]) -> float:
    if not headers_a or not headers_b:
        return 0.0
    a = {(h or "").strip().lower() for h in headers_a if h}
    b = {(h or "").strip().lower() for h in headers_b if h}
    if not a or not b:
        return 0.0
    inter = a & b
    return len(inter) / max(len(a), len(b))


def match_entities(
    sheets: Dict[str, List[Dict[str, Any]]], threshold: float = 0.8
) -> List[Dict[str, Any]]:
    """Group activities across sheets by name. Returns list of entity rows."""
    # Each entity: {key, values_by_sheet: {A: row, B: row, ...}}
    labels = sorted(sheets.keys())
    if not labels:
        return []
    primary = labels[0]
    entities: Dict[str, Dict[str, Any]] = {}
    for r in sheets[primary]:
        k = _key(r.get("activity") or "")
        if not k:
            continue
        entities.setdefault(k, {
            "key": k,
            "activity": r.get("activity"),
            "by_sheet": {},
        })["by_sheet"][primary] = r

    for label in labels[1:]:
        for r in sheets[label]:
            k = _key(r.get("activity") or "")
            if not k:
                continue
            # exact match
            if k in entities:
                entities[k]["by_sheet"][label] = r
                continue
            # fuzzy match
            best = None
            best_score = 0.0
            for existing_k in entities:
                s = _fuzzy(k, existing_k)
                if s > best_score:
                    best_score = s
                    best = existing_k
            if best and best_score >= threshold:
                entities[best]["by_sheet"][label] = r
            else:
                entities.setdefault(k, {
                    "key": k,
                    "activity": r.get("activity"),
                    "by_sheet": {label: r},
                })
    return list(entities.values())


def compute_variances(
    sheets: Dict[str, List[Dict[str, Any]]], threshold: float = 0.8
) -> Dict[str, Any]:
    labels = sorted(sheets.keys())
    entities = match_entities(sheets, threshold)

    variance_rows: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    for ent in entities:
        bys = ent["by_sheet"]
        present_labels = list(bys.keys())
        if len(present_labels) < len(labels):
            for L in labels:
                if L not in bys:
                    missing.append({
                        "activity": ent["activity"],
                        "missing_from_sheet": L,
                        "present_in": present_labels,
                    })

        row: Dict[str, Any] = {
            "activity": ent["activity"],
            "key": ent["key"],
            "sheets": {L: (bys.get(L) or {}).get("activity") for L in labels},
            "numeric": {},
            "deltas": {},
            "max_variance_pct": 0.0,
            "flag": "grey",
        }
        # numeric variances
        for f in NUMERIC_FIELDS:
            values = {}
            for L, r in bys.items():
                v = r.get(f)
                if isinstance(v, (int, float)):
                    values[L] = float(v)
            row["numeric"][f] = values
            if len(values) >= 2:
                vmin = min(values.values())
                vmax = max(values.values())
                spread = vmax - vmin
                pct = (spread / vmin * 100.0) if vmin > 0 else (100.0 if vmax > 0 else 0.0)
                row["deltas"][f] = {
                    "min": vmin, "max": vmax, "spread": round(spread, 2),
                    "pct": round(pct, 2),
                }
                if pct > row["max_variance_pct"]:
                    row["max_variance_pct"] = round(pct, 2)
        # conflicts on text fields
        for f in TEXT_FIELDS:
            values = {L: r.get(f) for L, r in bys.items() if r.get(f) not in (None, "")}
            distinct = set(values.values())
            if len(distinct) > 1:
                conflicts.append({
                    "activity": ent["activity"],
                    "field": f,
                    "values": values,
                })
        # flag color
        mvp = row["max_variance_pct"]
        if len(bys) < 2:
            row["flag"] = "grey"
        elif mvp > 50:
            row["flag"] = "red"
        elif mvp >= 10:
            row["flag"] = "orange"
        else:
            row["flag"] = "green"
        variance_rows.append(row)

    variance_rows.sort(key=lambda r: r["max_variance_pct"], reverse=True)

    # Outliers: variance >2 std from mean across activities (per numeric field)
    outliers: List[Dict[str, Any]] = []
    for f in NUMERIC_FIELDS:
        spreads = [r["deltas"].get(f, {}).get("pct", 0) for r in variance_rows if f in r["deltas"]]
        if len(spreads) >= 3:
            mu = statistics.mean(spreads)
            sd = statistics.pstdev(spreads) or 1.0
            for r in variance_rows:
                pct = r["deltas"].get(f, {}).get("pct")
                if pct is not None and pct > mu + 2 * sd:
                    outliers.append({
                        "activity": r["activity"],
                        "field": f,
                        "pct": pct,
                        "mean": round(mu, 2),
                        "std": round(sd, 2),
                    })

    # Source reliability: per-sheet vs others on TAT/days_taken
    reliability = _source_reliability(sheets, entities)

    # Multi-sheet consensus
    consensus = _consensus(entities, labels)

    # Column correlations: per pair of sheets, correlation across activities for each numeric field
    correlations = _column_correlations(sheets, entities, labels)

    summary = {
        "compared_sheets": len(labels),
        "matched": sum(1 for e in entities if len(e["by_sheet"]) >= 2),
        "unmatched": sum(1 for e in entities if len(e["by_sheet"]) < 2),
        "conflicts": len(conflicts),
        "outliers": len(outliers),
    }

    return {
        "summary": summary,
        "variance_rows": variance_rows,
        "conflicts": conflicts,
        "missing_entities": missing,
        "outliers": outliers,
        "source_reliability": reliability,
        "consensus": consensus,
        "correlations": correlations,
    }


def _source_reliability(
    sheets: Dict[str, List[Dict[str, Any]]], entities: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    labels = sorted(sheets.keys())
    out: List[Dict[str, Any]] = []
    if len(labels) < 2:
        return out
    # For each sheet, average % deviation from across-sheet mean for tat
    for L in labels:
        diffs: List[float] = []
        for ent in entities:
            vals = {Lx: r.get("tat") for Lx, r in ent["by_sheet"].items()
                    if isinstance(r.get("tat"), (int, float))}
            if L in vals and len(vals) >= 2:
                mean = sum(vals.values()) / len(vals)
                if mean > 0:
                    diffs.append((vals[L] - mean) / mean * 100.0)
        if diffs:
            avg = sum(diffs) / len(diffs)
            out.append({
                "sheet": L,
                "avg_tat_deviation_pct": round(avg, 2),
                "samples": len(diffs),
                "interpretation": (
                    f"Sheet {L} {'overestimates' if avg > 0 else 'underestimates'} TAT by "
                    f"{abs(round(avg,1))}% on average vs other sheets"
                ),
            })
    return out


def _consensus(entities: List[Dict[str, Any]], labels: List[str]) -> List[Dict[str, Any]]:
    if len(labels) < 3:
        return []
    out: List[Dict[str, Any]] = []
    for ent in entities:
        if len(ent["by_sheet"]) < 3:
            continue
        # Criticality consensus
        crits = [r.get("criticality") for r in ent["by_sheet"].values() if r.get("criticality")]
        if crits:
            from collections import Counter as _C
            c = _C(crits)
            top, cnt = c.most_common(1)[0]
            out.append({
                "activity": ent["activity"],
                "field": "criticality",
                "agreement": f"{cnt}/{len(ent['by_sheet'])}",
                "value": top,
            })
    return out


def _column_correlations(
    sheets: Dict[str, List[Dict[str, Any]]],
    entities: List[Dict[str, Any]],
    labels: List[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if len(labels) < 2:
        return out
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            La, Lb = labels[i], labels[j]
            for f in NUMERIC_FIELDS:
                xs: List[float] = []
                ys: List[float] = []
                for ent in entities:
                    ra = ent["by_sheet"].get(La)
                    rb = ent["by_sheet"].get(Lb)
                    if ra and rb and isinstance(ra.get(f), (int, float)) and isinstance(rb.get(f), (int, float)):
                        xs.append(float(ra[f]))
                        ys.append(float(rb[f]))
                if len(xs) >= 3:
                    r = _pearson(xs, ys)
                    out.append({
                        "sheet_a": La,
                        "sheet_b": Lb,
                        "field": f,
                        "r": round(r, 3),
                        "samples": len(xs),
                    })
    return out


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)

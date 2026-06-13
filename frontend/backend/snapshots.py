"""Daily snapshots + trends. snapshot_metrics() reduces each sheet to a compact metric
record (row count, numeric sums, quality score, anomaly count) that's cheap to store daily;
compute_trends() turns a series of those into time series + a 'what changed' diff."""
from collections import defaultdict
from typing import Any, Dict, List

from dashboards import _infer_columns, _to_number
from insights import _is_total_row, _quality_for_sheet, build_anomalies


def snapshot_metrics(sheets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for s in sheets:
        all_rows = s.get("rows_raw") or []
        rows = [r for r in all_rows if not _is_total_row(r)]
        headers = list(all_rows[0].keys()) if all_rows else (s.get("headers") or [])
        cols = _infer_columns(all_rows, headers)
        numeric = [c["name"] for c in cols if c["type"] == "number"]
        sums = {col: round(sum(_to_number(r.get(col)) or 0 for r in rows), 2) for col in numeric}
        q = _quality_for_sheet(s)
        an = build_anomalies([s])
        out.append({"label": s.get("label"), "row_count": len(all_rows),
                    "numeric_sums": sums, "quality_score": q["score"],
                    "anomaly_count": an.get("count", 0)})
    return out


def compute_trends(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    series = []
    for sn in snaps:
        sheets = sn.get("sheets", [])
        qs = [x.get("quality_score") for x in sheets if x.get("quality_score") is not None]
        merged = defaultdict(float)
        for x in sheets:
            for k, v in (x.get("numeric_sums") or {}).items():
                merged[k] += v
        series.append({
            "date": sn.get("date"),
            "total_rows": sum(x.get("row_count", 0) for x in sheets),
            "quality": round(sum(qs) / len(qs), 1) if qs else None,
            "anomalies": sum(x.get("anomaly_count", 0) for x in sheets),
            "numeric_sums": dict(merged),
        })

    changes = []
    if len(series) >= 2:
        a, b = series[-2], series[-1]
        if b["total_rows"] != a["total_rows"]:
            d = b["total_rows"] - a["total_rows"]
            changes.append({"metric": "rows", "delta": d,
                            "text": f"Rows {'+' if d > 0 else ''}{d} ({a['total_rows']} → {b['total_rows']})"})
        if a["quality"] is not None and b["quality"] is not None and b["quality"] != a["quality"]:
            d = round(b["quality"] - a["quality"], 1)
            changes.append({"metric": "quality", "delta": d,
                            "text": f"Quality {'+' if d > 0 else ''}{d} ({a['quality']} → {b['quality']})"})
        for k in sorted(set(list(a["numeric_sums"]) + list(b["numeric_sums"]))):
            av, bv = a["numeric_sums"].get(k, 0), b["numeric_sums"].get(k, 0)
            d = round(bv - av, 2)
            if d != 0:
                changes.append({"metric": k, "delta": d,
                                "text": f"{k} {'+' if d > 0 else ''}{d:,} ({av:,} → {bv:,})"})
    return {"series": series, "changes": changes}

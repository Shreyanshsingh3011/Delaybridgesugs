"""Alert rules — evaluate threshold/change rules against snapshot metrics.
A rule: {label?, metric, op, threshold, webhook_url?}
  metric: 'total_rows' | 'quality' | 'anomalies' | a numeric column name (sum)
  op: 'gt' | 'lt' | 'change_pct'  (change_pct compares to the previous snapshot)
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional


def aggregate_metrics(sheet_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    qs = [x.get("quality_score") for x in sheet_metrics if x.get("quality_score") is not None]
    sums = defaultdict(float)
    for x in sheet_metrics:
        for k, v in (x.get("numeric_sums") or {}).items():
            sums[k] += v
    return {
        "total_rows": sum(x.get("row_count", 0) for x in sheet_metrics),
        "quality": round(sum(qs) / len(qs), 1) if qs else None,
        "anomalies": sum(x.get("anomaly_count", 0) for x in sheet_metrics),
        "sums": dict(sums),
    }


def _value(metrics: Dict[str, Any], metric: str):
    if metric in ("total_rows", "quality", "anomalies"):
        return metrics.get(metric)
    return (metrics.get("sums") or {}).get(metric)


def evaluate_rules(rules: List[Dict[str, Any]], cur: Dict[str, Any],
                   prev: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    triggered = []
    for r in rules or []:
        metric, op = r.get("metric"), r.get("op")
        try:
            thr = float(r.get("threshold"))
        except (TypeError, ValueError):
            continue
        v = _value(cur, metric)
        if v is None:
            continue
        hit, msg = False, None
        if op == "gt" and v > thr:
            hit, msg = True, f"{metric} is {v} (> {thr})"
        elif op == "lt" and v < thr:
            hit, msg = True, f"{metric} is {v} (< {thr})"
        elif op == "change_pct" and prev is not None:
            pv = _value(prev, metric)
            if pv:
                pct = abs(v - pv) / abs(pv) * 100
                if pct >= thr:
                    hit, msg = True, f"{metric} changed {round(pct, 1)}% ({pv} → {v})"
        if hit:
            triggered.append({
                "label": r.get("label") or metric, "metric": metric, "op": op,
                "threshold": thr, "value": v, "message": msg, "webhook_url": r.get("webhook_url"),
            })
    return triggered

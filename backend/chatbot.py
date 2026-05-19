"""Chatbot — Anthropic Claude via Emergent Universal LLM Key.
Admin/Analyst mode and Dependent Person mode."""
import os
import json
import logging
from typing import Optional, Dict, Any, List

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

# Per user request: claude-sonnet-4-20250514. The current emergentintegrations supports
# claude-sonnet-4-5-20250929 from the Claude 4 family. We map to the closest available.
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

ADMIN_SUGGESTIONS = [
    "What is the current risk score and why?",
    "Who is causing the most downstream damage?",
    "Show me the critical path",
    "Which sheets have the biggest variance?",
    "Predict project completion date",
    "Top 3 improvements to unblock most tasks",
]

DEPENDENT_SUGGESTIONS = [
    "Why is my work blocked?",
    "When will I be unblocked?",
    "Who else is waiting like me?",
    "Should I escalate?",
    "What can I prepare while I wait?",
]


def _truncate(obj: Any, max_chars: int = 12000) -> str:
    s = json.dumps(obj, default=str)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...[truncated]"


def build_admin_system_prompt(analysis: Dict[str, Any], sheets_meta: List[Dict[str, Any]]) -> str:
    compact = {
        "mode": analysis.get("mode"),
        "totals": analysis.get("totals"),
        "risk_score": analysis.get("risk_score"),
        "top_delay_reasons": analysis.get("top_delay_reasons"),
        "person_ranking": (analysis.get("person_ranking") or [])[:10],
        "department_ranking": (analysis.get("department_ranking") or [])[:10],
        "critical_path": (analysis.get("dependency_chains") or {}).get("critical_path"),
        "at_risk_count": len((analysis.get("dependency_chains") or {}).get("at_risk_activities", [])),
        "chains_summary": [
            {
                "root_activity": c.get("root_activity"),
                "root_person": c.get("root_person"),
                "downstream_count": c.get("downstream_count"),
                "accumulated_days": c.get("accumulated_days"),
            }
            for c in (analysis.get("dependency_chains") or {}).get("chains", [])[:10]
        ],
        "variance_summary": (analysis.get("variance") or {}).get("summary"),
        "variance_top": (analysis.get("variance") or {}).get("variance_rows", [])[:10],
        "flags": [
            {
                "id": f.get("id"),
                "activity": f.get("activity"),
                "person": (f.get("flagged_to") or {}).get("person"),
                "severity": f.get("severity"),
                "overdue_days": f.get("overdue_days"),
                "reason": f.get("reason"),
            }
            for f in analysis.get("flags", [])[:25]
        ],
        "sheets": sheets_meta,
    }
    return (
        "You are DelayBridge AI — a project delay intelligence assistant. "
        "Answer ONLY from the live project data below. Do NOT use external knowledge. "
        "Cite actual activity names, person names, delay reasons, and dependency chains "
        "from the data. If something is not in the data, say so. Keep replies tight, "
        "structured, and action-oriented.\n\n"
        "=== LIVE PROJECT DATA (JSON) ===\n"
        + _truncate(compact)
    )


def build_dependent_system_prompt(
    analysis: Dict[str, Any],
    person: Dict[str, Any],
    blocked: List[Dict[str, Any]],
    my_activities: List[Dict[str, Any]],
) -> str:
    compact = {
        "person": person,
        "my_activities": my_activities,
        "blocked_by": blocked,
        "risk_score": analysis.get("risk_score"),
        "totals": analysis.get("totals"),
    }
    return (
        "You are DelayBridge AI in DEPENDENT PERSON MODE. "
        "You speak directly to "
        f"{person.get('name') or person.get('email')}. "
        "Use ONLY their personal blocked-by information below. "
        "Be empathetic, concise, action-oriented. Always reference real activity names "
        "and the blocking person's name from the data. Tell them: why blocked, who is "
        "blocking, expected impact, what to do, and others affected.\n\n"
        "=== PERSON DATA (JSON) ===\n" + _truncate(compact)
    )


async def chat_send(
    api_key: str,
    session_id: str,
    system_prompt: str,
    message: str,
) -> str:
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system_prompt,
    ).with_model("anthropic", CLAUDE_MODEL)
    resp = await chat.send_message(UserMessage(text=message))
    return resp

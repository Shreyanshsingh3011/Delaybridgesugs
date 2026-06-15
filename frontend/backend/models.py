"""Pydantic models for DelayBridge."""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============ Auth ============
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str


# ============ Sessions ============
class SessionCreate(BaseModel):
    name: str = "Untitled Project"


class SheetAdd(BaseModel):
    url: str
    label: Optional[str] = None  # A/B/C/D/E - auto-assigned if None


class ColumnMapping(BaseModel):
    """Map source columns to standard fields."""
    activity: Optional[str] = None
    criticality: Optional[str] = None
    responsible_person: Optional[str] = None
    responsible_email: Optional[str] = None
    responsible_phone: Optional[str] = None
    start_date: Optional[str] = None
    tat: Optional[str] = None
    days_taken: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    dependency: Optional[str] = None
    stage: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    email: Optional[str] = None  # if provided, switches to dependent person mode
    session_id: Optional[str] = None  # chat session id for multi-turn


class FlagAction(BaseModel):
    note: Optional[str] = None


class CopilotRequest(ChatRequest):
    sheets: Optional[List[str]] = None  # multi-sheet copilot: combine context across these labels


# ============ Concerns / Reminders ============
class ConcernCreate(BaseModel):
    raised_by: str
    raised_by_department: Optional[str] = None
    target_department: str
    sheet_label: Optional[str] = None
    activity_ref: Optional[str] = None
    title: str
    detail: Optional[str] = None
    severity: Optional[str] = "medium"


class ConcernUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class ReminderCreate(BaseModel):
    related_type: str
    related_id: Optional[str] = None
    recipient_email: EmailStr
    subject: str
    body: str
    schedule_at: Optional[str] = None
    recurrence: Optional[str] = "none"


# ============ Public Shapes ============
class SheetMeta(BaseModel):
    label: str
    url: str
    name: Optional[str] = None
    rows: int = 0
    columns: int = 0
    last_fetched: Optional[str] = None
    connected: bool = False
    color: str = "blue"


STANDARD_FIELDS = [
    "activity",
    "criticality",
    "responsible_person",
    "responsible_email",
    "responsible_phone",
    "start_date",
    "tat",
    "days_taken",
    "status",
    "reason",
    "dependency",
    "stage",
]

SHEET_COLORS = {"A": "blue", "B": "orange", "C": "purple", "D": "green", "E": "red"}

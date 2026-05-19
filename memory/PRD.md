# DelayBridge — PRD

## Original Problem Statement
Build a project delay intelligence and multi-sheet variance analysis system called **DelayBridge**.

One Google Sheet connected via Apps Script Web App URL is the single source of truth for delay analysis, correlation, flagging, alerts, and reporting. When 2+ sheets of the same data type are connected, variance analysis activates automatically. All automation (SMS, email, escalation, chatbot triggers) runs natively from the backend (no Make.com / Zapier / n8n).

## User decisions
- **Build scope**: Phase 1 — Sheet ingest + Delay correlation + Variance + Flags + AI Chatbot. **Backend only** (dashboard will be built in Lovable consuming public API).
- **AI model**: Anthropic Claude Sonnet via **Emergent Universal LLM key** (closest available: `claude-sonnet-4-5-20250929`).
- **Alerts (SMS/Email)**: **MOCKED** — logged to DB and returned via `/alerts`. No Twilio/SendGrid wired.
- **PDF reports**: Deferred to Phase 2 (ReportLab chosen).
- **Auth**: JWT admin login.

## Tech stack
- Backend: FastAPI (Python), MongoDB (motor), APScheduler (deferred to phase 2)
- AI: `emergentintegrations.llm.chat.LlmChat` → Anthropic
- Reports (P2): ReportLab + openpyxl

## Architecture (backend modules)
- `server.py` — app entrypoint, startup, CORS, routers
- `auth.py` — bcrypt + JWT, admin seed
- `models.py` — Pydantic schemas
- `sheet_fetcher.py` — Apps Script URL fetch + validation
- `normalizer.py` — column detection + normalization to standard schema
- `analysis.py` — reason classification, correlation matrix, dependency chains, person/dept/timeline ranks, risk score
- `variance.py` — entity matching, numeric/text variance, conflicts, outliers, source reliability, consensus, Pearson correlation per pair of sheets
- `flags.py` — delay flag generation + downstream lookup
- `chatbot.py` — admin & dependent system prompts + LlmChat wrapper
- `demo_data.py` — NIT-76 Operations 79-row dataset (single source + variant B for variance demo)
- `routes_admin.py` — JWT-protected admin endpoints
- `routes_public.py` — public token endpoints (Lovable / Apps Script consumers)

## What's implemented (2026-02)
- ✅ JWT admin auth (login/logout/me), admin seeded from env
- ✅ Session + sheet CRUD (up to 5 sheets per session, A–E labels)
- ✅ Apps Script Web App URL fetch & validation
- ✅ Column auto-detection + manual mapping endpoint
- ✅ Normalisation + data-quality report
- ✅ Reason classification (Approval Pending / Resource / Dependency / External / Design / Documentation / Other)
- ✅ Reason × reason correlation matrix (per-dept co-occurrence)
- ✅ Dependency chain BFS with accumulated days + critical path
- ✅ Person/department/timeline ranking, top delay reasons
- ✅ Risk score (0-100)
- ✅ Multi-sheet variance: entity match (exact+fuzzy), numeric deltas, conflicts, outliers (>2σ), source reliability, consensus (3+ sheets), Pearson correlation
- ✅ Flag generation (delay + variance flags) with downstream persons + severity
- ✅ Flag acknowledge / resolve endpoints
- ✅ Downstream lookup by email (returns blocked-by chains for a person)
- ✅ AI Chatbot (Claude Sonnet 4.5) — admin & dependent person modes
- ✅ Dependent person "pressure loop" — every dependent chat triggers MOCKED SMS+Email to blocker, logs to alert_log, marks flag `Escalated by Dependent`
- ✅ Demo data: NIT-76 Operations 79-row dataset auto-loads on demo token
- ✅ Public token endpoints: full analysis, flags, variances, correlations, dependencies, downstream, chat, suggestions, history, alerts, refresh, onboarding, status

## Public Demo
- Token: `demo-nit76-operations`
- Hit `GET /api/public/demo-nit76-operations` to get full analysis JSON

## Admin credentials
- Email: `admin@delaybridge.io`
- Password: `DelayBridge#2026`

## P0/P1 backlog (Phase 2)
- **P1** SMS via Twilio + Email via SendGrid (replace MOCKED status with real send)
- **P1** APScheduler escalation timers (L1/L2/L3) + daily 9 AM digest
- **P1** PDF report (ReportLab) — 8 sections per spec
- **P1** Excel report (openpyxl) — 6 sheets per spec
- **P1** Auto-refresh background job (every 30 min) on connected sheets
- **P2** Email config admin panel + per-session recipients
- **P2** WebSocket / SSE for live dashboard updates
- **P2** Per-user analyst accounts (currently single admin)

## Next action items
1. Validate via `testing_agent_v3` (backend only)
2. Wire Lovable frontend to public API
3. Phase 2: Twilio + SendGrid + PDF/Excel reports + APScheduler

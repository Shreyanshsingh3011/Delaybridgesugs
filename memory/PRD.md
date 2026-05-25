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

---

## Phase 1B update — 2026-02 (Frontend + Export Composer)
- ✅ Login page (JWT bearer stored as `db_token`)
- ✅ Builder shell — header, project picker, step indicator, logout
- ✅ **Step 1 — Connect Sheets**: paste up to 5 Apps Script URLs (labels A–E), refresh/remove, detected-mapping chips, data-quality stats, preview rows, setup guide with code copy, "Load demo data"
- ✅ **Step 2 — Configure Export**: 4 grouped field-toggle cards (Overview / Delay analysis / Variance / Flags), Run analysis, persisted export-config
- ✅ **Step 3 — Get Link**: composed URL `${BACKEND}/api/public/{token}/export?fields=...` + 8 slice URLs + Live preview tab + Code snippets (Lovable / Apps Script / cURL)
- ✅ New backend endpoints:
  - `GET /api/public/{token}/export?fields=` — composable JSON
  - `GET/POST /api/sessions/{id}/export-config` — persist field selection
- ✅ Testing: 53/53 backend tests pass, all frontend flows verified

---

## Phase 1C — Dependency Mapping Studio (2026-05)

A new module: visual architecture / dependency intelligence platform built on React Flow.

### Backend (FastAPI)
`/app/backend/routes_studio.py`:
- `POST /api/studio/fetch` — proxy fetch any Apps Script JSON endpoint
- `POST /api/studio/maps` — create new map (returns share_token, default mode=private)
- `GET /api/studio/maps` — list user maps
- `GET /api/studio/maps/{id}` — load
- `PUT /api/studio/maps/{id}` — save full graph state (title, nodes, edges, source_url, notes)
- `DELETE /api/studio/maps/{id}`
- `POST /api/studio/maps/{id}/share` — set mode public/private/readonly/editable
- `POST /api/studio/maps/{id}/analyze` — server-side analytics
- `GET  /api/studio/public/{token}` — load shared map (no auth)
- `PUT  /api/studio/public/{token}` — edit shared map (only if mode==editable)
- `GET  /api/studio/public/{token}/analyze`

Analytics include:
- in-degree, out-degree, orphans, roots, sinks
- cycle detection (DFS)
- topological order (Kahn) — DAG check
- bottlenecks (high (in+out)), excessive coupling (>6), redundant duplicate edges
- broken-chain edges, bad architectural patterns (UI→DB direct)
- scores: health, dependency, complexity (each 0–100)
- rule-based insights (severity: danger/warning/info/success)

### Frontend (React + React Flow + Tailwind + zustand + dagre + html-to-image + framer-motion)
- `/app/frontend/src/pages/Studio.jsx` — main page (3-panel layout)
- `/app/frontend/src/pages/SharedMap.jsx` — public/share view (readonly + editable modes)
- `/app/frontend/src/studio/store.js` — zustand store
- `/app/frontend/src/studio/analytics.js` — instant client-side analysis
- `/app/frontend/src/studio/autolayout.js` — dagre LR/TB + lightweight force layout
- `/app/frontend/src/studio/CustomNode.jsx` — category-coded icons, status dot, tags, stage
- `/app/frontend/src/studio/CustomEdge.jsx` — animated, type-coloured, label pill
- `/app/frontend/src/studio/LeftSidebar.jsx` — Apps Script connector, manual node library, 3 templates, search & filter
- `/app/frontend/src/studio/RightInspector.jsx` — scores, AI insights, full analytics, node editor (with incoming/outgoing lists), edge editor
- `/app/frontend/src/studio/TopBar.jsx` — title, zoom, fit, auto-arrange LR/TB/Force, export PNG/SVG/JSON, share modal, save

### Routes added in `App.js`
- `/studio` → auto-creates/loads first map and redirects to `/studio/:mapId`
- `/studio/:mapId` → editor (auth required)
- `/studio/share/:token` → public/shared view (no auth required)

### Builder header
- Added `Dependency Studio` button next to logout that navigates to `/studio`

### What works end-to-end (verified)
- Fetch Apps Script URL → records auto-become nodes
- Insert templates → multiple nodes + edges materialise
- Drag, connect, rename, duplicate, delete nodes
- Edit edge type/priority/label
- Auto-arrange LR / TB / Force
- Save / load / list / delete maps
- Share token + 4 modes (private/public/readonly/editable)
- Public viewer with editable-mode write-back via PUT
- Export PNG / SVG / JSON
- Live scores + insights + analytics summary updating with each change

---

## Phase 1D — Column Dependency Chaining Subsystem (2026-02-25)

A second tab inside `/studio` ("Column chain DAG") for authoring **DAG-of-columnId**
dependencies — fully client-side, encoded into the same Base64URL share link.

### Files
- `/app/frontend/src/studio/chainGraph.js` — pure algorithms (buildReach, wouldCreateCycle, nodeInspection, topoSort, computeRewire, withoutNode, upsertEdge)
- `/app/frontend/src/studio/ColumnChainStudio.jsx` — 3-panel UI (authoring · graph · inspector)
- `/app/frontend/src/studio/store.js` — `chainNodes`, `chainEdges`, `chainSelected` slice with `commitChainEdge`, `deleteChainEdge`, `deleteChainNode(mode)`, `addChainNodes`, `selectChainNode`, `resetChains`
- `/app/frontend/src/studio/codec.js` — bumped VERSION=2; encodes only `direct` + `skip` edges (transitive re-derived on import); decoder accepts v=1 or v=2 (backwards compatible)
- `/app/frontend/src/pages/Studio.jsx` — tab switcher Resolver ↔ Chain DAG; share modal now exposes chain stats and raw payload

### Capabilities
- DAG nodes = columnIds; edges have kind ∈ {`direct`, `skip`}
- **Transitive Inference Engine**: reachability index built on-the-fly; transitive edges never stored, never drawn
- **Cycle prevention** at commit-time with explicit toast feedback
- **Duplicate** and **self-loop** prevention
- **Inspector** per node: direct preds/succs, skip in/out, transitive ancestors/descendants, topo order, incident-edge list
- **Intermediate node deletion** with 2 strategies:
  - Disconnect — drops all incident edges
  - Rewire — inserts P×S new direct edges (Cartesian product of direct predecessors × direct successors) then drops the node
- **Lossless serialization** into Base64URL share link

### Verified by `/app/test_reports/iteration_4.json`
- 30/30 pure-algorithm tests pass
- 14/14 UI spec items pass (cycle prevention, rewire, round-trip, etc.)
- No critical regressions

### Phase 1D.1 — Frontend Export (2026-02-25)

Stateless export of the resolved chain to **any** external frontend (Lovable / Bubble / plain React).

**Backend**
- `GET /api/studio/resolve?d=<base64url-token>` (public, no auth — the token is the auth):
  decodes the share token (v1 OR v2), derives full transitive closure, and emits:
  `{ version, source, edges, chain: { nodes, directEdges, skipEdges, transitive, topoOrder, isDAG, stats } }`.
  Verified via curl: v=2 chain `A→B→C, A⤳C` correctly resolves descendants/ancestors and topoOrder.

**Frontend**
- New header button `Export to frontend` (next to Reset / Share link) opens a modal mounting
  `/app/frontend/src/studio/StudioExportPanel.jsx`.
- The panel exposes:
  - Resolve URL (copyable)
  - Lovable / Vanilla JS / cURL / Schema snippets (tabbed)
  - One-click **Download JSON** of the resolved chain
  - **Preview resolved** modal showing the server response live

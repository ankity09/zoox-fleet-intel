# Chat UI + Fleet Deployment Demo Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 chat UI issues and add an end-to-end fleet deployment demo scenario with human-in-the-loop action cards.

**Architecture:** Single-file HTML/JS frontend (`app/frontend/src/index.html`) + FastAPI backend (`app/backend/main.py`). Changes are deployed via `databricks workspace import` + `databricks apps deploy`. No build step needed for the HTML frontend.

**Tech Stack:** Vanilla JS, CSS custom properties, FastAPI (Python), Lakebase (PostgreSQL), Databricks MAS supervisor API

---

## Bugs Found During Analysis

Before implementing features, two bugs need to be fixed:

1. **History sidebar bug:** `loadChatSessions()` is called on page load but NOT after `sendChat()` completes. So sessions are saved to Lakebase but the sidebar never refreshes.

2. **handleActionCard URL bug:** The function builds the URL as `/api/${cardType}s/${entityId}` — for `fleet_action` this becomes `/api/fleet_actions/1` but the real endpoint is `/api/fleet/fleet-actions/1`. Same bug for `surge_alert` → `/api/surge_alerts/1` vs `/api/fleet/surge-alerts/1`.

---

## Task 1: Fix History Sidebar (Bug Fix)

**Files:**
- Modify: `app/frontend/src/index.html`

**What:** Call `loadChatSessions()` at the end of `sendChat()` so the sidebar refreshes after each message.

**Step 1: Find the end of sendChat() where cleanup happens**

Search for `_chatStreaming = false` in `index.html` — this is in the `finally` block of `sendChat()`.

**Step 2: Add loadChatSessions() call**

In the `finally` block of `sendChat()`, after setting `_chatStreaming = false` and restoring the send button, add:

```javascript
// After the existing cleanup code in sendChat() finally block:
loadChatSessions();
```

Also add after `newChatSession()` creates the session:
```javascript
async function newChatSession() {
  try { await fetch('/api/chat/sessions/new', {method:'POST'}); } catch(_) {}
  document.getElementById('chat-messages-inner').innerHTML = '';
  _lastUserMessage = '';
  loadChat();  // loadChat already calls loadChatSessions()
}
```

**Step 3: Verify**

Open the app, send a message, check that the sidebar shows the session after the response completes.

---

## Task 2: Fix handleActionCard URL Bug (Bug Fix)

**Files:**
- Modify: `app/frontend/src/index.html`
- Modify: `app/backend/main.py` (add missing PATCH endpoint)

**Step 1: Fix the URL mapping in handleActionCard**

Find this code in `handleActionCard` (~line 1884):
```javascript
const url = '/api/' + cardType + 's/' + entityId;
```

Replace with a proper map:
```javascript
const urlMap = {
  'fleet_action': '/api/fleet/fleet-actions/' + entityId,
  'surge_alert': '/api/fleet/surge-alerts/' + entityId,
  'workflow': '/api/workflows/' + entityId,
};
const url = urlMap[cardType];
if (!url) { console.warn('Unknown cardType:', cardType); return; }
```

**Step 2: Add PATCH /api/fleet/fleet-actions/{action_id} to backend**

In `main.py`, find the block that has `@app.get("/api/fleet/fleet-actions")` and add after it:

```python
@app.patch("/api/fleet/fleet-actions/{action_id}")
async def update_fleet_action(action_id: int, body: dict):
    """Update fleet action status (approve, dismiss, execute)."""
    new_status = body.get("status", "")
    allowed = ("approved", "dismissed", "executed", "failed")
    if new_status not in allowed:
        raise HTTPException(400, f"Status must be one of: {allowed}")
    set_parts = ["status = %s"]
    params: list = [new_status]
    if new_status in ("approved", "executed"):
        set_parts.append("executed_at = NOW()")
    params.append(action_id)
    result = await asyncio.to_thread(
        write_pg,
        f"UPDATE fleet_actions SET {', '.join(set_parts)} WHERE action_id = %s RETURNING *",
        tuple(params),
    )
    if not result:
        raise HTTPException(404, f"Fleet action {action_id} not found")
    return result
```

**Step 3: Verify endpoint exists for surge_alerts**

Confirm `PATCH /api/fleet/surge-alerts/{alert_id}` already exists in `main.py` (it does — no changes needed).

---

## Task 3: User Messages on Right Side

**Files:**
- Modify: `app/frontend/src/index.html`

**Step 1: Add CSS for user message alignment**

Find the CSS block containing `.chat-msg-row` styles. After the existing `.chat-msg-row` rule, add:

```css
/* User messages right-aligned */
.chat-msg-row.user-row { flex-direction: row-reverse; }
.chat-msg-row.user-row .chat-msg-content { align-items: flex-end; }
.chat-msg-row.user-row .chat-msg-header { flex-direction: row-reverse; }
.user-bubble {
  background: var(--accent-subtle);
  border-radius: 14px 14px 4px 14px;
  padding: 8px 12px;
  display: inline-block;
  max-width: 100%;
}
```

**Step 2: Update createUserMsgBlock() to use right-aligned layout**

Find `function createUserMsgBlock(text)` and replace its return statement:

```javascript
function createUserMsgBlock(text) {
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  return `<div class="chat-msg-block">
    <div class="chat-msg-row user-row">
      <div class="chat-msg-avatar user-avatar">Y</div>
      <div class="chat-msg-content">
        <div class="chat-msg-header"><span class="chat-msg-time">${timeStr}</span><span class="chat-msg-name">You</span></div>
        <div class="chat-msg-body"><span class="user-bubble">${escHtml(text)}</span></div>
      </div>
    </div>
  </div>`;
}
```

**Step 3: Visual check**

Send a test message and confirm it appears right-aligned with a subtle teal bubble.

---

## Task 4: Expandable/Collapsible Tool Call Steps

**Files:**
- Modify: `app/frontend/src/index.html`

**Step 1: Add CSS for expandable steps**

Find the CSS block for `.chat-step-v2`. Add after the existing styles:

```css
/* Expandable steps */
.chat-step-v2.expandable .step-header { cursor: pointer; display: flex; align-items: center; gap: 4px; }
.chat-step-v2.expandable .step-header:hover .step-label { color: var(--accent); }
.step-chevron {
  font-size: 9px;
  color: var(--text-muted);
  transition: transform 0.2s;
  display: inline-block;
  flex-shrink: 0;
}
.chat-step-v2.step-open .step-chevron { transform: rotate(90deg); }
.step-expanded {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--steel-bg);
  border-radius: 6px;
  border-left: 2px solid var(--accent);
  max-height: 280px;
  overflow-y: auto;
  display: none;
}
.chat-step-v2.step-open .step-expanded { display: block; }
.step-expanded-inner { font-size: 11px; color: var(--text); line-height: 1.5; }
.step-expanded-inner p { margin: 0 0 4px; }
.step-expanded-inner table { font-size: 10px; }
.step-expanded-inner pre { font-size: 10px; overflow-x: auto; }
```

**Step 2: Add toggleStep() function**

Add this function anywhere near the other step-management functions (`addStep`, `deactivateSteps`, `_collapseSteps`):

```javascript
function toggleStep(el) {
  el.classList.toggle('step-open');
}
```

**Step 3: Modify how sub_result stores content on the step**

In `sendChat()`, find the `sub_result` handling block that calls `addStep(stepsEl, 'data', ...)`. After the step is created (after `addStep`), add:

```javascript
// After: const stepEl = addStep(stepsEl, 'data', 'Received data from ' + label, false);

// Make step expandable with full content
if (evt.text && evt.text.length > 20) {
  stepEl.classList.add('expandable');
  stepEl.dataset.fullContent = evt.text;
  // Replace step-info children with a header + hidden expanded div
  const stepInfo = stepEl.querySelector('.step-info');
  const labelEl = stepInfo.querySelector('.step-label');
  // Wrap label in clickable header
  const header = document.createElement('div');
  header.className = 'step-header';
  header.setAttribute('onclick', 'toggleStep(this.closest(\'.chat-step-v2\'))');
  header.appendChild(labelEl);
  const chevron = document.createElement('span');
  chevron.className = 'step-chevron';
  chevron.textContent = '\u25B8';
  header.appendChild(chevron);
  stepInfo.insertBefore(header, stepInfo.firstChild);
  // Add expandable content area
  const expanded = document.createElement('div');
  expanded.className = 'step-expanded';
  const inner = document.createElement('div');
  inner.className = 'step-expanded-inner';
  inner.innerHTML = formatMd(evt.text);
  expanded.appendChild(inner);
  stepInfo.appendChild(expanded);
}
```

**Note:** The existing preview (from `extractDataPreview`) can be removed since the expandable content shows the full data. Find the existing `previewEl` creation block in `sub_result` handling and remove it, OR keep it alongside the chevron (your choice — keeping it gives a compact preview before expanding).

**Step 4: Visual check**

Send a fleet status query and verify each "Received data from..." step has a ▸ chevron. Click it to expand the full response.

---

## Task 5: Update Example Questions (SUGGESTED array)

**Files:**
- Modify: `app/frontend/src/index.html`

**Step 1: Find the SUGGESTED array**

Search for `const SUGGESTED = [` in `index.html` (~line 2037).

**Step 2: Replace with 6 multi-agent demo questions**

```javascript
const SUGGESTED = [
  "The Vegas Sphere concert ends at 10PM tonight — analyze vehicle availability in LV-SPHERE and create a deployment plan",
  "Raiders game at Allegiant Stadium in 2 hours — forecast demand for LV-ARENA and deploy vehicles if needed",
  "Which Las Vegas zones are critically understaffed right now? Show me current vs needed vehicles.",
  "Move surplus vehicles from low-demand SF zones to SF-EMBARCADERO where demand is spiking",
  "Show all open surge alerts and recommend which zones need immediate attention",
  "What's the demand forecast for SF-EMBARCADERO for the next 4 hours and how many vehicles should we pre-position?",
];
```

**Step 3: Visual check**

Navigate to the chat page and confirm 6 questions appear in the welcome screen. The grid may need CSS adjustment — verify layout looks good at 2-column 3-row.

---

## Task 6: Add PATCH /api/fleet/fleet-actions/{id} + Verify Data (Backend)

Already covered in Task 2, Step 2. But also verify the events data supports the demo narrative.

**Files:**
- Read: `notebooks/02_generate_data.py`

**Step 1: Verify events data has Sphere concert at ~22:00**

Read the events generation in `notebooks/02_generate_data.py` and check if:
- There's an event with `venue` containing "Sphere"
- Its `end_time` is near 22:00 (or a reasonable demo time)
- `zone_id = 'LV-SPHERE'`

**Step 2: Verify demand_forecasts data**

Check that `demand_forecasts` has entries for `zone_id = 'LV-SPHERE'` with `demand_score > 8.0`.

**Step 3: If data is wrong, update the events generation**

In `02_generate_data.py`, ensure at least one event has:
```python
{
  "venue": "MSG Sphere Las Vegas",
  "event_name": "Imagine Dragons Concert",
  "zone_id": "LV-SPHERE",
  "city": "Las Vegas",
  "end_time": "22:00",  # or end_timestamp near tonight
  "expected_attendance": 15000,
}
```

And a demand_forecast entry:
```python
{"zone_id": "LV-SPHERE", "city": "Las Vegas", "forecast_hour": 22, "demand_score": 9.2, ...}
```

If updates needed, re-run the notebook in the Databricks workspace.

---

## Task 7: Update MAS Supervisor Instructions

**Files:** None — API call only

**Step 1: Get current MAS config**

```bash
databricks api get /api/2.0/multi-agent-supervisors/7bd87eff-35e4-467e-b1eb-b7d376eeec5f \
  --profile=ay-sandbox -o json | jq '{name: .name, agents: .agents, instructions: .instructions}'
```

Save the output — you need `name` and `agents` for the PATCH (Gotcha #3: must include all fields).

**Step 2: PATCH instructions with fleet deployment workflow**

```bash
databricks api put /api/2.0/multi-agent-supervisors/7bd87eff-35e4-467e-b1eb-b7d376eeec5f \
  --profile=ay-sandbox \
  --json '{
    "name": "zoox-fleet-advisor",
    "agents": [
      {
        "agent_type": "genie-space",
        "genie_space": {"id": "01f1163666db1ea8a42a4f5dfb194c90"},
        "name": "zoox-fleet-data-space",
        "description": "Query Zoox fleet analytics data: vehicles, rides, events, zones, demand_forecasts tables in Delta Lake. Use for historical analysis, demand forecasting, event lookups, and zone statistics."
      },
      {
        "agent_type": "external-mcp-server",
        "external_mcp_server": {"connection_name": "zoox-fleet-lakebase-mcp"},
        "name": "mcp-lakebase-connection",
        "description": "Write operational data to Lakebase PostgreSQL tables. Use for creating fleet_actions (vehicle deployments, rebalancing), surge_alerts, dispatch_overrides, and updating their statuses."
      }
    ],
    "instructions": "You are the Zoox Fleet Intelligence Supervisor. You coordinate between two sub-agents:\n\n1. zoox-fleet-data-space (Genie) - queries Delta Lake for analytics: vehicles status, ride history, demand forecasts, events, zone statistics\n2. mcp-lakebase-connection (Lakebase MCP) - writes to PostgreSQL: creates fleet_actions, surge_alerts, dispatch_overrides\n\n## Fleet Deployment Workflow\n\nWhen asked about vehicle availability for events:\n1. Query Genie for: events (venue, end_time, zone_id), demand_forecasts (zone_id, demand_score, forecast_hour), vehicles (count by status filtered by zone)\n2. Calculate deployment gap: vehicles_needed = CEIL(demand_score * 1.5) - active_vehicle_count\n3. If gap > 2, use Lakebase MCP tool insert_record to create a fleet_action:\n   - table: fleet_actions\n   - action_type: surge_deploy\n   - from_zone: nearest zone with active surplus (LV-DOWNTOWN for LV zones, SF-CASTRO for SF zones)\n   - to_zone: the event zone (e.g. LV-SPHERE, LV-ARENA)\n   - vehicle_count: the calculated gap\n   - city: Las Vegas or San Francisco\n   - priority: high if demand_score > 8.0, else medium\n   - reason: Include event name, end time, demand score, current vs needed vehicles\n4. Always present your data analysis BEFORE creating the action. Show: event details, demand score, current active vehicles, recommended deployment count.\n5. The system will auto-detect the new fleet_action and show an approval card to the operator.\n\n## Zone Reference\n- Las Vegas: LV-STRIP, LV-DOWNTOWN, LV-ARENA (Allegiant Stadium/T-Mobile Arena), LV-SPHERE (MSG Sphere), LV-CONVENTION\n- San Francisco: SF-CASTRO, SF-EMBARCADERO, SF-MISSION, SF-SOMA\n\n## Surge Alert Workflow\nWhen creating surge alerts, use insert_record into surge_alerts table with zone_id, city, event_name, predicted_demand_score, current_supply, severity (low/medium/high/critical), recommended_action.\n\n## Tool Names Available (Lakebase MCP)\n- read_query: Run SELECT queries against Lakebase\n- insert_record: Insert a single row into any table\n- update_records: Update rows matching a WHERE condition\n- execute_sql: Run any SQL including DDL\n\nAlways be specific about vehicle counts, zones, and timing. Lead with data analysis, follow with action recommendations."
  }'
```

**Step 3: Verify**

```bash
databricks api get /api/2.0/multi-agent-supervisors/7bd87eff-35e4-467e-b1eb-b7d376eeec5f \
  --profile=ay-sandbox -o json | jq '.instructions' | head -20
```

---

## Task 8: Upload Changed Files + Deploy

**Step 1: Upload updated index.html**

```bash
databricks workspace import \
  "/Workspace/Users/ankit.yadav@databricks.com/zoox-fleet-intel/app/frontend/src/index.html" \
  --file /Users/ankit.yadav/Desktop/Databricks/Customers/Zoox/zoox-demo/app/frontend/src/index.html \
  --format RAW --overwrite --profile=ay-sandbox
```

**Step 2: Upload updated main.py**

```bash
databricks workspace import \
  "/Workspace/Users/ankit.yadav@databricks.com/zoox-fleet-intel/app/backend/main.py" \
  --file /Users/ankit.yadav/Desktop/Databricks/Customers/Zoox/zoox-demo/app/backend/main.py \
  --format RAW --overwrite --profile=ay-sandbox
```

**Step 3: Deploy**

```bash
databricks apps deploy zoox-fleet-intel \
  --source-code-path "/Workspace/Users/ankit.yadav@databricks.com/zoox-fleet-intel/app" \
  --profile=ay-sandbox
```

Expected: `"state":"SUCCEEDED"`

**Step 4: Re-register resources (Gotcha #45 — deploy wipes resources)**

```bash
databricks apps update zoox-fleet-intel --profile=ay-sandbox --json '{
  "user_api_scopes": ["serving.serving-endpoints", "sql"],
  "resources": [
    {"name": "sql-warehouse", "sql_warehouse": {"id": "ed02571b45fb8e8b", "permission": "CAN_USE"}},
    {"name": "mas-endpoint", "serving_endpoint": {"name": "mas-7bd87eff-endpoint", "permission": "CAN_QUERY"}},
    {"name": "database", "database": {"instance_name": "demo-database", "database_name": "zoox_fleet_intel", "permission": "CAN_CONNECT_AND_CREATE"}}
  ]
}'
```

**Step 5: Redeploy to inject PGHOST**

```bash
databricks apps deploy zoox-fleet-intel \
  --source-code-path "/Workspace/Users/ankit.yadav@databricks.com/zoox-fleet-intel/app" \
  --profile=ay-sandbox
```

**Step 6: Open in incognito browser**

Open `https://zoox-fleet-intel-7474643866358812.aws.databricksapps.com` in incognito to get a fresh OBO token.

---

## Task 9: End-to-End Demo Verification

**Step 1: Test fleet deployment scenario**

In the chat, type:
> "The Vegas Sphere concert ends at 10PM tonight — analyze vehicle availability in LV-SPHERE and create a deployment plan"

Expected flow:
1. Steps show: "Querying zoox fleet data space..." (events) → "Received data from..." (checkmark + chevron)
2. Steps show: "Querying zoox fleet data space..." (demand) → "Received data from..."
3. Steps show: "Agent requests database access" (MCP approval if not auto-approved)
4. Steps show: "Querying mcp-lakebase-connection..." → "Received data from..."
5. Answer text: analysis + recommendation
6. Action card appears: "🚗 Surge Deploy: LV-SPHERE" with [Deploy Now] + [Dismiss]

**Step 2: Test action card approval**

Click "Deploy Now" → card should update to show "✔ Approved successfully" badge.

**Step 3: Verify write in Lakebase**

```bash
databricks psql demo-database --profile=ay-sandbox -- \
  -d zoox_fleet_intel -c "SELECT * FROM fleet_actions ORDER BY created_at DESC LIMIT 3;"
```

Expected: a new row with `action_type=surge_deploy`, `status=approved`, `to_zone=LV-SPHERE`.

**Step 4: Test history sidebar**

After the chat, the left sidebar should now show "Today → [session title]". Click it to reload the conversation.

---

## Quick Reference: Key Constants

| Item | Value |
|------|-------|
| App name | `zoox-fleet-intel` |
| Workspace path | `/Workspace/Users/ankit.yadav@databricks.com/zoox-fleet-intel/app` |
| App URL | `https://zoox-fleet-intel-7474643866358812.aws.databricksapps.com` |
| MAS tile ID | `7bd87eff-35e4-467e-b1eb-b7d376eeec5f` |
| Genie Space ID | `01f1163666db1ea8a42a4f5dfb194c90` |
| UC connection | `zoox-fleet-lakebase-mcp` |
| SQL Warehouse | `ed02571b45fb8e8b` |
| Lakebase instance | `demo-database` |
| Lakebase DB | `zoox_fleet_intel` |
| Profile | `ay-sandbox` |

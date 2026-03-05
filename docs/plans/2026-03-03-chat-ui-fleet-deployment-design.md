# Chat UI Overhaul + Fleet Deployment Demo — Design Doc
Date: 2026-03-03

## Scope
Five improvements to the Zoox Fleet Intelligence demo chat UI and end-to-end MAS demo scenario.

---

## 1. History Sidebar Fix

**Problem:** Sidebar shows "No conversations yet" despite backend saving sessions to Lakebase `chat_sessions` table.

**Root cause:** `loadChat()` likely doesn't call `loadChatSessions()`, or the rendering is broken.

**Fix:**
- Call `GET /api/chat/sessions` on page load and on new message completion
- Render each session as a clickable row: first 50 chars of title + relative timestamp ("2m ago", "1h ago")
- Active session highlighted with accent border-left
- Clicking a session calls `POST /api/chat/sessions/{id}/switch`, clears `#chat-messages-inner`, re-renders history messages

---

## 2. Example Questions (Genie + Lakebase)

Replace 5 generic questions with 6 multi-agent demo questions in a 2x3 grid:

1. "The Sphere concert ends at 10PM — how many more vehicles does LV-SPHERE need?" → Genie + Lakebase write + action card
2. "Raiders game at Allegiant Stadium tonight — forecast the surge and deploy vehicles" → Genie + Lakebase write + action card
3. "Which Las Vegas zones are critically understaffed right now?" → Genie analytics only
4. "Move surplus vehicles from low-demand SF zones to high-demand ones" → Genie + Lakebase write
5. "Show open surge alerts and recommend which to resolve first" → Genie + Lakebase
6. "What's the demand forecast for SF-EMBARCADERO for the next 4 hours?" → Genie analytics only

---

## 3. User Messages on Right

**Change:** Add `user-msg-block` class to user message blocks.

**CSS:**
```css
.chat-msg-row.user { flex-direction: row-reverse; }
.user-avatar { background: var(--primary-light); }
.user-msg-bubble { background: var(--accent-subtle); border-radius: 14px 14px 4px 14px; }
```

**JS:** `createUserMsgBlock()` adds `user-msg-row` to the row div and `user-msg-bubble` to the body div.

---

## 4. Expandable/Collapsible Tool Calls

**Default state:** All steps collapsed (compact label + dot only).

**Interaction:** Click any step → chevron rotates, expanded panel slides down showing full sub-agent response (formatMd rendered).

**Implementation:**
- `addStep()` adds a `step-expandable` class and stores full response in `data-content` attribute
- `toggleStep(el)` function handles expand/collapse with CSS height animation
- Each `sub_result` event stores `evt.text` in the step's `data-content`
- Steps never auto-expand; user controls visibility

**CSS:** Slide animation via `max-height` transition (0 → auto via JS measurement).

---

## 5. Fleet Deployment End-to-End Demo

### Trigger Prompt
> "The Vegas Sphere concert ends at 10PM tonight — analyze vehicle availability in LV-SPHERE and recommend a deployment plan"

### Agent Flow
1. **Genie** → `SELECT * FROM zoox_fleet_intel.events WHERE venue LIKE '%Sphere%'` → finds concert ending 22:00
2. **Genie** → `SELECT * FROM zoox_fleet_intel.demand_forecasts WHERE zone_id = 'LV-SPHERE' ORDER BY forecast_hour` → gets score 9.0+
3. **Genie** → `SELECT status, COUNT(*) FROM zoox_fleet_intel.vehicles WHERE current_zone = 'LV-SPHERE' GROUP BY status` → 4 active, 2 charging, 1 maintenance
4. **Lakebase MCP** → `insert_record` into `fleet_actions`: type=`surge_deploy`, from=`LV-DOWNTOWN`, to=`LV-SPHERE`, count=5, priority=`high`, reason=*"Sphere concert ends 22:00 — demand 9.2/10, only 4 active vehicles in zone, need 9 to meet demand"*
5. Backend detects new `fleet_action` row → emits `action_card` SSE
6. UI renders: **"🚗 Surge Deploy: LV-SPHERE"** card with from/to/count/priority/reason
7. User clicks **[Deploy Now]** → `PATCH /api/fleet/fleet-actions/{id}` `{"status": "approved"}` → card resolves

### Backend Changes
- Add `PATCH /api/fleet/fleet-actions/{id}` endpoint accepting `{"status": "approved"|"dismissed"|"executed"}`
- Verify `fleet_actions` is in `ACTION_CARD_TABLES` (already is)
- Verify `handleActionCard('fleet_action', id, 'approve')` in JS calls the right PATCH endpoint

### Additional Demo Scenarios (as example questions)
- **Raiders surge**: LV-ARENA zone, Raiders game, deploy vehicles from LV-STRIP surplus
- **SF rebalancing**: SF-CASTRO surplus → SF-EMBARCADERO high demand
- **Low battery emergency**: vehicles < 15% battery in active zones → `charge_dispatch` action

### MAS Supervisor Instructions Update (PATCH via API)
Add to existing instructions:
```
Fleet Deployment Workflow:
1. When asked about vehicle availability at events, first query Genie for: events table (event name, venue, end_time), demand_forecasts (zone_id, demand_score, forecast_hour), vehicles (count by status and zone).
2. Calculate deployment gap: vehicles_needed = ceil(demand_score * 1.5) - active_in_zone
3. If gap > 0, use Lakebase MCP tool 'insert_record' to create a fleet_action:
   - table: fleet_actions
   - action_type: 'surge_deploy'
   - from_zone: nearest surplus zone
   - to_zone: event zone
   - vehicle_count: calculated gap
   - city: 'Las Vegas' or 'San Francisco'
   - priority: 'high' if demand_score > 8.0, else 'medium'
   - reason: Include event name, end time, demand score, current vs needed vehicles
4. The system will auto-detect the new record and show an action card for operator approval.
5. Always present the data analysis (event, demand, current supply) BEFORE creating the action card.

Available zones in Las Vegas: LV-STRIP, LV-DOWNTOWN, LV-ARENA, LV-SPHERE, LV-CONVENTION
Available zones in San Francisco: SF-CASTRO, SF-EMBARCADERO, SF-MISSION, SF-SOMA
```

---

## Data Verification Needed

Before demo, verify in Delta Lake:
- `events` table has a Sphere concert with `end_time` around 22:00 or a future timestamp
- `demand_forecasts` has LV-SPHERE with `demand_score > 8.5` in forecast hours near event end
- `vehicles` shows a mix of statuses in LV-SPHERE (some active, some charging) so the "shortage" narrative holds

If data doesn't match, update `notebooks/02_generate_data.py` to ensure the narrative data exists.

---

## Files to Modify

| File | Changes |
|------|---------|
| `app/frontend/src/index.html` | History sidebar render, user msg alignment, expandable steps, example questions |
| `app/backend/main.py` | Add `PATCH /api/fleet/fleet-actions/{id}`, verify handleActionCard JS |
| MAS supervisor (via API) | PATCH instructions with fleet deployment workflow |
| `notebooks/02_generate_data.py` | Verify/fix Sphere event data and demand forecast |

# Databricks notebook source
# Zoox Fleet Intelligence — Seed Lakebase with operational data
# Run AFTER 02_generate_data.py and after creating the Lakebase instance/schema.
#
# APPROACH A (recommended): Upgrade SDK, use generate_database_credential()
# APPROACH B (fallback): Seed via local CLI:
#   databricks psql <instance> --profile=<profile> -- -d <database> -f /tmp/seed.sql

# COMMAND ----------

# MAGIC %pip install --upgrade databricks-sdk psycopg2-binary

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import psycopg2
import json
import random
from datetime import datetime, timedelta
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

cred = w.database.generate_database_credential(instance_names=["TODO-INSTANCE-NAME"])
token = cred.token

# COMMAND ----------

# Connection parameters — update for your Lakebase instance
PG_HOST = "TODO"
PG_PORT = 5432
PG_DATABASE = "TODO"
PG_USER = ""
PG_SSLMODE = "require"

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DATABASE,
    user=PG_USER,
    password=token,
    sslmode=PG_SSLMODE,
)
conn.autocommit = True
cur = conn.cursor()
print("Connected to Lakebase")

# COMMAND ----------

# Apply schemas
# TODO: Update paths to match your workspace location
def _run_sql_file(sql_text, label="SQL"):
    lines = [line for line in sql_text.splitlines() if not line.strip().startswith("--")]
    cleaned = "\n".join(lines)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                cur.execute(stmt)
            except Exception as e:
                print(f"  ({label} skipped: {str(e)[:80]})")

try:
    schema_sql = open("/Workspace/Users/YOUR_EMAIL/zoox-demo/lakebase/core_schema.sql").read()
    _run_sql_file(schema_sql, "core_schema")
    print("Core schema applied")
except FileNotFoundError:
    print("core_schema.sql not found — apply manually or update path")

try:
    domain_sql = open("/Workspace/Users/YOUR_EMAIL/zoox-demo/lakebase/domain_schema.sql").read()
    _run_sql_file(domain_sql, "domain_schema")
    print("Domain schema applied")
except FileNotFoundError:
    print("domain_schema.sql not found — apply manually or update path")

# COMMAND ----------

# Deterministic seeding
random.seed(42)

ZONES_LV = ["LV-STRIP", "LV-DOWNTOWN", "LV-ARENA", "LV-SPHERE", "LV-CONVENTION"]
ZONES_SF = ["SF-SOMA", "SF-MISSION", "SF-EMBARCADERO", "SF-CASTRO"]
ALL_ZONES = ZONES_LV + ZONES_SF
VEHICLES_LV = [f"ZX-{i:03d}" for i in range(1, 31)]
VEHICLES_SF = [f"ZX-{i:03d}" for i in range(31, 51)]

now = datetime.utcnow()

# COMMAND ----------

# Seed fleet_actions (~30 rows)
fleet_action_data = [
    ("rebalance", "LV-DOWNTOWN", "LV-SPHERE", 4, "Las Vegas", "Sphere show ending 10pm - pre-position for demand surge", "high", "executed"),
    ("rebalance", "LV-CONVENTION", "LV-STRIP", 3, "Las Vegas", "Convention ended - redirect to Strip nightlife demand", "medium", "executed"),
    ("surge_deploy", "LV-ARENA", "LV-SPHERE", 5, "Las Vegas", "VGK game overlapping with Sphere show - maximum surge expected", "critical", "executed"),
    ("rebalance", "LV-STRIP", "LV-ARENA", 2, "Las Vegas", "Knights game starting in 2 hours - stage vehicles near T-Mobile Arena", "medium", "executed"),
    ("charge_dispatch", "LV-SPHERE", "LV-DOWNTOWN", 3, "Las Vegas", "Low battery vehicles recalled to downtown charging hub", "low", "executed"),
    ("rebalance", "SF-CASTRO", "SF-SOMA", 2, "San Francisco", "Morning commute demand shift to SoMa district", "medium", "executed"),
    ("surge_deploy", "SF-MISSION", "SF-EMBARCADERO", 3, "San Francisco", "Warriors game at Chase Center - deploy to Embarcadero", "high", "executed"),
    ("rebalance", "SF-EMBARCADERO", "SF-MISSION", 2, "San Francisco", "Evening demand shifting to Mission district restaurants", "low", "executed"),
    ("maintenance_pull", "LV-STRIP", "LV-DOWNTOWN", 1, "Las Vegas", "ZX-012 sensor calibration overdue - pull to maintenance bay", "medium", "executed"),
    ("recall", "LV-SPHERE", "LV-CONVENTION", 2, "Las Vegas", "Post-show excess vehicles - redistribute to convention area", "low", "executed"),
    ("rebalance", "LV-DOWNTOWN", "LV-ARENA", 3, "Las Vegas", "UFC fight night at T-Mobile Arena - pre-position vehicles", "high", "executed"),
    ("surge_deploy", "SF-SOMA", "SF-EMBARCADERO", 4, "San Francisco", "Tech conference ending at Moscone - surge to Embarcadero transit", "high", "executed"),
    ("charge_dispatch", "SF-MISSION", "SF-CASTRO", 2, "San Francisco", "Battery levels critical in Mission fleet - rotate to charging", "medium", "executed"),
    ("rebalance", "LV-STRIP", "LV-SPHERE", 3, "Las Vegas", "Sphere matinee show - afternoon pre-positioning", "medium", "executed"),
    ("rebalance", "LV-ARENA", "LV-DOWNTOWN", 2, "Las Vegas", "Post-game redistribution to downtown hotels", "low", "executed"),
    ("rebalance", "LV-CONVENTION", "LV-ARENA", 2, "Las Vegas", "Concert at T-Mobile Arena tonight", "medium", "approved"),
    ("surge_deploy", "LV-DOWNTOWN", "LV-SPHERE", 4, "Las Vegas", "Double Sphere show tonight - deploy maximum vehicles", "critical", "approved"),
    ("rebalance", "SF-EMBARCADERO", "SF-SOMA", 2, "San Francisco", "Dreamforce attendees arriving at Moscone", "medium", "approved"),
    ("charge_dispatch", "LV-STRIP", "LV-CONVENTION", 2, "Las Vegas", "Overnight charging rotation", "low", "approved"),
    ("rebalance", "SF-CASTRO", "SF-EMBARCADERO", 1, "San Francisco", "Chase Center event - need additional vehicles", "medium", "approved"),
    ("surge_deploy", "LV-STRIP", "LV-SPHERE", 5, "Las Vegas", "U2 residency final show - maximum demand expected", "critical", "pending"),
    ("rebalance", "LV-ARENA", "LV-STRIP", 3, "Las Vegas", "Late night Strip demand after arena events", "high", "pending"),
    ("rebalance", "SF-SOMA", "SF-MISSION", 2, "San Francisco", "Weekend dinner rush in Mission", "medium", "pending"),
    ("surge_deploy", "LV-DOWNTOWN", "LV-ARENA", 3, "Las Vegas", "Boxing match at T-Mobile Arena", "high", "pending"),
    ("maintenance_pull", "SF-EMBARCADERO", "SF-SOMA", 1, "San Francisco", "ZX-045 tire pressure warning", "medium", "pending"),
    ("rebalance", "LV-SPHERE", "LV-STRIP", 2, "Las Vegas", "Cancelled show - redistribute to Strip", "low", "dismissed"),
    ("surge_deploy", "SF-MISSION", "SF-CASTRO", 1, "San Francisco", "False alarm - parade cancelled", "low", "dismissed"),
    ("rebalance", "LV-DOWNTOWN", "LV-CONVENTION", 3, "Las Vegas", "Convention postponed to next week", "medium", "dismissed"),
    ("charge_dispatch", "LV-ARENA", "LV-DOWNTOWN", 2, "Las Vegas", "System error - vehicles already charged", "low", "failed"),
    ("rebalance", "SF-SOMA", "SF-EMBARCADERO", 3, "San Francisco", "Network timeout during execution", "high", "failed"),
]

for i, (atype, fz, tz, vc, city, reason, prio, status) in enumerate(fleet_action_data):
    executed_at = None
    if status in ("executed", "dismissed"):
        executed_at = now - timedelta(hours=random.randint(1, 720))
    cur.execute(
        "INSERT INTO fleet_actions (action_type, from_zone, to_zone, vehicle_count, city, reason, priority, status, executed_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (atype, fz, tz, vc, city, reason, prio, status, executed_at),
    )
print(f"Seeded fleet_actions: {len(fleet_action_data)} rows")

# COMMAND ----------

# Seed surge_alerts (~20 rows)
surge_alert_data = [
    ("LV-SPHERE", "Las Vegas", "Sphere: U2 Residency", 0.92, 4, "critical", "open", "Deploy 6 vehicles from LV-DOWNTOWN and LV-CONVENTION to LV-SPHERE"),
    ("LV-ARENA", "Las Vegas", "VGK vs Edmonton Oilers", 0.85, 5, "high", "open", "Deploy 4 vehicles from LV-STRIP to LV-ARENA"),
    ("LV-SPHERE", "Las Vegas", "Sphere: Postcard from Earth", 0.88, 3, "critical", "open", "Deploy 5 vehicles from adjacent zones to LV-SPHERE"),
    ("SF-EMBARCADERO", "San Francisco", "Warriors vs Lakers", 0.78, 4, "high", "open", "Deploy 3 vehicles from SF-CASTRO and SF-MISSION"),
    ("LV-CONVENTION", "Las Vegas", "CES 2026 Opening Day", 0.72, 6, "high", "open", "Stage 4 additional vehicles at LV-CONVENTION"),
    ("LV-STRIP", "Las Vegas", "New Year's Eve", 0.95, 8, "critical", "open", "Maximum deployment - all available vehicles to LV-STRIP"),
    ("SF-SOMA", "San Francisco", "Dreamforce 2025", 0.68, 5, "medium", "acknowledged", "Deploy 2 vehicles from SF-CASTRO"),
    ("LV-ARENA", "Las Vegas", "UFC 310 Main Event", 0.82, 6, "high", "acknowledged", "Deploy 3 vehicles from LV-DOWNTOWN"),
    ("LV-SPHERE", "Las Vegas", "Sphere: Dead & Company", 0.90, 4, "critical", "acknowledged", "Deploy 5 vehicles from LV-STRIP and LV-DOWNTOWN"),
    ("SF-EMBARCADERO", "San Francisco", "Chase Center Concert", 0.65, 5, "medium", "acknowledged", "Deploy 2 vehicles from SF-MISSION"),
    ("LV-SPHERE", "Las Vegas", "Sphere: Eagles Residency", 0.87, 5, "high", "resolved", "Deployed 4 vehicles - demand met successfully"),
    ("LV-ARENA", "Las Vegas", "VGK vs Calgary Flames", 0.75, 7, "medium", "resolved", "Pre-positioned 3 vehicles - wait times within target"),
    ("SF-SOMA", "San Francisco", "Google I/O Overflow", 0.62, 6, "medium", "resolved", "Deployed 2 vehicles - resolved within 30 min"),
    ("LV-CONVENTION", "Las Vegas", "SEMA Show", 0.70, 4, "medium", "resolved", "Convention shuttle demand handled by existing fleet"),
    ("LV-STRIP", "Las Vegas", "Friday Night Rush", 0.80, 10, "high", "resolved", "Deployed 5 vehicles from LV-CONVENTION - wait times normalized"),
    ("SF-MISSION", "San Francisco", "Dia de los Muertos Festival", 0.58, 4, "medium", "resolved", "Demand lower than predicted - no action needed"),
    ("LV-DOWNTOWN", "Las Vegas", "Fremont Street Event", 0.55, 7, "low", "resolved", "Adequate supply - monitored only"),
    ("SF-CASTRO", "San Francisco", "Pride Week Pre-Events", 0.60, 3, "medium", "resolved", "Deployed 1 vehicle from SF-SOMA"),
    ("LV-ARENA", "Las Vegas", "Cancelled Concert", 0.45, 8, "low", "dismissed", "Event cancelled - alert dismissed"),
    ("SF-SOMA", "San Francisco", "False Positive Detection", 0.42, 7, "low", "dismissed", "Sensor anomaly - no actual demand spike"),
]

for zone, city, event, score, supply, sev, status, rec in surge_alert_data:
    resolved_at = None
    if status in ("resolved", "dismissed"):
        resolved_at = now - timedelta(hours=random.randint(1, 480))
    cur.execute(
        "INSERT INTO surge_alerts (zone_id, city, event_name, predicted_demand_score, current_supply, severity, status, recommended_action, resolved_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (zone, city, event, score, supply, sev, status, rec, resolved_at),
    )
print(f"Seeded surge_alerts: {len(surge_alert_data)} rows")

# COMMAND ----------

# Seed dispatch_overrides (~15 rows)
override_data = [
    ("ZX-005", "LV-STRIP", "LV-SPHERE", "Las Vegas", "VIP customer pickup request at Sphere entrance", "fleet_manager"),
    ("ZX-012", "LV-ARENA", "LV-DOWNTOWN", "Las Vegas", "Maintenance facility closest to downtown", "maintenance_tech"),
    ("ZX-003", "LV-DOWNTOWN", "LV-STRIP", "Las Vegas", "High-priority airport transfer request", "dispatch_lead"),
    ("ZX-018", "LV-CONVENTION", "LV-ARENA", "Las Vegas", "Arena VIP pre-positioning for celebrity event", "fleet_manager"),
    ("ZX-022", "LV-SPHERE", "LV-CONVENTION", "Las Vegas", "Convention center executive shuttle", "dispatch_lead"),
    ("ZX-035", "SF-SOMA", "SF-EMBARCADERO", "San Francisco", "Chase Center corporate event pickup", "fleet_manager"),
    ("ZX-041", "SF-MISSION", "SF-SOMA", "San Francisco", "Moscone tech demo - showcase vehicle", "fleet_manager"),
    ("ZX-038", "SF-EMBARCADERO", "SF-CASTRO", "San Francisco", "Medical appointment transport request", "dispatch_lead"),
    ("ZX-033", "SF-CASTRO", "SF-SOMA", "San Francisco", "Morning corporate shuttle commitment", "operator"),
    ("ZX-008", "LV-STRIP", "LV-ARENA", "Las Vegas", "Pre-game VIP transport", "operator"),
    ("ZX-015", "LV-DOWNTOWN", "LV-SPHERE", "Las Vegas", "Sphere show - wheelchair accessible vehicle needed", "dispatch_lead"),
    ("ZX-025", "LV-ARENA", "LV-STRIP", "Las Vegas", "Post-game hotel drop-off priority", "operator"),
    ("ZX-042", "SF-SOMA", "SF-MISSION", "San Francisco", "Restaurant reservation pickup commitment", "operator"),
    ("ZX-010", "LV-STRIP", "LV-CONVENTION", "Las Vegas", "Override cancelled - vehicle reassigned", "fleet_manager"),
    ("ZX-047", "SF-EMBARCADERO", "SF-CASTRO", "San Francisco", "Route cancelled - passenger no-show", "operator"),
]

statuses_override = (["executed"] * 10) + (["pending"] * 3) + (["cancelled"] * 2)
random.shuffle(statuses_override)

for i, (vid, fz, tz, city, reason, by) in enumerate(override_data):
    status = statuses_override[i] if i < len(statuses_override) else "executed"
    cur.execute(
        "INSERT INTO dispatch_overrides (vehicle_id, from_zone, to_zone, city, reason, override_by, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (vid, fz, tz, city, reason, by, status),
    )
print(f"Seeded dispatch_overrides: {len(override_data)} rows")

# COMMAND ----------

# Seed workflows (~40 rows)
workflow_data = []

# Rebalancing requests (15)
rebalance_summaries = [
    ("LV-SPHERE", "zone", "LV-SPHERE", "Detected demand surge at LV-SPHERE. Sphere show ending at 10pm, predicted 2.8x demand multiplier. Current supply: 4 vehicles, recommended: 10. Initiating rebalance from LV-DOWNTOWN and LV-CONVENTION."),
    ("LV-ARENA", "zone", "LV-ARENA", "VGK game night - T-Mobile Arena expects 18,000 attendees. Current zone supply: 5 vehicles, recommended: 8. Pulling vehicles from LV-STRIP and LV-CONVENTION."),
    ("LV-STRIP", "zone", "LV-STRIP", "Weekend nightlife demand spike on the Strip. Historical pattern shows 3.2x base demand after 10pm. Need 12 vehicles, currently have 8."),
    ("SF-EMBARCADERO", "zone", "SF-EMBARCADERO", "Warriors home game at Chase Center. Predicted 2.5x demand for Embarcadero zone. Rebalancing 3 vehicles from SF-CASTRO."),
    ("SF-SOMA", "zone", "SF-SOMA", "Moscone Center tech conference. 15,000 attendees expected. Morning arrival surge predicted. Deploy 4 vehicles from SF-MISSION."),
    ("LV-CONVENTION", "zone", "LV-CONVENTION", "CES 2026 day 2. Convention center demand remains elevated. Maintaining enhanced vehicle staging."),
    ("LV-SPHERE", "zone", "LV-SPHERE", "Double Sphere show today. Matinee at 2pm, evening at 8pm. Maximum demand expected between shows and after evening show."),
    ("SF-MISSION", "zone", "SF-MISSION", "Friday evening dinner rush. Mission district restaurants generating 1.8x base demand. Rebalancing from SF-SOMA post-conference."),
    ("LV-DOWNTOWN", "zone", "LV-DOWNTOWN", "Downtown Fremont Street Experience event. Moderate demand increase expected. Moving 2 vehicles from LV-CONVENTION."),
    ("SF-EMBARCADERO", "zone", "SF-EMBARCADERO", "Ferry building farmers market Saturday. Predicted 1.5x morning demand. Pre-positioning 2 vehicles."),
    ("LV-STRIP", "zone", "LV-STRIP", "New Year's Eve preparation. Maximum fleet deployment to LV-STRIP starting 6pm. All non-essential zones reduced to minimum."),
    ("LV-ARENA", "zone", "LV-ARENA", "UFC fight night. T-Mobile Arena sold out at 20,000. High-value ride demand expected post-event."),
    ("SF-SOMA", "zone", "SF-SOMA", "Dreamforce closing ceremony. 30,000 attendees departing Moscone. Maximum SOMA deployment."),
    ("LV-SPHERE", "zone", "LV-SPHERE", "U2 final residency show. Record ticket prices suggest high-value riders. Premium positioning requested."),
    ("SF-CASTRO", "zone", "SF-CASTRO", "Castro neighborhood festival. Moderate demand increase. Routing 1 vehicle from SF-SOMA."),
]
for zone, etype, eid, summary in rebalance_summaries:
    chain = json.dumps([
        {"step": 1, "tool": "monitor", "label": "Demand spike detected", "output": zone + " demand elevated", "status": "completed"},
        {"step": 2, "tool": "analyze", "label": "Supply-demand analysis", "output": summary[:80], "status": "completed"},
        {"step": 3, "tool": "action", "label": "Rebalance initiated", "output": "Fleet action created", "status": "completed"},
    ])
    workflow_data.append(("rebalancing_request", random.choice(["monitor", "monitor", "chat"]),
        random.choice(["medium", "high", "high", "critical"]), summary, etype, eid, chain))

# Surge responses (15)
surge_summaries = [
    ("LV-SPHERE", "zone", "LV-SPHERE", "Sphere show U2 Residency creating 3.2x demand surge. Deploying 6 additional vehicles from LV-DOWNTOWN (3) and LV-CONVENTION (3). ETA: 15 minutes."),
    ("LV-ARENA", "zone", "LV-ARENA", "VGK playoff game. 20,000 capacity sold out. Post-game surge expected at 10:30pm. Pre-deploying 5 vehicles."),
    ("SF-EMBARCADERO", "zone", "SF-EMBARCADERO", "Chase Center Warriors game. 18,000 attendees. Deploying 4 vehicles from SF-CASTRO and SF-MISSION for post-game demand."),
    ("LV-STRIP", "zone", "LV-STRIP", "NYE countdown surge. All available vehicles routing to LV-STRIP. 15 vehicles deployed from all other zones."),
    ("SF-SOMA", "zone", "SF-SOMA", "Dreamforce keynote ending. 25,000 departing Moscone simultaneously. Maximum SOMA deployment with overflow to SF-EMBARCADERO."),
    ("LV-CONVENTION", "zone", "LV-CONVENTION", "CES opening day. 50,000 registered attendees. Convention center zone at maximum capacity. Overflow staging at LV-DOWNTOWN."),
    ("LV-SPHERE", "zone", "LV-SPHERE", "Dead & Company Sphere residency. 18,000 capacity. Deploying 5 vehicles pre-show and 8 vehicles post-show."),
    ("LV-ARENA", "zone", "LV-ARENA", "Boxing championship at T-Mobile Arena. Premium ride demand expected. VIP pre-positioning 3 vehicles."),
    ("SF-EMBARCADERO", "zone", "SF-EMBARCADERO", "Giants game at Oracle Park overflow. Embarcadero demand 2.1x. Deploying 2 vehicles from SF-CASTRO."),
    ("LV-STRIP", "zone", "LV-STRIP", "Saturday night Strip surge. Historical pattern: 2.5x demand 10pm-2am. Deploying 8 vehicles from LV-CONVENTION and LV-DOWNTOWN."),
    ("SF-SOMA", "zone", "SF-SOMA", "Google I/O conference at Moscone. Day 2 keynote ending at 5pm. Preparing for departure surge."),
    ("LV-SPHERE", "zone", "LV-SPHERE", "Eagles Sphere residency. Concert ending at 11pm. Deploying 6 vehicles for post-show surge."),
    ("LV-ARENA", "zone", "LV-ARENA", "UFC main event. T-Mobile Arena. Late-night ride demand expected through 1am. Staging 4 vehicles."),
    ("SF-MISSION", "zone", "SF-MISSION", "Dia de los Muertos celebration. Mission district. Moderate demand increase 6pm-midnight."),
    ("LV-DOWNTOWN", "zone", "LV-DOWNTOWN", "Fremont Street holiday event. Downtown surge expected. Moving 3 vehicles from LV-CONVENTION."),
]
for zone, etype, eid, summary in surge_summaries:
    chain = json.dumps([
        {"step": 1, "tool": "monitor", "label": "Surge detected", "output": zone + " demand spike", "status": "completed"},
        {"step": 2, "tool": "analyze", "label": "Event correlation", "output": "Event-driven demand confirmed", "status": "completed"},
        {"step": 3, "tool": "action", "label": "Vehicles deployed", "output": "Surge response executed", "status": "completed"},
    ])
    workflow_data.append(("surge_response", random.choice(["monitor", "monitor", "manual"]),
        random.choice(["high", "high", "critical", "medium"]), summary, etype, eid, chain))

# Dispatch overrides (10)
override_summaries = [
    ("ZX-005", "vehicle", "ZX-005", "Manual override: VIP pickup at Sphere main entrance. ZX-005 rerouted from LV-STRIP to LV-SPHERE. Priority: immediate."),
    ("ZX-012", "vehicle", "ZX-012", "Maintenance override: ZX-012 pulled from service for sensor recalibration. Routed to downtown maintenance bay."),
    ("ZX-035", "vehicle", "ZX-035", "Corporate event override: ZX-035 assigned to Chase Center VIP pickup. Removed from general dispatch pool."),
    ("ZX-018", "vehicle", "ZX-018", "Celebrity transport: ZX-018 assigned to arena VIP entrance. Security protocol engaged."),
    ("ZX-041", "vehicle", "ZX-041", "Demo vehicle: ZX-041 assigned to Moscone Center for technology showcase. Removed from ride pool."),
    ("ZX-003", "vehicle", "ZX-003", "Airport priority: ZX-003 redirected for high-priority airport transfer from LV-DOWNTOWN."),
    ("ZX-038", "vehicle", "ZX-038", "Medical transport: ZX-038 assigned for medical appointment transport in SF-CASTRO. Accessibility mode enabled."),
    ("ZX-022", "vehicle", "ZX-022", "Executive shuttle: ZX-022 assigned to convention center executive transport loop."),
    ("ZX-015", "vehicle", "ZX-015", "Accessibility override: ZX-015 assigned for wheelchair-accessible Sphere pickup."),
    ("ZX-047", "vehicle", "ZX-047", "Route override cancelled: ZX-047 passenger no-show at SF-EMBARCADERO. Returning to general pool."),
]
for vid, etype, eid, summary in override_summaries:
    chain = json.dumps([
        {"step": 1, "tool": "monitor", "label": "Override requested", "output": vid + " override", "status": "completed"},
        {"step": 2, "tool": "action", "label": "Vehicle reassigned", "output": "Dispatch updated", "status": "completed"},
    ])
    workflow_data.append(("dispatch_override", random.choice(["manual", "chat"]),
        random.choice(["medium", "medium", "high", "low"]), summary, etype, eid, chain))

# Assign statuses
wf_statuses = (["pending_approval"] * 8 + ["in_progress"] * 5 + ["approved"] * 20 + ["dismissed"] * 5 + ["failed"] * 2)
random.shuffle(wf_statuses)

for i, (wtype, trigger, sev, summary, etype, eid, chain) in enumerate(workflow_data):
    status = wf_statuses[i] if i < len(wf_statuses) else "approved"
    completed_at = None
    if status in ("approved", "dismissed", "failed"):
        completed_at = now - timedelta(hours=random.randint(1, 720))
    headline_map = {
        "rebalancing_request": "Fleet Rebalancing: " + eid,
        "surge_response": "Surge Response: " + eid,
        "dispatch_override": "Dispatch Override: " + eid,
    }
    headline = headline_map.get(wtype, wtype.replace("_", " ").title())
    cur.execute(
        "INSERT INTO workflows (workflow_type, trigger_source, severity, summary, entity_type, entity_id, "
        "status, reasoning_chain, completed_at, headline, enriched_summary) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (wtype, trigger, sev, summary, etype, eid, status, chain, completed_at, headline, summary),
    )
print(f"Seeded workflows: {len(workflow_data)} rows")

# COMMAND ----------

# Seed agent_actions (~50 rows)
action_data = [
    ("demand_forecast", "high", "zone", "LV-SPHERE", "Generated 24h demand forecast for LV-SPHERE: peak demand score 0.92 at 10pm (Sphere show ending)", "Forecast published to demand_forecasts table"),
    ("demand_forecast", "medium", "zone", "LV-ARENA", "Generated 24h demand forecast for LV-ARENA: peak demand score 0.78 at 10:30pm (VGK game)", "Forecast published"),
    ("demand_forecast", "medium", "zone", "SF-EMBARCADERO", "Generated 24h demand forecast for SF-EMBARCADERO: peak demand score 0.72 at 10pm (Chase Center event)", "Forecast published"),
    ("rebalance_trigger", "high", "zone", "LV-SPHERE", "Triggered rebalance: LV-SPHERE supply deficit detected. 4 vehicles available, 10 recommended.", "Created fleet_action #1: rebalance from LV-DOWNTOWN"),
    ("rebalance_trigger", "medium", "zone", "LV-STRIP", "Triggered rebalance: LV-STRIP weekend demand pattern detected. Pre-positioning 5 vehicles.", "Created fleet_action #2: rebalance from LV-CONVENTION"),
    ("rebalance_trigger", "high", "zone", "SF-EMBARCADERO", "Triggered rebalance: Warriors game demand surge imminent. Deploying 3 vehicles to SF-EMBARCADERO.", "Created fleet_action #7"),
    ("surge_detection", "critical", "zone", "LV-SPHERE", "SURGE DETECTED: Sphere show demand 3.2x base. Current wait time 18 min, target 8 min.", "Created surge_alert: critical severity"),
    ("surge_detection", "high", "zone", "LV-ARENA", "Surge detected: VGK post-game demand 2.5x base at LV-ARENA. 12,000 fans departing.", "Created surge_alert: high severity"),
    ("surge_detection", "medium", "zone", "SF-SOMA", "Moderate surge detected: Moscone conference ending. 1.8x demand in SF-SOMA.", "Created surge_alert: medium severity"),
    ("surge_detection", "critical", "zone", "LV-STRIP", "NYE surge detected: LV-STRIP demand 4.0x base. All vehicles deploying.", "Created surge_alert: critical severity"),
    ("battery_alert", "medium", "vehicle", "ZX-008", "ZX-008 battery at 22%. Scheduling charge rotation. Current zone: LV-STRIP.", "Dispatched to charging hub"),
    ("battery_alert", "medium", "vehicle", "ZX-015", "ZX-015 battery at 18%. Urgent charge needed. Removing from ride pool.", "Dispatched to LV-DOWNTOWN charging hub"),
    ("battery_alert", "low", "vehicle", "ZX-033", "ZX-033 battery at 25%. Scheduling next available charge slot in SF-SOMA.", "Queued for charging"),
    ("battery_alert", "medium", "vehicle", "ZX-042", "ZX-042 battery at 20%. Rerouting to SF-MISSION charging station.", "Dispatched to charging"),
    ("zone_optimization", "medium", "zone", "LV-STRIP", "Zone optimization: LV-STRIP has 12 vehicles, optimal is 10 at current demand. Redistributing 2.", "Redistribution initiated"),
    ("zone_optimization", "low", "zone", "SF-CASTRO", "Zone optimization: SF-CASTRO over-supplied. 5 vehicles present, 3 optimal. Moving 2 to SF-SOMA.", "Redistribution initiated"),
    ("zone_optimization", "medium", "zone", "LV-DOWNTOWN", "Zone optimization: LV-DOWNTOWN under-supplied for morning shift. Requesting 2 vehicles from LV-STRIP.", "Request created"),
    ("demand_forecast", "medium", "zone", "LV-CONVENTION", "Generated weekly forecast for LV-CONVENTION: CES 2026 expected to drive 2.5x demand all week.", "Published weekly forecast"),
    ("demand_forecast", "low", "zone", "SF-CASTRO", "Generated 24h forecast for SF-CASTRO: normal demand expected, no events.", "Forecast published"),
    ("demand_forecast", "high", "zone", "LV-STRIP", "Generated 24h forecast for LV-STRIP: NYE demand predicted at 4.0x base. Maximum deployment recommended.", "Published critical forecast"),
    ("rebalance_trigger", "critical", "zone", "LV-SPHERE", "Emergency rebalance: Sphere show sold out, current supply 3 vehicles, need 10. Wait time 22 min.", "Created priority fleet_action"),
    ("surge_detection", "high", "zone", "LV-CONVENTION", "Surge detected: CES 2026 registration overflow. LV-CONVENTION demand 2.2x base.", "Created surge_alert"),
    ("battery_alert", "high", "vehicle", "ZX-023", "ZX-023 battery critical at 12%. Emergency pull from LV-ARENA ride pool.", "Emergency dispatch to charging"),
    ("zone_optimization", "low", "zone", "SF-EMBARCADERO", "Zone optimization: SF-EMBARCADERO balanced at 7 vehicles. No action needed.", "Monitoring continued"),
    ("demand_forecast", "medium", "zone", "SF-EMBARCADERO", "Generated 48h forecast for SF-EMBARCADERO: Warriors double-header weekend. Elevated demand Sat-Sun.", "Published multi-day forecast"),
    ("rebalance_trigger", "medium", "zone", "SF-SOMA", "Pre-emptive rebalance: Dreamforce Day 1 starting. Moving 3 vehicles to SF-SOMA from SF-CASTRO.", "Created fleet_action"),
    ("surge_detection", "medium", "zone", "SF-MISSION", "Moderate surge: Friday dinner rush in Mission district. 1.5x demand detected.", "Monitoring - no action needed"),
    ("battery_alert", "low", "vehicle", "ZX-048", "ZX-048 battery at 28%. Next charge slot available in 45 minutes.", "Scheduled charging"),
    ("zone_optimization", "high", "zone", "LV-SPHERE", "Post-show zone optimization: LV-SPHERE has 10 vehicles, demand dropping. Redistributing 5 vehicles.", "Redistribution fleet_action created"),
    ("demand_forecast", "high", "zone", "LV-ARENA", "Emergency forecast update: UFC main card extended. LV-ARENA demand window extended to 1:30am.", "Updated forecast"),
    ("rebalance_trigger", "medium", "zone", "LV-CONVENTION", "Convention day 3 rebalance: Reduced attendance expected. Pulling 2 vehicles to LV-STRIP.", "Created fleet_action"),
    ("surge_detection", "high", "zone", "SF-EMBARCADERO", "Concert surge at Chase Center. 17,000 attendees. Post-concert demand at 11pm.", "Created surge_alert"),
    ("battery_alert", "medium", "vehicle", "ZX-019", "ZX-019 battery degradation detected. Charge efficiency 82%. Scheduling diagnostics.", "Maintenance ticket created"),
    ("zone_optimization", "medium", "zone", "LV-ARENA", "Pre-game zone prep: Moving vehicles to optimal positions around T-Mobile Arena perimeter.", "3 vehicles repositioned"),
    ("demand_forecast", "low", "zone", "LV-DOWNTOWN", "Quiet Tuesday forecast for LV-DOWNTOWN. Base demand only. No events.", "Published routine forecast"),
    ("rebalance_trigger", "high", "zone", "LV-STRIP", "Friday night Strip rebalance. Historical 2.8x pattern confirmed by real-time data.", "Created fleet_action for 5 vehicles"),
    ("surge_detection", "medium", "zone", "LV-DOWNTOWN", "Fremont Street Experience event surge. 1.6x demand detected in LV-DOWNTOWN.", "Monitoring - threshold not met for alert"),
    ("battery_alert", "low", "vehicle", "ZX-036", "ZX-036 scheduled maintenance charging complete. Battery at 95%. Returning to SF-SOMA pool.", "Vehicle returned to service"),
    ("zone_optimization", "medium", "zone", "SF-SOMA", "Morning commute optimization: SF-SOMA demand rising. Routing 2 idle vehicles from SF-CASTRO.", "Redistribution complete"),
    ("demand_forecast", "medium", "zone", "SF-SOMA", "Generated commute forecast: SF-SOMA peak demand 8-9am, secondary peak 5-6pm.", "Published commute forecast"),
    ("rebalance_trigger", "low", "zone", "SF-CASTRO", "Light demand in SF-CASTRO. Reducing to minimum 2 vehicles. Excess to SF-MISSION.", "Created fleet_action"),
    ("surge_detection", "critical", "zone", "LV-SPHERE", "Double show surge: Sphere matinee ending + evening show arriving simultaneously. Maximum alert.", "Created critical surge_alert"),
    ("battery_alert", "medium", "vehicle", "ZX-027", "ZX-027 showing unusual power consumption. 15% higher than fleet average. Monitoring.", "Added to watchlist"),
    ("zone_optimization", "low", "zone", "LV-CONVENTION", "Convention center quiet period. Reducing to 3 vehicles. Excess to LV-STRIP for nightlife.", "Redistribution initiated"),
    ("demand_forecast", "high", "zone", "LV-SPHERE", "Sphere double-show forecast: Peak demand 0.95 at 11pm. Highest forecast this month.", "Published critical forecast"),
    ("rebalance_trigger", "medium", "zone", "SF-EMBARCADERO", "Weekend harbor cruise traffic. Embarcadero demand 1.4x. Minor rebalance from SF-CASTRO.", "Created fleet_action"),
    ("surge_detection", "low", "zone", "SF-CASTRO", "Minor demand increase in SF-CASTRO. Below alert threshold. Continued monitoring.", "No action taken"),
    ("battery_alert", "high", "vehicle", "ZX-011", "ZX-011 rapid battery drain. 40% to 15% in 2 hours. Possible hardware issue. Emergency pull.", "Emergency maintenance dispatch"),
    ("zone_optimization", "medium", "zone", "LV-STRIP", "Late night optimization: Redistributing post-midnight vehicles. 8 vehicles to staging, 4 to charging.", "12 vehicle moves initiated"),
    ("demand_forecast", "medium", "zone", "LV-ARENA", "Next week forecast: 3 VGK home games + 1 concert. Elevated demand Mon/Wed/Sat.", "Published weekly forecast"),
]

aa_statuses = (["executed"] * 30 + ["pending"] * 10 + ["dismissed"] * 5 + ["failed"] * 5)
random.shuffle(aa_statuses)

for i, (atype, sev, etype, eid, desc, action) in enumerate(action_data):
    status = aa_statuses[i] if i < len(aa_statuses) else "executed"
    created = now - timedelta(hours=random.randint(0, 168))
    cur.execute(
        "INSERT INTO agent_actions (action_type, severity, entity_type, entity_id, description, action_taken, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (atype, sev, etype, eid, desc, action, status, created),
    )
print(f"Seeded agent_actions: {len(action_data)} rows")

# COMMAND ----------

# Seed notes (~30 rows)
notes_data = [
    ("vehicle", "ZX-015", "ZX-015 showing intermittent sensor readings in rain conditions. Scheduled for diagnostic.", "maintenance_tech"),
    ("vehicle", "ZX-008", "ZX-008 battery degradation tracking: 92% health, down from 95% last month. Within normal range.", "maintenance_tech"),
    ("vehicle", "ZX-003", "ZX-003 consistently highest-rated vehicle in passenger surveys. Consider for VIP assignments.", "fleet_manager"),
    ("vehicle", "ZX-023", "ZX-023 had emergency battery pull on 2/15. Root cause: software bug in charge management. Patched.", "maintenance_tech"),
    ("vehicle", "ZX-041", "ZX-041 designated as demo vehicle for Moscone Center tech showcases. Keep in pristine condition.", "fleet_manager"),
    ("vehicle", "ZX-012", "ZX-012 sensor recalibration completed. All systems nominal. Returned to active duty.", "maintenance_tech"),
    ("vehicle", "ZX-035", "ZX-035 assigned to corporate events rotation for Chase Center. Premium interior cleaning weekly.", "fleet_manager"),
    ("vehicle", "ZX-019", "ZX-019 charging efficiency at 82%. Below fleet average of 91%. Hardware inspection scheduled.", "ai_agent"),
    ("vehicle", "ZX-027", "ZX-027 power consumption anomaly detected. 15% above fleet average. Under observation for 48h.", "ai_agent"),
    ("vehicle", "ZX-011", "ZX-011 emergency maintenance: rapid battery drain identified as faulty thermal management module. Replaced.", "maintenance_tech"),
    ("zone", "LV-SPHERE", "LV-SPHERE zone: Consider permanent staging area for post-show demand. Current ad-hoc staging causes 5-min delays.", "fleet_manager"),
    ("zone", "LV-STRIP", "LV-STRIP Friday/Saturday pattern: demand consistently 2.5-3x base after 10pm. Pre-positioning by 9:30pm recommended.", "ai_agent"),
    ("zone", "LV-ARENA", "LV-ARENA: T-Mobile Arena events highly predictable from schedule. Auto-deployment working well.", "operator"),
    ("zone", "LV-CONVENTION", "LV-CONVENTION: CES week requires special planning. Convention goers prefer pickup at LVCC loop road, not main entrance.", "operator"),
    ("zone", "SF-SOMA", "SF-SOMA: Moscone Center events cause parking congestion. Recommend pickup zone on Howard St, not 4th St.", "operator"),
    ("zone", "SF-EMBARCADERO", "SF-EMBARCADERO: Chase Center post-game traffic blocks Terry Francois Blvd. Use alternative pickup on 3rd St.", "operator"),
    ("zone", "LV-DOWNTOWN", "LV-DOWNTOWN charging hub utilization at 78%. Consider adding 2 charging slots for peak demand periods.", "fleet_manager"),
    ("zone", "SF-MISSION", "SF-MISSION: Weekend dinner rush 7-9pm. Valencia St restaurants generate consistent demand. Auto-detection working.", "ai_agent"),
    ("zone", "SF-CASTRO", "SF-CASTRO: Lowest demand zone in SF. Consider reducing minimum vehicle allocation from 4 to 3.", "ai_agent"),
    ("event", "VGK-2025", "VGK games: Average post-game demand multiplier 2.3x. Deploy vehicles 30 min before game end for optimal positioning.", "ai_agent"),
    ("event", "SPHERE-2025", "Sphere shows: Demand varies by artist. U2/Eagles: 3.5x, Postcard from Earth: 2.0x, Dead & Company: 3.0x.", "fleet_manager"),
    ("event", "CES-2026", "CES 2026: Week-long elevated demand. Day 1 highest (50K attendees), tapering to Day 4 (25K). Plan daily rebalancing.", "fleet_manager"),
    ("event", "NYE-2025", "NYE 2025: Record demand expected on Strip. All vehicles deployed. Consider temporary additional capacity.", "fleet_manager"),
    ("event", "WARRIORS-2025", "Warriors home games: Chase Center capacity 18,064. Post-game surge lasts 45 min. Pre-position by 4th quarter.", "operator"),
    ("event", "DREAMFORCE-2025", "Dreamforce: 3-day event at Moscone. Keynote days (Day 1, 3) have 2x demand of regular sessions (Day 2).", "ai_agent"),
    ("event", "UFC-2025", "UFC events at T-Mobile Arena: Fights run late (past midnight). Need vehicles staged until 1:30am minimum.", "operator"),
    ("vehicle", "ZX-050", "ZX-050 newest vehicle in fleet. Commissioned 2026-01-15. All systems nominal. Assigned to SF-EMBARCADERO.", "fleet_manager"),
    ("vehicle", "ZX-001", "ZX-001 fleet veteran. Commissioned 2025-08-10. 12,000+ rides completed. Highest mileage in fleet.", "fleet_manager"),
    ("zone", "LV-SPHERE", "LV-SPHERE staging optimization result: Moving staging from parking lot B to valet loop reduced avg wait by 3.2 min.", "ai_agent"),
    ("zone", "LV-STRIP", "LV-STRIP: Wynn/Encore corridor generates 22% of Strip zone demand. Consider micro-zone staging.", "ai_agent"),
]

for etype, eid, text, author in notes_data:
    cur.execute(
        "INSERT INTO notes (entity_type, entity_id, note_text, author) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (etype, eid, text, author),
    )
print(f"Seeded notes: {len(notes_data)} rows")

# COMMAND ----------

# Verify seeded data
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
for row in cur.fetchall():
    cur.execute(f"SELECT COUNT(*) FROM {row[0]}")
    count = cur.fetchone()[0]
    print(f"  {row[0]}: {count} rows")

# COMMAND ----------

cur.close()
conn.close()
print("Done — Lakebase seeded successfully")

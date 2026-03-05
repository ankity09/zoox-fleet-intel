"""
Reseed Zoox Fleet Intel Delta Lake tables via Statement Execution API.
Uses the same hash-based deterministic logic as the notebook but executes
via SQL Warehouse (no Spark cluster needed).
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

PROFILE = "ay-sandbox"
WAREHOUSE_ID = "ed02571b45fb8e8b"
FQ = "main.zoox_fleet_intel"

TODAY = date.today()
SIX_MONTHS_AGO = TODAY - timedelta(days=180)

# ── Hash helpers (same as notebook) ──────────────────────────────────────
def _hash_float(seed, lo, hi):
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return lo + (h / 0xFFFFFFFF) * (hi - lo)

def _hash_int(seed, lo, hi):
    return int(_hash_float(seed, lo, hi + 0.999))

def _hash_choice(seed, options):
    return options[_hash_int(seed, 0, len(options) - 1)]

def _hash_weighted(seed, options, weights):
    h = _hash_float(seed, 0.0, 1.0)
    cumulative = 0.0
    total = sum(weights)
    for i, w in enumerate(weights):
        cumulative += w / total
        if h <= cumulative:
            return options[i]
    return options[-1]

def _hash_date(seed, start, end):
    days_range = (end - start).days
    offset = _hash_int(seed, 0, max(0, days_range))
    return start + timedelta(days=offset)

# ── SQL execution helper ────────────────────────────────────────────────
def run_sql(sql, wait=True):
    """Execute SQL via Statement Execution API."""
    payload = {
        "warehouse_id": WAREHOUSE_ID,
        "statement": sql,
        "wait_timeout": "50s" if wait else "0s",
    }
    cmd = [
        "databricks", "api", "post", "/api/2.0/sql/statements",
        "--profile", PROFILE, "--json", json.dumps(payload)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:300]}")
        return None
    try:
        d = json.loads(result.stdout)
        status = d.get("status", {}).get("state", "UNKNOWN")
        if status == "FAILED":
            err = d.get("status", {}).get("error", {}).get("message", "unknown")
            print(f"  SQL FAILED: {err[:200]}")
            return None
        return d
    except json.JSONDecodeError:
        print(f"  JSON parse error: {result.stdout[:200]}")
        return None

def esc(s):
    """Escape single quotes in SQL strings."""
    return str(s).replace("'", "''")

# ── Constants ────────────────────────────────────────────────────────────
ZONES = [
    {"zone_id": "LV-STRIP",      "zone_name": "Las Vegas Strip",             "city": "Las Vegas",     "base_demand": 45, "capacity": 12, "lat": 36.1147, "lon": -115.1728},
    {"zone_id": "LV-DOWNTOWN",   "zone_name": "Downtown Las Vegas",          "city": "Las Vegas",     "base_demand": 25, "capacity": 8,  "lat": 36.1699, "lon": -115.1398},
    {"zone_id": "LV-ARENA",      "zone_name": "T-Mobile Arena District",     "city": "Las Vegas",     "base_demand": 30, "capacity": 10, "lat": 36.1590, "lon": -115.1485},
    {"zone_id": "LV-SPHERE",     "zone_name": "Sphere District",             "city": "Las Vegas",     "base_demand": 35, "capacity": 10, "lat": 36.1582, "lon": -115.1520},
    {"zone_id": "LV-CONVENTION", "zone_name": "Convention Center District",  "city": "Las Vegas",     "base_demand": 20, "capacity": 6,  "lat": 36.1290, "lon": -115.1530},
    {"zone_id": "SF-SOMA",       "zone_name": "SoMa",                        "city": "San Francisco", "base_demand": 40, "capacity": 8,  "lat": 37.7749, "lon": -122.3994},
    {"zone_id": "SF-MISSION",    "zone_name": "Mission District",            "city": "San Francisco", "base_demand": 30, "capacity": 6,  "lat": 37.7599, "lon": -122.4148},
    {"zone_id": "SF-EMBARCADERO","zone_name": "Embarcadero",                 "city": "San Francisco", "base_demand": 35, "capacity": 7,  "lat": 37.7936, "lon": -122.3930},
    {"zone_id": "SF-CASTRO",     "zone_name": "Castro",                      "city": "San Francisco", "base_demand": 20, "capacity": 4,  "lat": 37.7609, "lon": -122.4350},
]

LV_ZONE_IDS = [z["zone_id"] for z in ZONES if z["city"] == "Las Vegas"]
SF_ZONE_IDS = [z["zone_id"] for z in ZONES if z["city"] == "San Francisco"]

VEHICLES = []
for i in range(1, 51):
    vid = "ZX-" + str(i).zfill(3)
    city = "Las Vegas" if i <= 30 else "San Francisco"
    zone_options = LV_ZONE_IDS if city == "Las Vegas" else SF_ZONE_IDS
    home_zone = _hash_choice("home-zone-" + vid, zone_options)
    VEHICLES.append({"vehicle_id": vid, "model": "Zoox Robotaxi", "city": city, "home_zone": home_zone})

EVENT_VENUES = [
    {"venue": "The Sphere",                    "city": "Las Vegas",     "zone": "LV-SPHERE",     "types": ["concert", "experience", "special_event"],  "cap_lo": 8000,  "cap_hi": 18000, "epw": 3.5},
    {"venue": "T-Mobile Arena",                "city": "Las Vegas",     "zone": "LV-ARENA",      "types": ["hockey", "concert", "boxing", "ufc"],      "cap_lo": 12000, "cap_hi": 20000, "epw": 2.0},
    {"venue": "Las Vegas Convention Center",   "city": "Las Vegas",     "zone": "LV-CONVENTION", "types": ["convention", "trade_show", "expo"],        "cap_lo": 5000,  "cap_hi": 50000, "epw": 0.5},
    {"venue": "Moscone Center",                "city": "San Francisco", "zone": "SF-SOMA",       "types": ["tech_conference", "convention"],            "cap_lo": 3000,  "cap_hi": 30000, "epw": 0.25},
    {"venue": "Chase Center",                  "city": "San Francisco", "zone": "SF-EMBARCADERO","types": ["basketball", "concert"],                    "cap_lo": 15000, "cap_hi": 18000, "epw": 2.0},
]

EVENT_NAMES = {
    "The Sphere": ["Sphere Experience: U2 Residency", "Sphere: Dead & Company", "Sphere: Phish Las Vegas", "Sphere Experience: Anyma", "Sphere: Immersive Light Show", "Sphere Experience: Coldplay"],
    "T-Mobile Arena": ["VGK vs Oilers", "VGK vs Avalanche", "VGK vs Kings", "VGK vs Sharks", "UFC Fight Night", "Canelo vs Benavidez", "Morgan Wallen Live", "UFC 310: Main Card"],
    "Las Vegas Convention Center": ["CES 2026", "SEMA Show", "NAB Show 2026", "MAGIC Las Vegas", "World of Concrete", "AWS re:Invent"],
    "Moscone Center": ["Dreamforce 2025", "Google Cloud Next", "RSA Conference", "GDC 2026", "Databricks Data+AI Summit"],
    "Chase Center": ["Warriors vs Lakers", "Warriors vs Celtics", "Warriors vs Nuggets", "Warriors vs Suns", "Billie Eilish Tour", "SZA: Lana Tour"],
}

EVENT_START_HOURS = {
    "concert": [19, 20], "experience": [14, 17, 19], "special_event": [18, 19, 20],
    "hockey": [17, 19], "boxing": [18, 20], "ufc": [18, 20],
    "convention": [9, 10], "trade_show": [9, 10], "expo": [9, 10],
    "tech_conference": [9, 10], "basketball": [17, 19],
}
EVENT_DURATIONS = {
    "concert": 3, "experience": 2, "special_event": 3, "hockey": 3, "boxing": 4, "ufc": 4,
    "convention": 8, "trade_show": 8, "expo": 8, "tech_conference": 8, "basketball": 3,
}

STATUS_OPTIONS = ["active", "active", "active", "idle", "charging", "maintenance", "en_route"]
STATUS_WEIGHTS = [3, 3, 3, 2, 2, 1, 1]
PAID_RIDES_START = date(2025, 12, 1)

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 1: zones
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("Reseeding Zoox Fleet Intel tables in", FQ)
print("=" * 60)

print("\n1/5 Creating zones table (9 rows)...")
values = []
for z in ZONES:
    values.append(f"('{z['zone_id']}', '{esc(z['zone_name'])}', '{z['city']}', {z['base_demand']}, {z['capacity']}, {z['lat']}, {z['lon']})")
sql = f"""CREATE OR REPLACE TABLE {FQ}.zones AS
SELECT * FROM VALUES {', '.join(values)}
AS t(zone_id STRING, zone_name STRING, city STRING, base_demand_per_hour INT, vehicle_capacity INT, latitude DOUBLE, longitude DOUBLE)"""
run_sql(sql)
print("  Done: 9 rows")

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 2: vehicles
# ═══════════════════════════════════════════════════════════════════════════
print("\n2/5 Creating vehicles table (50 rows)...")
values = []
for v in VEHICLES:
    vid = v["vehicle_id"]
    zone_options = LV_ZONE_IDS if v["city"] == "Las Vegas" else SF_ZONE_IDS
    current_zone = _hash_choice("cur-zone-" + vid, zone_options)
    status = _hash_weighted("status-" + vid, STATUS_OPTIONS, STATUS_WEIGHTS)
    battery = _hash_int("battery-" + vid, 20, 100)
    rides_today = _hash_int("rides-today-" + vid, 0, 25)
    commissioned = _hash_date("commission-" + vid, SIX_MONTHS_AGO, TODAY - timedelta(days=30))
    hours_ago = _hash_int("last-ride-hrs-" + vid, 0, 8)
    minutes_ago = _hash_int("last-ride-min-" + vid, 0, 59)
    last_ride_dt = datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0) - timedelta(hours=hours_ago, minutes=minutes_ago)
    last_ride_str = last_ride_dt.strftime("%Y-%m-%d %H:%M:%S")
    values.append(f"('{vid}', '{v['model']}', '{v['city']}', '{current_zone}', '{status}', {battery}, {rides_today}, '{last_ride_str}', DATE'{commissioned.isoformat()}')")

sql = f"""CREATE OR REPLACE TABLE {FQ}.vehicles AS
SELECT * FROM VALUES {', '.join(values)}
AS t(vehicle_id STRING, model STRING, city STRING, current_zone STRING, status STRING, battery_pct INT, rides_today INT, last_ride_at STRING, commissioned_date DATE)"""
run_sql(sql)
print("  Done: 50 rows")

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 3: events
# ═══════════════════════════════════════════════════════════════════════════
print("\n3/5 Creating events table...")
events_rows = []
event_counter = 0
for venue_info in EVENT_VENUES:
    venue = venue_info["venue"]
    city = venue_info["city"]
    zone = venue_info["zone"]
    types = venue_info["types"]
    cap_lo, cap_hi = venue_info["cap_lo"], venue_info["cap_hi"]
    names_list = EVENT_NAMES[venue]
    total_events = int((180 / 7.0) * venue_info["epw"])
    for i in range(total_events):
        event_counter += 1
        eid = "EVT-" + str(event_counter).zfill(4)
        seed = venue + "-" + str(i)
        ev_date = _hash_date("evt-date-" + seed, SIX_MONTHS_AGO, TODAY + timedelta(days=14))
        ev_type = _hash_choice("evt-type-" + seed, types)
        ev_name = _hash_choice("evt-name-" + seed, names_list)
        attendance = _hash_int("evt-att-" + seed, cap_lo, cap_hi)
        start_hour = _hash_choice("evt-hour-" + seed, EVENT_START_HOURS.get(ev_type, [19]))
        start_min = _hash_choice("evt-min-" + seed, [0, 0, 0, 30])
        duration = EVENT_DURATIONS.get(ev_type, 3)
        end_hour = min(start_hour + duration, 23)
        start_t = f"{start_hour:02d}:{start_min:02d}"
        end_t = f"{end_hour:02d}:{start_min:02d}"
        demand_mult = round(max(1.5, min(4.0, attendance / 10000.0)), 2)
        events_rows.append((eid, venue, ev_name, ev_type, city, zone, attendance, ev_date, start_t, end_t, demand_mult))

values = []
for e in events_rows:
    values.append(f"('{e[0]}', '{esc(e[1])}', '{esc(e[2])}', '{e[3]}', '{e[4]}', '{e[5]}', {e[6]}, DATE'{e[7].isoformat()}', '{e[8]}', '{e[9]}', {e[10]})")

sql = f"""CREATE OR REPLACE TABLE {FQ}.events AS
SELECT * FROM VALUES {', '.join(values)}
AS t(event_id STRING, venue STRING, event_name STRING, event_type STRING, city STRING, zone STRING, expected_attendance INT, event_date DATE, start_time STRING, end_time STRING, demand_multiplier DOUBLE)"""
run_sql(sql)
print(f"  Done: {len(events_rows)} rows")

# Build event date lookup for rides
event_dates_by_city = {}
for e in events_rows:
    key = str(e[7]) + "|" + e[4]
    event_dates_by_city[key] = max(event_dates_by_city.get(key, 0.0), e[10])

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 4: rides (batch INSERT)
# ═══════════════════════════════════════════════════════════════════════════
print("\n4/5 Creating rides table (this takes a minute)...")

# Create empty table first
run_sql(f"""CREATE OR REPLACE TABLE {FQ}.rides (
  ride_id STRING, vehicle_id STRING, city STRING,
  pickup_zone STRING, dropoff_zone STRING,
  request_time STRING, pickup_time STRING, dropoff_time STRING,
  wait_time_min DOUBLE, distance_miles DOUBLE, fare_usd DOUBLE, ride_status STRING
)""")

rides_batch = []
ride_counter = 0
current_day = TODAY - timedelta(days=30)  # Last 30 days for denser data

HOUR_WEIGHTS = [1,1,1,1,1,2,3,4,5,5,5,5,5,5,6,7,8,9,10,10,9,7,4,2]

while current_day <= TODAY:
    day_str = current_day.isoformat()
    is_weekend = current_day.weekday() >= 5
    base_lv = 180 if is_weekend else 150
    base_sf = 130 if is_weekend else 100

    lv_mult = event_dates_by_city.get(day_str + "|Las Vegas", 1.0)
    sf_mult = event_dates_by_city.get(day_str + "|San Francisco", 1.0)
    rides_lv = min(int(base_lv * max(lv_mult, 1.0) * _hash_float("day-var-lv-" + day_str, 0.85, 1.15)), 500)
    rides_sf = min(int(base_sf * max(sf_mult, 1.0) * _hash_float("day-var-sf-" + day_str, 0.85, 1.15)), 350)

    lv_veh = [v["vehicle_id"] for v in VEHICLES if v["city"] == "Las Vegas"]
    sf_veh = [v["vehicle_id"] for v in VEHICLES if v["city"] == "San Francisco"]
    is_paid = current_day >= PAID_RIDES_START

    for city_rides, city, zones, vehs, has_ev in [
        (rides_lv, "Las Vegas", LV_ZONE_IDS, lv_veh, lv_mult > 1.0),
        (rides_sf, "San Francisco", SF_ZONE_IDS, sf_veh, sf_mult > 1.0),
    ]:
        for r in range(city_rides):
            ride_counter += 1
            rid = f"RD-{ride_counter:07d}"
            sb = rid + "-" + day_str
            vid = _hash_choice("ride-veh-" + sb, vehs)
            pz = _hash_choice("ride-pu-" + sb, zones)
            dz = _hash_choice("ride-do-" + sb, zones)
            hour = _hash_weighted("ride-hr-" + sb, list(range(24)), HOUR_WEIGHTS)
            minute = _hash_int("ride-min-" + sb, 0, 59)
            second = _hash_int("ride-sec-" + sb, 0, 59)
            req_time = f"{day_str} {hour:02d}:{minute:02d}:{second:02d}"
            wait = round(_hash_float("ride-wait-" + sb, 5.0, 20.0) if has_ev else _hash_float("ride-wait-" + sb, 2.0, 12.0), 1)
            pu_dt = datetime(current_day.year, current_day.month, current_day.day, hour, minute, second) + timedelta(minutes=wait)
            dist = round(_hash_float("ride-dist-" + sb, 1.0, 15.0), 1)
            trip_min = dist * _hash_float("ride-speed-" + sb, 2.5, 5.0)
            do_dt = pu_dt + timedelta(minutes=trip_min)
            fare = round(_hash_float("ride-fare-" + sb, 2.0, 15.0), 2) if is_paid else 0.0
            if current_day == TODAY and hour >= 10:
                st = _hash_weighted("ride-st-" + sb, ["completed", "in_progress", "cancelled"], [70, 20, 10])
            else:
                st = _hash_weighted("ride-st-" + sb, ["completed", "cancelled"], [95, 5])

            rides_batch.append(
                f"('{rid}','{vid}','{city}','{pz}','{dz}',"
                f"'{req_time}','{pu_dt.strftime('%Y-%m-%d %H:%M:%S')}','{do_dt.strftime('%Y-%m-%d %H:%M:%S')}',"
                f"{wait},{dist},{fare},'{st}')"
            )

    # Flush batch every ~2000 rows
    if len(rides_batch) >= 2000:
        sql = f"INSERT INTO {FQ}.rides VALUES {','.join(rides_batch)}"
        run_sql(sql)
        print(f"  Inserted {ride_counter} rides so far...")
        rides_batch = []

    current_day += timedelta(days=1)

# Flush remaining
if rides_batch:
    sql = f"INSERT INTO {FQ}.rides VALUES {','.join(rides_batch)}"
    run_sql(sql)

print(f"  Done: {ride_counter} rides total")

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 5: demand_forecasts
# ═══════════════════════════════════════════════════════════════════════════
print("\n5/5 Creating demand_forecasts table...")

fc_event_lookup = {}
for e in events_rows:
    key = str(e[7]) + "|" + e[5]  # date|zone
    fc_event_lookup[key] = max(fc_event_lookup.get(key, 0.0), e[10])

fc_batch = []
fc_counter = 0
HOUR_CURVE = [0.2,0.15,0.1,0.1,0.15,0.3,0.5,0.7,0.8,0.85,0.8,0.75,0.7,0.75,0.8,0.85,0.9,1.0,1.0,0.95,0.85,0.7,0.5,0.3]

# Historical (past 14 days, every 3h) + Future (next 7 days, every hour)
for day_offset in range(-14, 8):
    fc_day = TODAY + timedelta(days=day_offset)
    day_str = fc_day.isoformat()
    hours = range(0, 24, 3) if day_offset < 0 else range(24)

    for z in ZONES:
        zid, city, base, cap = z["zone_id"], z["city"], z["base_demand"], z["capacity"]
        ev_mult = fc_event_lookup.get(day_str + "|" + zid, 1.0)

        for hour in hours:
            fc_counter += 1
            fid = f"FC-{fc_counter:06d}"
            sb = f"{fid}-{day_str}-{zid}-{hour}"
            hw = HOUR_CURVE[hour]
            predicted = max(1, int(base * hw * max(ev_mult, 1.0) * _hash_float("fc-demand-" + sb, 0.8, 1.2)))
            supply = max(1, int(cap * _hash_float("fc-supply-" + sb, 0.5, 1.0)))
            demand_score = round(min(1.0, predicted / (base * 1.5)), 2)
            if ev_mult > 1.0:
                demand_score = round(min(1.0, demand_score * 1.3), 2)
            base_conf = max(0.7, 0.95 - max(0, day_offset) * 0.02)
            confidence = round(_hash_float("fc-conf-" + sb, max(0.70, base_conf - 0.10), min(0.98, base_conf + 0.03)), 2)

            fc_batch.append(
                f"('{fid}','{zid}','{city}',DATE'{day_str}',{hour},{predicted},{supply},{demand_score},{confidence},'v2.3')"
            )

sql = f"""CREATE OR REPLACE TABLE {FQ}.demand_forecasts AS
SELECT * FROM VALUES {','.join(fc_batch)}
AS t(forecast_id STRING, zone_id STRING, city STRING, forecast_date DATE, hour INT, predicted_demand INT, predicted_supply INT, demand_score DOUBLE, confidence DOUBLE, model_version STRING)"""
run_sql(sql)
print(f"  Done: {fc_counter} rows")

# ═══════════════════════════════════════════════════════════════════════════
# VERIFY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Verification:")
for t in ["zones", "vehicles", "events", "rides", "demand_forecasts"]:
    d = run_sql(f"SELECT COUNT(*) as cnt FROM {FQ}.{t}")
    if d:
        rows = d.get("result", {}).get("data_array", [[0]])
        print(f"  {t}: {rows[0][0]} rows")
print("=" * 60)
print("Done! Refresh the app to see data.")

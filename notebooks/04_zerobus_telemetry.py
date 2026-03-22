# Databricks notebook source
# MAGIC %md
# MAGIC # ZeroBus Telemetry — Real-Time Taxi Streaming
# MAGIC Creates the `taxi_telemetry` table and generates 24h historical + live data.

# COMMAND ----------

dbutils.widgets.text("CATALOG", "serverless_simplot_v1_catalog")
dbutils.widgets.text("SCHEMA", "zoox_fleet_intel")
CATALOG = dbutils.widgets.get("CATALOG")
SCHEMA = dbutils.widgets.get("SCHEMA")
FQ = f"{CATALOG}.{SCHEMA}"
print(f"Target: {FQ}")

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.taxi_telemetry (
# MAGIC     vehicle_id        STRING    COMMENT 'Robotaxi identifier (ZX-001 to ZX-050)',
# MAGIC     timestamp         TIMESTAMP COMMENT 'UTC timestamp of the telemetry reading',
# MAGIC     latitude          DOUBLE    COMMENT 'WGS-84 latitude',
# MAGIC     longitude         DOUBLE    COMMENT 'WGS-84 longitude',
# MAGIC     heading_deg       DOUBLE    COMMENT 'Compass heading 0-360',
# MAGIC     speed_mph         DOUBLE    COMMENT 'Ground speed in mph',
# MAGIC     battery_pct       INT       COMMENT 'Battery level 0-100',
# MAGIC     battery_range_mi  DOUBLE    COMMENT 'Estimated range in miles',
# MAGIC     motor_temp_f      DOUBLE    COMMENT 'Motor temperature Fahrenheit',
# MAGIC     cabin_temp_f      DOUBLE    COMMENT 'Cabin temperature Fahrenheit',
# MAGIC     passenger_count   INT       COMMENT 'Number of passengers (0-4)',
# MAGIC     lidar_status      STRING    COMMENT 'LIDAR status: nominal or degraded',
# MAGIC     camera_status     STRING    COMMENT 'Camera status: nominal or degraded',
# MAGIC     status            STRING    COMMENT 'Vehicle status: active, en_route, charging, idle',
# MAGIC     zone              STRING    COMMENT 'Current operating zone'
# MAGIC ) USING DELTA
# MAGIC COMMENT 'Real-time robotaxi telemetry — 10-second cadence'

# COMMAND ----------

# MAGIC %sql
# MAGIC GRANT MODIFY, SELECT ON TABLE ${CATALOG}.${SCHEMA}.taxi_telemetry TO `account users`

# COMMAND ----------

# ─── Zone & Vehicle Definitions ──────────────────────────────────────────────

import hashlib
import math
import random
from datetime import datetime, timedelta
from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, IntegerType, StringType,
    DoubleType, TimestampType,
)

# 9 operating zones with center coordinates
ZONES = [
    {"zone_id": "LV-STRIP",      "city": "Las Vegas",     "lat": 36.1147, "lon": -115.1728},
    {"zone_id": "LV-DOWNTOWN",   "city": "Las Vegas",     "lat": 36.1699, "lon": -115.1398},
    {"zone_id": "LV-ARENA",      "city": "Las Vegas",     "lat": 36.1590, "lon": -115.1485},
    {"zone_id": "LV-SPHERE",     "city": "Las Vegas",     "lat": 36.1582, "lon": -115.1520},
    {"zone_id": "LV-CONVENTION", "city": "Las Vegas",     "lat": 36.1290, "lon": -115.1530},
    {"zone_id": "SF-SOMA",       "city": "San Francisco", "lat": 37.7749, "lon": -122.3994},
    {"zone_id": "SF-MISSION",    "city": "San Francisco", "lat": 37.7599, "lon": -122.4148},
    {"zone_id": "SF-EMBARCADERO","city": "San Francisco", "lat": 37.7936, "lon": -122.3930},
    {"zone_id": "SF-CASTRO",     "city": "San Francisco", "lat": 37.7609, "lon": -122.4350},
]

LV_ZONES = [z for z in ZONES if z["city"] == "Las Vegas"]
SF_ZONES = [z for z in ZONES if z["city"] == "San Francisco"]

# ─── Build 50 vehicles ──────────────────────────────────────────────────────

def _det_hash(seed: str) -> int:
    """Deterministic integer hash from a seed string."""
    return int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)

VEHICLES = []
for i in range(1, 51):
    vid = f"ZX-{i:03d}"
    city = "Las Vegas" if i <= 30 else "San Francisco"
    pool = LV_ZONES if i <= 30 else SF_ZONES
    home_zone = pool[_det_hash(vid) % len(pool)]

    # Assign scenario
    if 47 <= i <= 50:
        scenario = "low_battery"
    elif 44 <= i <= 46:
        scenario = "sensor_fault"
    elif 41 <= i <= 43:
        scenario = "high_demand"
    else:
        scenario = "normal"

    VEHICLES.append({
        "vehicle_id": vid,
        "city": city,
        "home_zone": home_zone,
        "scenario": scenario,
    })

print(f"Defined {len(VEHICLES)} vehicles")
print(f"  Las Vegas:     {sum(1 for v in VEHICLES if v['city'] == 'Las Vegas')}")
print(f"  San Francisco: {sum(1 for v in VEHICLES if v['city'] == 'San Francisco')}")
print(f"  Scenarios:     { {s: sum(1 for v in VEHICLES if v['scenario'] == s) for s in ['normal','low_battery','sensor_fault','high_demand']} }")

# COMMAND ----------

# ─── Generate 24h Historical Telemetry ───────────────────────────────────────
# 24h x 360 readings/hr (every 10s) x 50 taxis = 432,000 rows
# Inserted in 1-hour batches to avoid OOM on the driver.

TELEMETRY_SCHEMA = StructType([
    StructField("vehicle_id",       StringType(),    False),
    StructField("timestamp",        TimestampType(), False),
    StructField("latitude",         DoubleType(),    False),
    StructField("longitude",        DoubleType(),    False),
    StructField("heading_deg",      DoubleType(),    False),
    StructField("speed_mph",        DoubleType(),    False),
    StructField("battery_pct",      IntegerType(),   False),
    StructField("battery_range_mi", DoubleType(),    False),
    StructField("motor_temp_f",     DoubleType(),    False),
    StructField("cabin_temp_f",     DoubleType(),    False),
    StructField("passenger_count",  IntegerType(),   False),
    StructField("lidar_status",     StringType(),    False),
    StructField("camera_status",    StringType(),    False),
    StructField("status",           StringType(),    False),
    StructField("zone",             StringType(),    False),
])

READINGS_PER_HOUR = 360  # every 10 seconds
HOURS = 24
NOW = datetime.utcnow()
START = NOW - timedelta(hours=HOURS)

# Per-vehicle mutable state seeded deterministically
random.seed(42)
vehicle_states = {}
for v in VEHICLES:
    zone = v["home_zone"]
    init_battery = random.randint(40, 95)
    vehicle_states[v["vehicle_id"]] = {
        "lat": zone["lat"] + random.uniform(-0.005, 0.005),
        "lon": zone["lon"] + random.uniform(-0.005, 0.005),
        "heading": random.uniform(0, 360),
        "speed": random.uniform(10, 25),
        "battery_pct": init_battery,
        "motor_temp_f": random.uniform(140, 180),
        "cabin_temp_f": random.uniform(68, 74),
        "passenger_count": random.choice([0, 0, 1, 2, 1]),
        "charging": False,
        "charge_start_pct": 0,
    }

def _clamp(val, lo, hi):
    return max(lo, min(hi, val))

total_inserted = 0

for hour_offset in range(HOURS):
    batch_rows = []
    batch_start = START + timedelta(hours=hour_offset)
    progress_frac = hour_offset / HOURS  # 0.0 → 1.0 over 24h

    for tick in range(READINGS_PER_HOUR):
        ts = batch_start + timedelta(seconds=tick * 10)

        for v in VEHICLES:
            vid = v["vehicle_id"]
            s = vehicle_states[vid]
            zone = v["home_zone"]
            scenario = v["scenario"]

            # ── Battery drain / charging logic ───────────────────────────
            drain_rate = 2.0 / 360  # ~2% per hour per 10s tick
            if scenario == "low_battery":
                drain_rate = 4.0 / 360  # drain twice as fast

            if s["charging"]:
                # Charge at ~20% per hour
                s["battery_pct"] = _clamp(s["battery_pct"] + 20.0 / 360, 0, 100)
                s["speed"] = 0.0
                s["passenger_count"] = 0
                if s["battery_pct"] >= 90:
                    s["charging"] = False
            else:
                s["battery_pct"] = _clamp(s["battery_pct"] - drain_rate, 0, 100)
                if s["battery_pct"] < 10:
                    s["charging"] = True
                    s["charge_start_pct"] = s["battery_pct"]

            # ── Movement: random walk within zone ────────────────────────
            if not s["charging"]:
                # Heading random walk
                s["heading"] = (s["heading"] + random.uniform(-15, 15)) % 360
                # Speed varies
                if scenario == "high_demand":
                    s["speed"] = _clamp(s["speed"] + random.uniform(-3, 3), 15, 35)
                else:
                    s["speed"] = _clamp(s["speed"] + random.uniform(-2, 2), 5, 30)

                # Position walk (small delta per 10s tick)
                bearing_rad = math.radians(s["heading"])
                speed_deg = (s["speed"] / 3600) * 10 * (1 / 69.0)  # rough deg per 10s
                s["lat"] += math.cos(bearing_rad) * speed_deg
                s["lon"] += math.sin(bearing_rad) * speed_deg * (1 / math.cos(math.radians(zone["lat"])))

                # Rubberband back toward zone center (prevent drift too far)
                drift_lat = s["lat"] - zone["lat"]
                drift_lon = s["lon"] - zone["lon"]
                if abs(drift_lat) > 0.015:
                    s["lat"] -= drift_lat * 0.05
                if abs(drift_lon) > 0.015:
                    s["lon"] -= drift_lon * 0.05

            # ── Motor temp correlates with speed ─────────────────────────
            target_temp = 150 + s["speed"] * 1.5
            s["motor_temp_f"] = _clamp(
                s["motor_temp_f"] + (target_temp - s["motor_temp_f"]) * 0.1 + random.uniform(-1, 1),
                130, 230,
            )
            s["cabin_temp_f"] = _clamp(s["cabin_temp_f"] + random.uniform(-0.3, 0.3), 65, 78)

            # ── Passenger count (shifts occasionally) ────────────────────
            if not s["charging"] and random.random() < 0.02:
                if scenario == "high_demand":
                    s["passenger_count"] = random.choice([1, 2, 2, 3, 3, 4])
                else:
                    s["passenger_count"] = random.choice([0, 0, 1, 1, 2])

            # ── Sensor status ────────────────────────────────────────────
            lidar = "nominal"
            camera = "nominal"
            if scenario == "sensor_fault" and progress_frac > 0.4:
                # After 40% into the 24h window, sensors start degrading
                if random.random() < 0.6:
                    lidar = "degraded"
                if random.random() < 0.4:
                    camera = "degraded"

            # ── Vehicle status ───────────────────────────────────────────
            if s["charging"]:
                status = "charging"
            elif s["passenger_count"] > 0:
                status = "en_route"
            elif s["speed"] < 2:
                status = "idle"
            else:
                status = "active"

            battery_range = round(s["battery_pct"] * 3.0, 1)  # ~300mi at 100%

            batch_rows.append(Row(
                vehicle_id       = vid,
                timestamp        = ts,
                latitude         = round(s["lat"], 6),
                longitude        = round(s["lon"], 6),
                heading_deg      = round(s["heading"] % 360, 1),
                speed_mph        = round(s["speed"], 1),
                battery_pct      = int(s["battery_pct"]),
                battery_range_mi = battery_range,
                motor_temp_f     = round(s["motor_temp_f"], 1),
                cabin_temp_f     = round(s["cabin_temp_f"], 1),
                passenger_count  = s["passenger_count"],
                lidar_status     = lidar,
                camera_status    = camera,
                status           = status,
                zone             = zone["zone_id"],
            ))

    # Write hourly batch
    df = spark.createDataFrame(batch_rows, schema=TELEMETRY_SCHEMA)
    df.write.mode("append").saveAsTable(f"{FQ}.taxi_telemetry")
    total_inserted += len(batch_rows)
    print(f"  Hour {hour_offset+1:2d}/{HOURS} — {len(batch_rows):,} rows (cumulative: {total_inserted:,})")

print(f"\nDone. Total rows inserted: {total_inserted:,}")

# COMMAND ----------

# ─── Verify Row Counts ───────────────────────────────────────────────────────

count = spark.sql(f"SELECT COUNT(*) as cnt FROM {FQ}.taxi_telemetry").collect()[0]["cnt"]
print(f"taxi_telemetry rows: {count:,}")
# Show sample
display(spark.sql(f"SELECT * FROM {FQ}.taxi_telemetry ORDER BY timestamp DESC LIMIT 20"))

# COMMAND ----------

# MAGIC %pip install databricks-zerobus-ingest-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# ─── ZeroBus SDK — Live Telemetry Burst (Optional) ──────────────────────────
#
# This cell is a placeholder for initializing the ZeroBus ingest SDK and
# pushing a short 5-minute live burst of telemetry data. In production, the
# live feed is handled by the app's LiveFeedEngine via the Statement
# Execution API, not this notebook.
#
# Usage (when SDK is available):
#
#   from databricks_zerobus_ingest import ZeroBusClient
#
#   client = ZeroBusClient(
#       catalog=CATALOG,
#       schema=SCHEMA,
#       table="taxi_telemetry",
#   )
#
#   # Push 5 minutes of live readings at 10s cadence
#   for vehicle in VEHICLES:
#       client.register_vehicle(vehicle["vehicle_id"], zone=vehicle["home_zone"]["zone_id"])
#
#   client.start(duration_sec=300, cadence_sec=10)
#   client.stop()
#
# For now, the app backend handles live telemetry injection directly.
print("ZeroBus SDK placeholder — live feed is managed by the app backend.")

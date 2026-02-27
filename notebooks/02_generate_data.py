# Databricks notebook source
# Zoox Fleet Intelligence Platform — Delta Lake Data Generation
# Generates 5 Delta Lake tables: zones, vehicles, events, rides, demand_forecasts
# Hash-based deterministic generation — re-running produces identical data for a given date.

# COMMAND ----------

CATALOG = "serverless_simplot_v1_catalog"
SCHEMA = "zoox_fleet_intel"
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Using {CATALOG}.{SCHEMA}")

# COMMAND ----------

import hashlib
import math
from datetime import date, datetime, timedelta
from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, IntegerType, StringType,
    DoubleType, DateType, LongType, BooleanType,
)

# Reference date — data always looks fresh relative to today.
TODAY = date.today()
SIX_MONTHS_AGO = TODAY - timedelta(days=180)

# ─── Deterministic hash-based generation functions ────────────────────────

def _hash_float(seed, lo, hi):
    """Deterministic float in [lo, hi] from a seed string."""
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return lo + (h / 0xFFFFFFFF) * (hi - lo)


def _hash_int(seed, lo, hi):
    return int(_hash_float(seed, lo, hi + 0.999))


def _hash_choice(seed, options):
    return options[_hash_int(seed, 0, len(options) - 1)]


def _hash_weighted(seed, options, weights):
    """Weighted random choice using hash."""
    h = _hash_float(seed, 0.0, 1.0)
    cumulative = 0.0
    total = sum(weights)
    for i, w in enumerate(weights):
        cumulative += w / total
        if h <= cumulative:
            return options[i]
    return options[-1]


def _hash_date(seed, start, end):
    """Deterministic date between start and end."""
    days_range = (end - start).days
    offset = _hash_int(seed, 0, max(0, days_range))
    return start + timedelta(days=offset)


print("Hash functions loaded. TODAY =", TODAY, " SIX_MONTHS_AGO =", SIX_MONTHS_AGO)

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS — Zoox Fleet Intelligence Domain Entities
# ═══════════════════════════════════════════════════════════════════════════

CITIES = ["Las Vegas", "San Francisco"]

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

# 50 vehicles — 30 in Las Vegas (ZX-001..ZX-030), 20 in San Francisco (ZX-031..ZX-050)
VEHICLES = []
for i in range(1, 51):
    vid = "ZX-" + str(i).zfill(3)
    city = "Las Vegas" if i <= 30 else "San Francisco"
    zone_options = LV_ZONE_IDS if city == "Las Vegas" else SF_ZONE_IDS
    home_zone = _hash_choice("home-zone-" + vid, zone_options)
    VEHICLES.append({"vehicle_id": vid, "model": "Zoox Robotaxi", "city": city, "home_zone": home_zone})

# Event venues
EVENT_VENUES = [
    {"venue": "The Sphere",                    "city": "Las Vegas",     "zone": "LV-SPHERE",     "types": ["concert", "experience", "special_event"],                "cap_lo": 8000,  "cap_hi": 18000, "events_per_week": 3.5},
    {"venue": "T-Mobile Arena",                "city": "Las Vegas",     "zone": "LV-ARENA",      "types": ["hockey", "concert", "boxing", "ufc"],                   "cap_lo": 12000, "cap_hi": 20000, "events_per_week": 2.0},
    {"venue": "Las Vegas Convention Center",   "city": "Las Vegas",     "zone": "LV-CONVENTION", "types": ["convention", "trade_show", "expo"],                     "cap_lo": 5000,  "cap_hi": 50000, "events_per_week": 0.5},
    {"venue": "Moscone Center",                "city": "San Francisco", "zone": "SF-SOMA",       "types": ["tech_conference", "convention"],                        "cap_lo": 3000,  "cap_hi": 30000, "events_per_week": 0.25},
    {"venue": "Chase Center",                  "city": "San Francisco", "zone": "SF-EMBARCADERO","types": ["basketball", "concert"],                                "cap_lo": 15000, "cap_hi": 18000, "events_per_week": 2.0},
]

# Realistic event names per venue
EVENT_NAMES = {
    "The Sphere": [
        "Sphere Experience: U2 Residency", "Sphere Experience: Postcard from Earth",
        "Sphere Experience: Dead & Company", "Sphere Experience: Eagles Residency",
        "Sphere: Phish Las Vegas", "Sphere Experience: Anyma", "Sphere: Special Event",
        "Sphere Experience: V-Unbeatable", "Sphere: New Year's Eve Spectacular",
        "Sphere Experience: Adele Residency", "Sphere: Immersive Light Show",
        "Sphere Experience: Coldplay Residency",
    ],
    "T-Mobile Arena": [
        "VGK vs Oilers", "VGK vs Avalanche", "VGK vs Kings", "VGK vs Sharks",
        "VGK vs Coyotes", "VGK vs Canucks", "VGK vs Flames", "VGK vs Blues",
        "VGK vs Stars", "VGK vs Wild", "VGK vs Jets", "VGK vs Kraken",
        "UFC Fight Night Las Vegas", "Canelo vs Benavidez", "Morgan Wallen Live",
        "Drake: It's All a Blur Tour", "Taylor Swift Surprise Show",
        "UFC 310: Main Card", "PBR World Finals", "VGK vs Blackhawks",
    ],
    "Las Vegas Convention Center": [
        "CES 2026", "SEMA Show 2025", "NAB Show 2026", "MAGIC Las Vegas",
        "World of Concrete 2026", "CONEXPO-CON/AGG", "Pack Expo Las Vegas",
        "HITEC Las Vegas", "AWS re:Invent 2025", "Money20/20 USA",
    ],
    "Moscone Center": [
        "Dreamforce 2025", "Google Cloud Next 2026", "RSA Conference 2026",
        "GDC 2026", "NVIDIA GTC 2026", "Databricks Data+AI Summit 2026",
        "Oracle CloudWorld 2025", "Salesforce Connections 2026",
    ],
    "Chase Center": [
        "Warriors vs Lakers", "Warriors vs Celtics", "Warriors vs Nuggets",
        "Warriors vs Suns", "Warriors vs Clippers", "Warriors vs Kings",
        "Warriors vs Grizzlies", "Warriors vs Thunder", "Warriors vs Mavericks",
        "Billie Eilish: Hit Me Hard and Soft Tour", "SZA: Lana Tour",
        "Bad Bunny: Most Wanted Tour", "Olivia Rodrigo: GUTS World Tour",
    ],
}

# Start hours for event types
EVENT_START_HOURS = {
    "concert": [19, 20], "experience": [14, 17, 19], "special_event": [18, 19, 20],
    "hockey": [17, 19], "boxing": [18, 20], "ufc": [18, 20],
    "convention": [9, 10], "trade_show": [9, 10], "expo": [9, 10],
    "tech_conference": [9, 10], "basketball": [17, 19],
}

# Event durations in hours by type
EVENT_DURATIONS = {
    "concert": 3, "experience": 2, "special_event": 3,
    "hockey": 3, "boxing": 4, "ufc": 4,
    "convention": 8, "trade_show": 8, "expo": 8,
    "tech_conference": 8, "basketball": 3,
}

# Paid rides start date (free rides before this)
PAID_RIDES_START = date(2025, 12, 1)

print("Constants loaded.")
print("  Zones:", len(ZONES))
print("  Vehicles:", len(VEHICLES))
print("  Event Venues:", len(EVENT_VENUES))

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 1: zones (9 rows)
# ═══════════════════════════════════════════════════════════════════════════

zones_schema = StructType([
    StructField("zone_id", StringType()),
    StructField("zone_name", StringType()),
    StructField("city", StringType()),
    StructField("base_demand_per_hour", IntegerType()),
    StructField("vehicle_capacity", IntegerType()),
    StructField("latitude", DoubleType()),
    StructField("longitude", DoubleType()),
])

zones_rows = []
for z in ZONES:
    zones_rows.append(Row(
        zone_id=z["zone_id"],
        zone_name=z["zone_name"],
        city=z["city"],
        base_demand_per_hour=z["base_demand"],
        vehicle_capacity=z["capacity"],
        latitude=z["lat"],
        longitude=z["lon"],
    ))

df_zones = spark.createDataFrame(zones_rows, zones_schema)
df_zones.write.mode("overwrite").saveAsTable("zones")
print("Created zones table with", df_zones.count(), "rows")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 2: vehicles (50 rows)
# ═══════════════════════════════════════════════════════════════════════════

vehicles_schema = StructType([
    StructField("vehicle_id", StringType()),
    StructField("model", StringType()),
    StructField("city", StringType()),
    StructField("current_zone", StringType()),
    StructField("status", StringType()),
    StructField("battery_pct", IntegerType()),
    StructField("rides_today", IntegerType()),
    StructField("last_ride_at", StringType()),
    StructField("commissioned_date", DateType()),
])

STATUS_OPTIONS = ["active", "active", "active", "idle", "charging", "maintenance", "en_route"]
STATUS_WEIGHTS = [3, 3, 3, 2, 2, 1, 1]

vehicles_rows = []
for v in VEHICLES:
    vid = v["vehicle_id"]
    zone_options = LV_ZONE_IDS if v["city"] == "Las Vegas" else SF_ZONE_IDS
    current_zone = _hash_choice("cur-zone-" + vid, zone_options)
    status = _hash_weighted("status-" + vid, STATUS_OPTIONS, STATUS_WEIGHTS)
    battery = _hash_int("battery-" + vid, 20, 100)
    rides_today = _hash_int("rides-today-" + vid, 0, 25)
    commissioned = _hash_date("commission-" + vid, SIX_MONTHS_AGO, TODAY - timedelta(days=30))

    # Generate a recent last_ride_at timestamp
    hours_ago = _hash_int("last-ride-hrs-" + vid, 0, 8)
    minutes_ago = _hash_int("last-ride-min-" + vid, 0, 59)
    last_ride_dt = datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0) - timedelta(hours=hours_ago, minutes=minutes_ago)
    last_ride_str = last_ride_dt.strftime("%Y-%m-%d %H:%M:%S")

    vehicles_rows.append(Row(
        vehicle_id=vid,
        model=v["model"],
        city=v["city"],
        current_zone=current_zone,
        status=status,
        battery_pct=battery,
        rides_today=rides_today,
        last_ride_at=last_ride_str,
        commissioned_date=commissioned,
    ))

df_vehicles = spark.createDataFrame(vehicles_rows, vehicles_schema)
df_vehicles.write.mode("overwrite").saveAsTable("vehicles")
print("Created vehicles table with", df_vehicles.count(), "rows")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 3: events (~200 rows)
# ═══════════════════════════════════════════════════════════════════════════

events_schema = StructType([
    StructField("event_id", StringType()),
    StructField("venue", StringType()),
    StructField("event_name", StringType()),
    StructField("event_type", StringType()),
    StructField("city", StringType()),
    StructField("zone", StringType()),
    StructField("expected_attendance", IntegerType()),
    StructField("event_date", DateType()),
    StructField("start_time", StringType()),
    StructField("end_time", StringType()),
    StructField("demand_multiplier", DoubleType()),
])

events_rows = []
event_counter = 0

for venue_info in EVENT_VENUES:
    venue = venue_info["venue"]
    city = venue_info["city"]
    zone = venue_info["zone"]
    types = venue_info["types"]
    cap_lo = venue_info["cap_lo"]
    cap_hi = venue_info["cap_hi"]
    events_per_week = venue_info["events_per_week"]
    names_list = EVENT_NAMES[venue]

    # Calculate total events over 6-month window
    total_weeks = 180 / 7.0
    total_events = int(total_weeks * events_per_week)

    for i in range(total_events):
        event_counter += 1
        eid = "EVT-" + str(event_counter).zfill(4)
        seed_base = venue + "-" + str(i)

        # Pick event date spread across the window
        event_date = _hash_date("evt-date-" + seed_base, SIX_MONTHS_AGO, TODAY)

        # Pick event type and name
        event_type = _hash_choice("evt-type-" + seed_base, types)
        event_name = _hash_choice("evt-name-" + seed_base, names_list)

        # Attendance
        attendance = _hash_int("evt-att-" + seed_base, cap_lo, cap_hi)

        # Start hour based on event type
        start_hours_options = EVENT_START_HOURS.get(event_type, [19])
        start_hour = _hash_choice("evt-hour-" + seed_base, start_hours_options)
        start_min = _hash_choice("evt-min-" + seed_base, [0, 0, 0, 30])
        duration = EVENT_DURATIONS.get(event_type, 3)
        end_hour = start_hour + duration
        end_min = start_min

        start_h_str = str(start_hour).zfill(2)
        start_m_str = str(start_min).zfill(2)
        end_h_str = str(min(end_hour, 23)).zfill(2)
        end_m_str = str(end_min).zfill(2)
        start_time_str = start_h_str + ":" + start_m_str
        end_time_str = end_h_str + ":" + end_m_str

        # Demand multiplier: attendance / 10000, clamped to [1.5, 4.0]
        raw_mult = attendance / 10000.0
        demand_mult = max(1.5, min(4.0, raw_mult))
        demand_mult = round(demand_mult, 2)

        events_rows.append(Row(
            event_id=eid,
            venue=venue,
            event_name=event_name,
            event_type=event_type,
            city=city,
            zone=zone,
            expected_attendance=attendance,
            event_date=event_date,
            start_time=start_time_str,
            end_time=end_time_str,
            demand_multiplier=demand_mult,
        ))

df_events = spark.createDataFrame(events_rows, events_schema)
df_events.write.mode("overwrite").saveAsTable("events")
print("Created events table with", df_events.count(), "rows")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 4: rides (~50,000 rows)
# ═══════════════════════════════════════════════════════════════════════════
# ~280 rides/day average across the fleet, with spikes on event days.
# Rides before Dec 1 2025 are free (fare = 0.0), paid after.

rides_schema = StructType([
    StructField("ride_id", StringType()),
    StructField("vehicle_id", StringType()),
    StructField("city", StringType()),
    StructField("pickup_zone", StringType()),
    StructField("dropoff_zone", StringType()),
    StructField("request_time", StringType()),
    StructField("pickup_time", StringType()),
    StructField("dropoff_time", StringType()),
    StructField("wait_time_min", DoubleType()),
    StructField("distance_miles", DoubleType()),
    StructField("fare_usd", DoubleType()),
    StructField("ride_status", StringType()),
])

# Build a lookup of event dates by city for demand spikes
event_dates_by_city = {}
for ev in events_rows:
    key = str(ev.event_date) + "|" + ev.city
    if key not in event_dates_by_city:
        event_dates_by_city[key] = 0.0
    # Take the max multiplier if multiple events on same day
    event_dates_by_city[key] = max(event_dates_by_city[key], ev.demand_multiplier)

rides_rows = []
ride_counter = 0
current_day = SIX_MONTHS_AGO

while current_day <= TODAY:
    day_str = current_day.isoformat()

    # Determine base rides for this day
    # Weekends get slightly more rides
    day_of_week = current_day.weekday()
    is_weekend = day_of_week >= 5
    base_rides_lv = 180 if is_weekend else 150
    base_rides_sf = 130 if is_weekend else 100

    # Check for events and apply multiplier
    lv_key = day_str + "|Las Vegas"
    sf_key = day_str + "|San Francisco"
    lv_mult = event_dates_by_city.get(lv_key, 1.0)
    sf_mult = event_dates_by_city.get(sf_key, 1.0)

    # Apply event multiplier (but cap total to avoid explosion)
    rides_lv = min(int(base_rides_lv * max(lv_mult, 1.0)), 500)
    rides_sf = min(int(base_rides_sf * max(sf_mult, 1.0)), 350)

    # Add some hash-based daily variation (+/- 15%)
    variation_lv = _hash_float("day-var-lv-" + day_str, 0.85, 1.15)
    variation_sf = _hash_float("day-var-sf-" + day_str, 0.85, 1.15)
    rides_lv = int(rides_lv * variation_lv)
    rides_sf = int(rides_sf * variation_sf)

    lv_vehicles = [v["vehicle_id"] for v in VEHICLES if v["city"] == "Las Vegas"]
    sf_vehicles = [v["vehicle_id"] for v in VEHICLES if v["city"] == "San Francisco"]

    is_paid = current_day >= PAID_RIDES_START
    has_lv_event = lv_mult > 1.0
    has_sf_event = sf_mult > 1.0

    for city_rides, city, city_zones, city_vehicles, has_event in [
        (rides_lv, "Las Vegas", LV_ZONE_IDS, lv_vehicles, has_lv_event),
        (rides_sf, "San Francisco", SF_ZONE_IDS, sf_vehicles, has_sf_event),
    ]:
        for r in range(city_rides):
            ride_counter += 1
            rid = "RD-" + str(ride_counter).zfill(7)
            seed_base = rid + "-" + day_str

            vehicle_id = _hash_choice("ride-veh-" + seed_base, city_vehicles)
            pickup_zone = _hash_choice("ride-pu-" + seed_base, city_zones)
            dropoff_zone = _hash_choice("ride-do-" + seed_base, city_zones)

            # Request time: spread across the day, heavier in evening
            hour = _hash_weighted(
                "ride-hr-" + seed_base,
                list(range(24)),
                [1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 5, 5, 5, 5, 6, 7, 8, 9, 10, 10, 9, 7, 4, 2],
            )
            minute = _hash_int("ride-min-" + seed_base, 0, 59)
            second = _hash_int("ride-sec-" + seed_base, 0, 59)

            h_str = str(hour).zfill(2)
            m_str = str(minute).zfill(2)
            s_str = str(second).zfill(2)
            request_time = day_str + " " + h_str + ":" + m_str + ":" + s_str

            # Wait time: higher during events
            if has_event:
                wait_min = round(_hash_float("ride-wait-" + seed_base, 5.0, 20.0), 1)
            else:
                wait_min = round(_hash_float("ride-wait-" + seed_base, 2.0, 12.0), 1)

            # Pickup time = request_time + wait
            pickup_dt = datetime(
                current_day.year, current_day.month, current_day.day,
                hour, minute, second
            ) + timedelta(minutes=wait_min)
            pickup_time = pickup_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Distance and trip duration
            distance = round(_hash_float("ride-dist-" + seed_base, 1.0, 15.0), 1)
            trip_minutes = distance * _hash_float("ride-speed-" + seed_base, 2.5, 5.0)
            dropoff_dt = pickup_dt + timedelta(minutes=trip_minutes)
            dropoff_time = dropoff_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Fare: free before Dec 1 2025, paid after
            if is_paid:
                fare = round(_hash_float("ride-fare-" + seed_base, 2.0, 15.0), 2)
            else:
                fare = 0.0

            # Ride status
            if current_day == TODAY and hour >= 10:
                status = _hash_weighted(
                    "ride-st-" + seed_base,
                    ["completed", "in_progress", "cancelled"],
                    [70, 20, 10],
                )
            else:
                status = _hash_weighted(
                    "ride-st-" + seed_base,
                    ["completed", "cancelled"],
                    [95, 5],
                )

            rides_rows.append(Row(
                ride_id=rid,
                vehicle_id=vehicle_id,
                city=city,
                pickup_zone=pickup_zone,
                dropoff_zone=dropoff_zone,
                request_time=request_time,
                pickup_time=pickup_time,
                dropoff_time=dropoff_time,
                wait_time_min=wait_min,
                distance_miles=distance,
                fare_usd=fare,
                ride_status=status,
            ))

    current_day += timedelta(days=1)

print("Generated", len(rides_rows), "ride records. Writing to Delta Lake...")

# COMMAND ----------

# Write rides table (separate cell for large table — better notebook UX)
df_rides = spark.createDataFrame(rides_rows, rides_schema)
df_rides.write.mode("overwrite").saveAsTable("rides")
print("Created rides table with", df_rides.count(), "rows")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 5: demand_forecasts (~5,000 rows)
# ═══════════════════════════════════════════════════════════════════════════
# Future forecasts (next 7 days) + historical forecasts (past 30 days).
# One row per zone per hour.

forecasts_schema = StructType([
    StructField("forecast_id", StringType()),
    StructField("zone_id", StringType()),
    StructField("city", StringType()),
    StructField("forecast_date", DateType()),
    StructField("hour", IntegerType()),
    StructField("predicted_demand", IntegerType()),
    StructField("predicted_supply", IntegerType()),
    StructField("demand_score", DoubleType()),
    StructField("confidence", DoubleType()),
    StructField("model_version", StringType()),
])

# Build event lookup for forecast period
forecast_event_lookup = {}
for ev in events_rows:
    key = str(ev.event_date) + "|" + ev.zone
    if key not in forecast_event_lookup:
        forecast_event_lookup[key] = ev.demand_multiplier
    else:
        forecast_event_lookup[key] = max(forecast_event_lookup[key], ev.demand_multiplier)

forecasts_rows = []
fc_counter = 0

# Historical forecasts: past 30 days, sample every 3rd hour to keep size reasonable
hist_start = TODAY - timedelta(days=30)
hist_day = hist_start
while hist_day < TODAY:
    day_str = hist_day.isoformat()
    for z in ZONES:
        zid = z["zone_id"]
        city = z["city"]
        base = z["base_demand"]
        cap = z["capacity"]
        event_key = day_str + "|" + zid
        event_mult = forecast_event_lookup.get(event_key, 1.0)

        for hour in range(0, 24, 3):  # Every 3 hours for historical
            fc_counter += 1
            fid = "FC-" + str(fc_counter).zfill(6)
            seed_base = fid + "-" + day_str + "-" + zid + "-" + str(hour)

            # Hour-of-day demand curve
            hour_weight = [0.2, 0.15, 0.1, 0.1, 0.15, 0.3, 0.5, 0.7, 0.8, 0.85, 0.8, 0.75,
                           0.7, 0.75, 0.8, 0.85, 0.9, 1.0, 1.0, 0.95, 0.85, 0.7, 0.5, 0.3]
            hw = hour_weight[hour]

            predicted = int(base * hw * max(event_mult, 1.0) * _hash_float("fc-demand-" + seed_base, 0.8, 1.2))
            predicted = max(1, predicted)
            supply = int(cap * _hash_float("fc-supply-" + seed_base, 0.5, 1.0))
            supply = max(1, supply)

            demand_score = round(min(1.0, predicted / (base * 1.5)), 2)
            if event_mult > 1.0:
                demand_score = round(min(1.0, demand_score * 1.3), 2)

            confidence = round(_hash_float("fc-conf-" + seed_base, 0.70, 0.98), 2)

            forecasts_rows.append(Row(
                forecast_id=fid,
                zone_id=zid,
                city=city,
                forecast_date=hist_day,
                hour=hour,
                predicted_demand=predicted,
                predicted_supply=supply,
                demand_score=demand_score,
                confidence=confidence,
                model_version="v2.3",
            ))

    hist_day += timedelta(days=1)

# Future forecasts: next 7 days, every hour (high resolution for operational use)
for day_offset in range(0, 8):
    fc_day = TODAY + timedelta(days=day_offset)
    day_str = fc_day.isoformat()

    for z in ZONES:
        zid = z["zone_id"]
        city = z["city"]
        base = z["base_demand"]
        cap = z["capacity"]
        event_key = day_str + "|" + zid
        event_mult = forecast_event_lookup.get(event_key, 1.0)

        for hour in range(24):
            fc_counter += 1
            fid = "FC-" + str(fc_counter).zfill(6)
            seed_base = fid + "-" + day_str + "-" + zid + "-" + str(hour)

            hour_weight = [0.2, 0.15, 0.1, 0.1, 0.15, 0.3, 0.5, 0.7, 0.8, 0.85, 0.8, 0.75,
                           0.7, 0.75, 0.8, 0.85, 0.9, 1.0, 1.0, 0.95, 0.85, 0.7, 0.5, 0.3]
            hw = hour_weight[hour]

            predicted = int(base * hw * max(event_mult, 1.0) * _hash_float("fc-demand-" + seed_base, 0.8, 1.2))
            predicted = max(1, predicted)
            supply = int(cap * _hash_float("fc-supply-" + seed_base, 0.5, 1.0))
            supply = max(1, supply)

            demand_score = round(min(1.0, predicted / (base * 1.5)), 2)
            if event_mult > 1.0:
                demand_score = round(min(1.0, demand_score * 1.3), 2)

            # Future forecasts have slightly lower confidence further out
            base_conf = 0.95 - (day_offset * 0.02)
            confidence = round(_hash_float("fc-conf-" + seed_base, max(0.70, base_conf - 0.10), min(0.98, base_conf + 0.03)), 2)

            forecasts_rows.append(Row(
                forecast_id=fid,
                zone_id=zid,
                city=city,
                forecast_date=fc_day,
                hour=hour,
                predicted_demand=predicted,
                predicted_supply=supply,
                demand_score=demand_score,
                confidence=confidence,
                model_version="v2.3",
            ))

print("Generated", len(forecasts_rows), "forecast records. Writing to Delta Lake...")

# COMMAND ----------

# Write demand_forecasts table
df_forecasts = spark.createDataFrame(forecasts_rows, forecasts_schema)
df_forecasts.write.mode("overwrite").saveAsTable("demand_forecasts")
print("Created demand_forecasts table with", df_forecasts.count(), "rows")

# COMMAND ----------

# ═══════════════════════════════════════════════════════════════════════════
# VERIFY ALL TABLES
# ═══════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("Zoox Fleet Intelligence — Data Generation Complete")
print("=" * 70)
table_name = CATALOG + "." + SCHEMA
print("Catalog.Schema:", table_name)
print("")
print("Table row counts:")
for t in ["zones", "vehicles", "events", "rides", "demand_forecasts"]:
    full_table = CATALOG + "." + SCHEMA + "." + t
    count = spark.sql("SELECT COUNT(*) as cnt FROM " + full_table).collect()[0]["cnt"]
    print("  " + t + ": " + str(count) + " rows")
print("")
print("Done. Proceed to Lakebase setup (03_seed_lakebase.py) and app deployment.")

# COMMAND ----------

spark.sql("SHOW TABLES").display()

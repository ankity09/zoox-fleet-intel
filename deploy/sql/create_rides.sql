-- Zoox Fleet Intelligence: rides table (~50K rows)
-- Hash-based deterministic generation over 180-day window.
-- Strategy: generate days -> expand to rides-per-day -> hash all fields.
-- Helper: h(seed) = CAST(conv(substr(sha2(seed, 256), 1, 8), 16, 10) AS BIGINT)

DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.rides;

-- SPLIT

CREATE TABLE ${CATALOG}.${SCHEMA}.rides (
  ride_id        STRING,
  vehicle_id     STRING,
  city           STRING,
  pickup_zone    STRING,
  dropoff_zone   STRING,
  request_time   STRING,
  pickup_time    STRING,
  dropoff_time   STRING,
  wait_time_min  DOUBLE,
  distance_miles DOUBLE,
  fare_usd       DOUBLE,
  ride_status    STRING
) USING DELTA;

-- SPLIT

-- Build a temp view of event max multipliers per (event_date, city) from the events table.
-- This allows rides on event days to have boosted counts.
CREATE OR REPLACE TEMPORARY VIEW event_day_multipliers AS
SELECT
  event_date,
  city,
  MAX(demand_multiplier) AS max_mult
FROM ${CATALOG}.${SCHEMA}.events
GROUP BY event_date, city;

-- SPLIT

INSERT INTO ${CATALOG}.${SCHEMA}.rides
WITH
-- Step 1: Generate day sequence from SIX_MONTHS_AGO to TODAY
days AS (
  SELECT
    date_add(date_sub(current_date(), 180), cast(d AS INT)) AS ride_date
  FROM (SELECT explode(sequence(0, 180)) AS d)
),

-- Step 2: Cross-join days with cities, compute rides per city per day
day_city AS (
  SELECT
    d.ride_date,
    c.city,
    CASE
      WHEN c.city = 'Las Vegas' AND dayofweek(d.ride_date) IN (1, 7) THEN 180
      WHEN c.city = 'Las Vegas' THEN 150
      WHEN c.city = 'San Francisco' AND dayofweek(d.ride_date) IN (1, 7) THEN 130
      ELSE 100
    END AS base_rides,
    COALESCE(edm.max_mult, 1.0) AS event_mult
  FROM days d
  CROSS JOIN (SELECT 'Las Vegas' AS city UNION ALL SELECT 'San Francisco') c
  LEFT JOIN event_day_multipliers edm
    ON edm.event_date = d.ride_date AND edm.city = c.city
),

-- Step 3: Compute actual ride count per day/city
day_city_count AS (
  SELECT
    ride_date,
    city,
    CAST(
      LEAST(
        CASE WHEN city = 'Las Vegas' THEN 500 ELSE 350 END,
        base_rides * GREATEST(event_mult, 1.0)
      )
      * (0.85 + (CAST(conv(substr(sha2(concat('day-var-', city, '-', date_format(ride_date, 'yyyy-MM-dd')), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 0.30)
    AS INT) AS ride_count
  FROM day_city
),

-- Step 4: Explode ride_count into individual ride rows
ride_rows AS (
  SELECT
    dcc.ride_date,
    dcc.city,
    r_idx.ride_num,
    ROW_NUMBER() OVER (ORDER BY dcc.ride_date, dcc.city, r_idx.ride_num) AS global_rn,
    concat(date_format(dcc.ride_date, 'yyyy-MM-dd'), '-', dcc.city, '-', cast(r_idx.ride_num AS STRING)) AS seed
  FROM day_city_count dcc
  LATERAL VIEW explode(sequence(1, dcc.ride_count)) r_idx AS ride_num
),

-- Step 5: Hash all ride fields
ride_hashed AS (
  SELECT
    rr.global_rn,
    rr.ride_date,
    rr.city,
    rr.seed,

    -- vehicle_id: pick from city's vehicles
    CASE WHEN rr.city = 'Las Vegas'
      THEN concat('ZX-', lpad(cast(1 + CAST(CAST(conv(substr(sha2(concat('ride-veh-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 30 AS INT) AS STRING), 3, '0'))
      ELSE concat('ZX-', lpad(cast(31 + CAST(CAST(conv(substr(sha2(concat('ride-veh-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 20 AS INT) AS STRING), 3, '0'))
    END AS vehicle_id,

    -- pickup_zone
    CASE WHEN rr.city = 'Las Vegas'
      THEN element_at(array('LV-STRIP', 'LV-DOWNTOWN', 'LV-ARENA', 'LV-SPHERE', 'LV-CONVENTION'),
        CAST(CAST(conv(substr(sha2(concat('ride-pu-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 5 AS INT) + 1)
      ELSE element_at(array('SF-SOMA', 'SF-MISSION', 'SF-EMBARCADERO', 'SF-CASTRO'),
        CAST(CAST(conv(substr(sha2(concat('ride-pu-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 4 AS INT) + 1)
    END AS pickup_zone,

    -- dropoff_zone
    CASE WHEN rr.city = 'Las Vegas'
      THEN element_at(array('LV-STRIP', 'LV-DOWNTOWN', 'LV-ARENA', 'LV-SPHERE', 'LV-CONVENTION'),
        CAST(CAST(conv(substr(sha2(concat('ride-do-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 5 AS INT) + 1)
      ELSE element_at(array('SF-SOMA', 'SF-MISSION', 'SF-EMBARCADERO', 'SF-CASTRO'),
        CAST(CAST(conv(substr(sha2(concat('ride-do-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 4 AS INT) + 1)
    END AS dropoff_zone,

    -- Hour of day: weighted distribution favoring evening hours
    -- Weights: [1,1,1,1,1,2,3,4,5,5,5,5,5,5,6,7,8,9,10,10,9,7,4,2] total=118
    -- Expand each hour by its weight into a 118-element array, pick via modulo
    element_at(
      array(
        0, 1, 2, 3, 4,
        5, 5,
        6, 6, 6,
        7, 7, 7, 7,
        8, 8, 8, 8, 8,
        9, 9, 9, 9, 9,
        10, 10, 10, 10, 10,
        11, 11, 11, 11, 11,
        12, 12, 12, 12, 12,
        13, 13, 13, 13, 13,
        14, 14, 14, 14, 14, 14,
        15, 15, 15, 15, 15, 15, 15,
        16, 16, 16, 16, 16, 16, 16, 16,
        17, 17, 17, 17, 17, 17, 17, 17, 17,
        18, 18, 18, 18, 18, 18, 18, 18, 18, 18,
        19, 19, 19, 19, 19, 19, 19, 19, 19, 19,
        20, 20, 20, 20, 20, 20, 20, 20, 20,
        21, 21, 21, 21, 21, 21, 21,
        22, 22, 22, 22,
        23, 23
      ),
      CAST(CAST(conv(substr(sha2(concat('ride-hr-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 118 AS INT) + 1
    ) AS ride_hour,

    CAST(CAST(conv(substr(sha2(concat('ride-min-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 60 AS INT) AS ride_minute,
    CAST(CAST(conv(substr(sha2(concat('ride-sec-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 60 AS INT) AS ride_second,

    -- wait_time_min: 2-12 min
    ROUND(2.0 + (CAST(conv(substr(sha2(concat('ride-wait-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 10.0, 1) AS wait_time_min,

    -- distance_miles: 1-15
    ROUND(1.0 + (CAST(conv(substr(sha2(concat('ride-dist-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 14.0, 1) AS distance_miles,

    -- speed factor for trip duration: 2.5-5.0 min/mile
    2.5 + (CAST(conv(substr(sha2(concat('ride-speed-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 2.5 AS speed_factor,

    -- fare: $0 before 2025-12-01, $2-15 after
    CASE
      WHEN rr.ride_date >= DATE '2025-12-01'
        THEN ROUND(2.0 + (CAST(conv(substr(sha2(concat('ride-fare-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 13.0, 2)
      ELSE 0.0
    END AS fare_usd,

    -- ride_status: 95% completed / 5% cancelled; today's rides also have in_progress
    CASE
      WHEN rr.ride_date = current_date()
        THEN element_at(
          array(
            'completed','completed','completed','completed','completed','completed','completed',
            'in_progress','in_progress',
            'cancelled'
          ),
          CAST(CAST(conv(substr(sha2(concat('ride-st-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 10 AS INT) + 1
        )
      ELSE
        CASE WHEN CAST(conv(substr(sha2(concat('ride-st-', seed), 256), 1, 8), 16, 10) AS BIGINT) % 20 = 0
          THEN 'cancelled'
          ELSE 'completed'
        END
    END AS ride_status

  FROM ride_rows rr
),

-- Step 6: Compute timestamps from components
ride_final AS (
  SELECT
    rh.*,
    cast(concat(
      date_format(ride_date, 'yyyy-MM-dd'), ' ',
      lpad(cast(ride_hour AS STRING), 2, '0'), ':',
      lpad(cast(ride_minute AS STRING), 2, '0'), ':',
      lpad(cast(ride_second AS STRING), 2, '0')
    ) AS TIMESTAMP) AS request_ts,
    ROUND(distance_miles * speed_factor, 1) AS trip_minutes
  FROM ride_hashed rh
)

SELECT
  concat('RD-', lpad(cast(global_rn AS STRING), 7, '0')) AS ride_id,
  vehicle_id,
  city,
  pickup_zone,
  dropoff_zone,
  date_format(request_ts, 'yyyy-MM-dd HH:mm:ss') AS request_time,
  date_format(request_ts + make_interval(0, 0, 0, 0, 0, cast(wait_time_min AS INT), 0), 'yyyy-MM-dd HH:mm:ss') AS pickup_time,
  date_format(request_ts + make_interval(0, 0, 0, 0, 0, cast(wait_time_min + trip_minutes AS INT), 0), 'yyyy-MM-dd HH:mm:ss') AS dropoff_time,
  wait_time_min,
  distance_miles,
  fare_usd,
  ride_status
FROM ride_final;

-- SPLIT

-- Clean up temp view
DROP VIEW IF EXISTS event_day_multipliers;

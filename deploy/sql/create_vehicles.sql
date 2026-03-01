-- Zoox Fleet Intelligence: vehicles table (50 rows)
-- Hash-based deterministic generation using sha2/conv for all derived fields.
-- Helper: h(seed) = CAST(conv(substr(sha2(seed, 256), 1, 8), 16, 10) AS BIGINT)
-- This gives a deterministic integer in [0, 4294967295] from any string seed.

DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.vehicles;

-- SPLIT

CREATE TABLE ${CATALOG}.${SCHEMA}.vehicles (
  vehicle_id        STRING,
  model             STRING,
  city              STRING,
  current_zone      STRING,
  status            STRING,
  battery_pct       INT,
  rides_today       INT,
  last_ride_at      STRING,
  commissioned_date DATE
) USING DELTA;

-- SPLIT

INSERT INTO ${CATALOG}.${SCHEMA}.vehicles
WITH seq AS (
  SELECT explode(sequence(1, 50)) AS num
),
raw AS (
  SELECT
    num,
    concat('ZX-', lpad(cast(num AS STRING), 3, '0')) AS vehicle_id,
    'Zoox Robotaxi' AS model,
    CASE WHEN num <= 30 THEN 'Las Vegas' ELSE 'San Francisco' END AS city,
    array('LV-STRIP', 'LV-DOWNTOWN', 'LV-ARENA', 'LV-SPHERE', 'LV-CONVENTION') AS lv_zones,
    array('SF-SOMA', 'SF-MISSION', 'SF-EMBARCADERO', 'SF-CASTRO') AS sf_zones,
    array('active', 'active', 'active', 'idle', 'charging', 'maintenance', 'en_route') AS status_arr
  FROM seq
),
hashed AS (
  SELECT
    vehicle_id,
    model,
    city,

    -- current_zone: pick from city-appropriate zone array
    CASE WHEN city = 'Las Vegas'
      THEN element_at(lv_zones,
        CAST(CAST(conv(substr(sha2(concat('cur-zone-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 5 AS INT) + 1)
      ELSE element_at(sf_zones,
        CAST(CAST(conv(substr(sha2(concat('cur-zone-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 4 AS INT) + 1)
    END AS current_zone,

    -- status: weighted pick from 7-element array (3x active weight)
    element_at(status_arr,
      CAST(CAST(conv(substr(sha2(concat('status-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 7 AS INT) + 1
    ) AS status,

    -- battery_pct: hash between 20 and 100
    20 + CAST(CAST(conv(substr(sha2(concat('battery-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 81 AS INT) AS battery_pct,

    -- rides_today: hash between 0 and 25
    CAST(CAST(conv(substr(sha2(concat('rides-today-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 26 AS INT) AS rides_today,

    -- commissioned_date: hash between SIX_MONTHS_AGO and TODAY-30
    date_add(
      date_sub(current_date(), 180),
      CAST(CAST(conv(substr(sha2(concat('commission-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 150 AS INT)
    ) AS commissioned_date,

    -- last_ride_at: today at noon minus hash-based hours/minutes
    CAST(CAST(conv(substr(sha2(concat('last-ride-hrs-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 9 AS INT) AS hrs_ago,
    CAST(CAST(conv(substr(sha2(concat('last-ride-min-', vehicle_id), 256), 1, 8), 16, 10) AS BIGINT) % 60 AS INT) AS mins_ago

  FROM raw
)
SELECT
  vehicle_id,
  model,
  city,
  current_zone,
  status,
  battery_pct,
  rides_today,
  date_format(
    cast(concat(
      date_format(current_date(), 'yyyy-MM-dd'),
      ' 12:00:00'
    ) AS TIMESTAMP) - INTERVAL '1' HOUR * hrs_ago - INTERVAL '1' MINUTE * mins_ago,
    'yyyy-MM-dd HH:mm:ss'
  ) AS last_ride_at,
  commissioned_date
FROM hashed;

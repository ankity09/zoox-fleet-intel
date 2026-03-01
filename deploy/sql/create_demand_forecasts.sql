-- Zoox Fleet Intelligence: demand_forecasts table (~5K rows)
-- Historical forecasts (past 30 days, every 3 hours) + future forecasts (next 7 days, every hour).
-- Cross-join zones with date/hour ranges, hash-based demand/supply values.

DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.demand_forecasts;

-- SPLIT

CREATE TABLE ${CATALOG}.${SCHEMA}.demand_forecasts (
  forecast_id      STRING,
  zone_id          STRING,
  city             STRING,
  forecast_date    DATE,
  hour             INT,
  predicted_demand INT,
  predicted_supply INT,
  demand_score     DOUBLE,
  confidence       DOUBLE,
  model_version    STRING
) USING DELTA;

-- SPLIT

INSERT INTO ${CATALOG}.${SCHEMA}.demand_forecasts
WITH
-- Zone reference data
zones AS (
  SELECT * FROM (VALUES
    ('LV-STRIP',      'Las Vegas',      45, 12),
    ('LV-DOWNTOWN',   'Las Vegas',      25,  8),
    ('LV-ARENA',      'Las Vegas',      30, 10),
    ('LV-SPHERE',     'Las Vegas',      35, 10),
    ('LV-CONVENTION', 'Las Vegas',      20,  6),
    ('SF-SOMA',       'San Francisco',  40,  8),
    ('SF-MISSION',    'San Francisco',  30,  6),
    ('SF-EMBARCADERO','San Francisco',  35,  7),
    ('SF-CASTRO',     'San Francisco',  20,  4)
  ) AS t(zone_id, city, base_demand, vehicle_capacity)
),

-- Hour-of-day demand weight curve (24 elements, indexed 0..23)
hour_weights AS (
  SELECT * FROM (VALUES
    (0, 0.20), (1, 0.15), (2, 0.10), (3, 0.10), (4, 0.15), (5, 0.30),
    (6, 0.50), (7, 0.70), (8, 0.80), (9, 0.85), (10, 0.80), (11, 0.75),
    (12, 0.70), (13, 0.75), (14, 0.80), (15, 0.85), (16, 0.90), (17, 1.00),
    (18, 1.00), (19, 0.95), (20, 0.85), (21, 0.70), (22, 0.50), (23, 0.30)
  ) AS t(hour, weight)
),

-- Event multiplier lookup per (date, zone) from the events table
event_zone_mult AS (
  SELECT
    event_date,
    zone AS zone_id,
    MAX(demand_multiplier) AS event_mult
  FROM ${CATALOG}.${SCHEMA}.events
  GROUP BY event_date, zone
),

-- ──────────────────────────────────────────────────────────
-- PART A: Historical forecasts — past 30 days, every 3 hours
-- ──────────────────────────────────────────────────────────
hist_dates AS (
  SELECT date_add(date_sub(current_date(), 30), cast(d AS INT)) AS forecast_date
  FROM (SELECT explode(sequence(0, 29)) AS d)
),

hist_hours AS (
  SELECT explode(sequence(0, 21, 3)) AS hour
),

hist_cross AS (
  SELECT
    z.zone_id, z.city, z.base_demand, z.vehicle_capacity,
    hd.forecast_date,
    hh.hour,
    hw.weight AS hour_weight,
    COALESCE(ezm.event_mult, 1.0) AS event_mult,
    concat(date_format(hd.forecast_date, 'yyyy-MM-dd'), '-', z.zone_id, '-', cast(hh.hour AS STRING)) AS seed,
    'historical' AS period
  FROM zones z
  CROSS JOIN hist_dates hd
  CROSS JOIN hist_hours hh
  JOIN hour_weights hw ON hw.hour = hh.hour
  LEFT JOIN event_zone_mult ezm ON ezm.event_date = hd.forecast_date AND ezm.zone_id = z.zone_id
),

-- ──────────────────────────────────────────────────────────
-- PART B: Future forecasts — next 7 days (incl. today), every hour
-- ──────────────────────────────────────────────────────────
future_dates AS (
  SELECT date_add(current_date(), cast(d AS INT)) AS forecast_date
  FROM (SELECT explode(sequence(0, 7)) AS d)
),

future_hours AS (
  SELECT explode(sequence(0, 23)) AS hour
),

future_cross AS (
  SELECT
    z.zone_id, z.city, z.base_demand, z.vehicle_capacity,
    fd.forecast_date,
    fh.hour,
    hw.weight AS hour_weight,
    COALESCE(ezm.event_mult, 1.0) AS event_mult,
    concat(date_format(fd.forecast_date, 'yyyy-MM-dd'), '-', z.zone_id, '-', cast(fh.hour AS STRING)) AS seed,
    'future' AS period
  FROM zones z
  CROSS JOIN future_dates fd
  CROSS JOIN future_hours fh
  JOIN hour_weights hw ON hw.hour = fh.hour
  LEFT JOIN event_zone_mult ezm ON ezm.event_date = fd.forecast_date AND ezm.zone_id = z.zone_id
),

-- ──────────────────────────────────────────────────────────
-- Combine historical + future
-- ──────────────────────────────────────────────────────────
all_forecasts AS (
  SELECT * FROM hist_cross
  UNION ALL
  SELECT * FROM future_cross
),

-- ──────────────────────────────────────────────────────────
-- Compute demand, supply, scores
-- ──────────────────────────────────────────────────────────
computed AS (
  SELECT
    af.*,

    -- predicted_demand: base * hour_weight * event_mult * random(0.8..1.2), min 1
    GREATEST(1, CAST(
      af.base_demand * af.hour_weight * GREATEST(af.event_mult, 1.0)
      * (0.8 + (CAST(conv(substr(sha2(concat('fc-demand-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 0.4)
    AS INT)) AS predicted_demand,

    -- predicted_supply: capacity * random(0.5..1.0), min 1
    GREATEST(1, CAST(
      af.vehicle_capacity
      * (0.5 + (CAST(conv(substr(sha2(concat('fc-supply-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 0.5)
    AS INT)) AS predicted_supply,

    -- day_offset for future confidence decay
    CASE
      WHEN af.period = 'future'
        THEN datediff(af.forecast_date, current_date())
      ELSE 0
    END AS day_offset

  FROM all_forecasts af
),

scored AS (
  SELECT
    c.*,

    -- demand_score: predicted / (base * 1.5), clamped to [0, 1], boosted 1.3x for events
    ROUND(LEAST(1.0,
      CASE WHEN c.event_mult > 1.0
        THEN LEAST(1.0, (cast(c.predicted_demand AS DOUBLE) / (c.base_demand * 1.5)) * 1.3)
        ELSE cast(c.predicted_demand AS DOUBLE) / (c.base_demand * 1.5)
      END
    ), 2) AS demand_score,

    -- confidence: historical = hash(0.70..0.98), future = decaying base with hash variation
    CASE
      WHEN c.period = 'historical'
        THEN ROUND(0.70 + (CAST(conv(substr(sha2(concat('fc-conf-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0) * 0.28, 2)
      ELSE ROUND(
        GREATEST(0.70,   0.95 - (c.day_offset * 0.02) - 0.10)
        + (CAST(conv(substr(sha2(concat('fc-conf-', seed), 256), 1, 8), 16, 10) AS BIGINT) / 4294967295.0)
        * (LEAST(0.98, 0.95 - (c.day_offset * 0.02) + 0.03) - GREATEST(0.70, 0.95 - (c.day_offset * 0.02) - 0.10)),
      2)
    END AS confidence

  FROM computed c
),

-- Assign sequential forecast IDs
numbered AS (
  SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY forecast_date, zone_id, hour) AS rn
  FROM scored
)

SELECT
  concat('FC-', lpad(cast(rn AS STRING), 6, '0')) AS forecast_id,
  zone_id,
  city,
  forecast_date,
  hour,
  predicted_demand,
  predicted_supply,
  demand_score,
  confidence,
  'v2.3' AS model_version
FROM numbered;

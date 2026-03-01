-- Zoox Fleet Intelligence: events table (~200 rows)
-- Hash-based deterministic generation for 5 venues over a 6-month window.
-- Helper: h(seed) = CAST(conv(substr(sha2(seed, 256), 1, 8), 16, 10) AS BIGINT)

DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.events;

-- SPLIT

CREATE TABLE ${CATALOG}.${SCHEMA}.events (
  event_id             STRING,
  venue                STRING,
  event_name           STRING,
  event_type           STRING,
  city                 STRING,
  zone                 STRING,
  expected_attendance  INT,
  event_date           DATE,
  start_time           STRING,
  end_time             STRING,
  demand_multiplier    DOUBLE
) USING DELTA;

-- SPLIT

INSERT INTO ${CATALOG}.${SCHEMA}.events
WITH venues AS (
  -- venue, city, zone, total_events (= floor(180/7 * events_per_week)), cap_lo, cap_hi
  SELECT * FROM (VALUES
    ('The Sphere',                   'Las Vegas',     'LV-SPHERE',     90,   8000, 18000),
    ('T-Mobile Arena',               'Las Vegas',     'LV-ARENA',      51,  12000, 20000),
    ('Las Vegas Convention Center',  'Las Vegas',     'LV-CONVENTION', 12,   5000, 50000),
    ('Moscone Center',               'San Francisco', 'SF-SOMA',        6,   3000, 30000),
    ('Chase Center',                 'San Francisco', 'SF-EMBARCADERO',51,  15000, 18000)
  ) AS t(venue, city, zone, total_events, cap_lo, cap_hi)
),

-- Event names per venue (indexed 1..N)
sphere_names AS (
  SELECT * FROM (VALUES
    (1, 'Sphere Experience: U2 Residency'), (2, 'Sphere Experience: Postcard from Earth'),
    (3, 'Sphere Experience: Dead & Company'), (4, 'Sphere Experience: Eagles Residency'),
    (5, 'Sphere: Phish Las Vegas'), (6, 'Sphere Experience: Anyma'), (7, 'Sphere: Special Event'),
    (8, 'Sphere Experience: V-Unbeatable'), (9, 'Sphere: New Year''s Eve Spectacular'),
    (10, 'Sphere Experience: Adele Residency'), (11, 'Sphere: Immersive Light Show'),
    (12, 'Sphere Experience: Coldplay Residency')
  ) AS t(idx, name)
),
tmobile_names AS (
  SELECT * FROM (VALUES
    (1, 'VGK vs Oilers'), (2, 'VGK vs Avalanche'), (3, 'VGK vs Kings'), (4, 'VGK vs Sharks'),
    (5, 'VGK vs Coyotes'), (6, 'VGK vs Canucks'), (7, 'VGK vs Flames'), (8, 'VGK vs Blues'),
    (9, 'VGK vs Stars'), (10, 'VGK vs Wild'), (11, 'VGK vs Jets'), (12, 'VGK vs Kraken'),
    (13, 'UFC Fight Night Las Vegas'), (14, 'Canelo vs Benavidez'), (15, 'Morgan Wallen Live'),
    (16, 'Drake: It''s All a Blur Tour'), (17, 'Taylor Swift Surprise Show'),
    (18, 'UFC 310: Main Card'), (19, 'PBR World Finals'), (20, 'VGK vs Blackhawks')
  ) AS t(idx, name)
),
lvcc_names AS (
  SELECT * FROM (VALUES
    (1, 'CES 2026'), (2, 'SEMA Show 2025'), (3, 'NAB Show 2026'), (4, 'MAGIC Las Vegas'),
    (5, 'World of Concrete 2026'), (6, 'CONEXPO-CON/AGG'), (7, 'Pack Expo Las Vegas'),
    (8, 'HITEC Las Vegas'), (9, 'AWS re:Invent 2025'), (10, 'Money20/20 USA')
  ) AS t(idx, name)
),
moscone_names AS (
  SELECT * FROM (VALUES
    (1, 'Dreamforce 2025'), (2, 'Google Cloud Next 2026'), (3, 'RSA Conference 2026'),
    (4, 'GDC 2026'), (5, 'NVIDIA GTC 2026'), (6, 'Databricks Data+AI Summit 2026'),
    (7, 'Oracle CloudWorld 2025'), (8, 'Salesforce Connections 2026')
  ) AS t(idx, name)
),
chase_names AS (
  SELECT * FROM (VALUES
    (1, 'Warriors vs Lakers'), (2, 'Warriors vs Celtics'), (3, 'Warriors vs Nuggets'),
    (4, 'Warriors vs Suns'), (5, 'Warriors vs Clippers'), (6, 'Warriors vs Kings'),
    (7, 'Warriors vs Grizzlies'), (8, 'Warriors vs Thunder'), (9, 'Warriors vs Mavericks'),
    (10, 'Billie Eilish: Hit Me Hard and Soft Tour'), (11, 'SZA: Lana Tour'),
    (12, 'Bad Bunny: Most Wanted Tour'), (13, 'Olivia Rodrigo: GUTS World Tour')
  ) AS t(idx, name)
),

-- Event types per venue (indexed 1..N)
venue_types AS (
  SELECT * FROM (VALUES
    ('The Sphere',                   1, 'concert'),     ('The Sphere',                   2, 'experience'),   ('The Sphere',                   3, 'special_event'),
    ('T-Mobile Arena',               1, 'hockey'),      ('T-Mobile Arena',               2, 'concert'),      ('T-Mobile Arena',               3, 'boxing'),       ('T-Mobile Arena', 4, 'ufc'),
    ('Las Vegas Convention Center',  1, 'convention'),  ('Las Vegas Convention Center',  2, 'trade_show'),   ('Las Vegas Convention Center',  3, 'expo'),
    ('Moscone Center',               1, 'tech_conference'), ('Moscone Center',            2, 'convention'),
    ('Chase Center',                 1, 'basketball'),  ('Chase Center',                 2, 'concert')
  ) AS t(venue, idx, etype)
),

venue_type_counts AS (
  SELECT venue, max(idx) AS type_count FROM venue_types GROUP BY venue
),
venue_name_counts AS (
  SELECT 'The Sphere' AS venue, 12 AS name_count
  UNION ALL SELECT 'T-Mobile Arena', 20
  UNION ALL SELECT 'Las Vegas Convention Center', 10
  UNION ALL SELECT 'Moscone Center', 8
  UNION ALL SELECT 'Chase Center', 13
),

-- Generate event indices per venue
event_indices AS (
  SELECT
    v.venue, v.city, v.zone, v.cap_lo, v.cap_hi,
    explode(sequence(0, v.total_events - 1)) AS event_idx
  FROM venues v
),

event_raw AS (
  SELECT
    ei.venue, ei.city, ei.zone, ei.cap_lo, ei.cap_hi, ei.event_idx,
    concat(ei.venue, '-', cast(ei.event_idx AS STRING)) AS seed_base,
    vtc.type_count,
    vnc.name_count
  FROM event_indices ei
  JOIN venue_type_counts vtc ON vtc.venue = ei.venue
  JOIN venue_name_counts vnc ON vnc.venue = ei.venue
),

event_hashed AS (
  SELECT
    er.*,
    -- event_date: hash into [SIX_MONTHS_AGO, TODAY]
    date_add(
      date_sub(current_date(), 180),
      CAST(CAST(conv(substr(sha2(concat('evt-date-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 181 AS INT)
    ) AS event_date,

    -- event_type index (1-based)
    CAST(CAST(conv(substr(sha2(concat('evt-type-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % type_count AS INT) + 1 AS type_idx,

    -- event_name index (1-based)
    CAST(CAST(conv(substr(sha2(concat('evt-name-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % name_count AS INT) + 1 AS name_idx,

    -- attendance: hash between cap_lo and cap_hi
    cap_lo + CAST(CAST(conv(substr(sha2(concat('evt-att-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % (cap_hi - cap_lo + 1) AS INT) AS expected_attendance,

    -- start_minute: pick from [0, 0, 0, 30] (75% chance of :00, 25% chance of :30)
    CASE WHEN CAST(conv(substr(sha2(concat('evt-min-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 4 = 3 THEN 30 ELSE 0 END AS start_min

  FROM event_raw er
),

-- Resolve event type string
event_with_type AS (
  SELECT
    eh.*,
    vt.etype AS event_type
  FROM event_hashed eh
  JOIN venue_types vt ON vt.venue = eh.venue AND vt.idx = eh.type_idx
),

-- Resolve event name string
event_with_name AS (
  SELECT
    ewt.*,
    COALESCE(sn.name, tn.name, ln.name, mn.name, cn.name) AS event_name
  FROM event_with_type ewt
  LEFT JOIN sphere_names  sn ON ewt.venue = 'The Sphere'                   AND sn.idx = ewt.name_idx
  LEFT JOIN tmobile_names tn ON ewt.venue = 'T-Mobile Arena'               AND tn.idx = ewt.name_idx
  LEFT JOIN lvcc_names    ln ON ewt.venue = 'Las Vegas Convention Center'   AND ln.idx = ewt.name_idx
  LEFT JOIN moscone_names mn ON ewt.venue = 'Moscone Center'               AND mn.idx = ewt.name_idx
  LEFT JOIN chase_names   cn ON ewt.venue = 'Chase Center'                 AND cn.idx = ewt.name_idx
),

-- Compute start/end hours and demand multiplier
event_final AS (
  SELECT
    ewn.*,
    -- Start hour based on event type (hash into type-specific hour arrays)
    CASE ewn.event_type
      WHEN 'concert'         THEN element_at(array(19, 20), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'experience'      THEN element_at(array(14, 17, 19), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 3 AS INT) + 1)
      WHEN 'special_event'   THEN element_at(array(18, 19, 20), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 3 AS INT) + 1)
      WHEN 'hockey'          THEN element_at(array(17, 19), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'boxing'          THEN element_at(array(18, 20), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'ufc'             THEN element_at(array(18, 20), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'convention'      THEN element_at(array(9, 10), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'trade_show'      THEN element_at(array(9, 10), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'expo'            THEN element_at(array(9, 10), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'tech_conference' THEN element_at(array(9, 10), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      WHEN 'basketball'      THEN element_at(array(17, 19), CAST(CAST(conv(substr(sha2(concat('evt-hour-', seed_base), 256), 1, 8), 16, 10) AS BIGINT) % 2 AS INT) + 1)
      ELSE 19
    END AS start_hour,

    -- Duration based on event type
    CASE ewn.event_type
      WHEN 'concert'         THEN 3
      WHEN 'experience'      THEN 2
      WHEN 'special_event'   THEN 3
      WHEN 'hockey'          THEN 3
      WHEN 'boxing'          THEN 4
      WHEN 'ufc'             THEN 4
      WHEN 'convention'      THEN 8
      WHEN 'trade_show'      THEN 8
      WHEN 'expo'            THEN 8
      WHEN 'tech_conference' THEN 8
      WHEN 'basketball'      THEN 3
      ELSE 3
    END AS duration_hours
  FROM event_with_name ewn
),

-- Assign sequential event IDs
numbered AS (
  SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY venue, event_idx) AS rn
  FROM event_final
)

SELECT
  concat('EVT-', lpad(cast(rn AS STRING), 4, '0')) AS event_id,
  venue,
  event_name,
  event_type,
  city,
  zone,
  expected_attendance,
  event_date,
  concat(lpad(cast(start_hour AS STRING), 2, '0'), ':', lpad(cast(start_min AS STRING), 2, '0')) AS start_time,
  concat(lpad(cast(LEAST(start_hour + duration_hours, 23) AS STRING), 2, '0'), ':', lpad(cast(start_min AS STRING), 2, '0')) AS end_time,
  ROUND(LEAST(4.0, GREATEST(1.5, expected_attendance / 10000.0)), 2) AS demand_multiplier
FROM numbered;

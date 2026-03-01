-- Zoox Fleet Intelligence: zones table (9 rows)
-- Pure INSERT VALUES — no dependencies.

DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.zones;

-- SPLIT

CREATE TABLE ${CATALOG}.${SCHEMA}.zones (
  zone_id              STRING,
  zone_name            STRING,
  city                 STRING,
  base_demand_per_hour INT,
  vehicle_capacity     INT,
  latitude             DOUBLE,
  longitude            DOUBLE
) USING DELTA;

-- SPLIT

INSERT INTO ${CATALOG}.${SCHEMA}.zones VALUES
  ('LV-STRIP',      'Las Vegas Strip',             'Las Vegas',      45, 12, 36.1147, -115.1728),
  ('LV-DOWNTOWN',   'Downtown Las Vegas',          'Las Vegas',      25,  8, 36.1699, -115.1398),
  ('LV-ARENA',      'T-Mobile Arena District',     'Las Vegas',      30, 10, 36.1590, -115.1485),
  ('LV-SPHERE',     'Sphere District',             'Las Vegas',      35, 10, 36.1582, -115.1520),
  ('LV-CONVENTION', 'Convention Center District',   'Las Vegas',      20,  6, 36.1290, -115.1530),
  ('SF-SOMA',       'SoMa',                        'San Francisco',  40,  8, 37.7749, -122.3994),
  ('SF-MISSION',    'Mission District',            'San Francisco',  30,  6, 37.7599, -122.4148),
  ('SF-EMBARCADERO','Embarcadero',                 'San Francisco',  35,  7, 37.7936, -122.3930),
  ('SF-CASTRO',     'Castro',                      'San Francisco',  20,  4, 37.7609, -122.4350);

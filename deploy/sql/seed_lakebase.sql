-- Zoox Fleet Intelligence — Seed Lakebase (PostgreSQL)
-- Run via: databricks psql <instance> --profile=<profile> -- -d <database> -f deploy/sql/seed_lakebase.sql
-- Tables must already exist (created by core_schema.sql and domain_schema.sql).
-- All timestamps use NOW() - INTERVAL for relative offsets.
-- Uses ON CONFLICT DO NOTHING for idempotent re-runs.

BEGIN;

-- ============================================================
-- Truncate all tables (restart sequences, cascade FKs)
-- ============================================================
TRUNCATE fleet_actions, surge_alerts, dispatch_overrides, workflows, agent_actions, notes RESTART IDENTITY CASCADE;

-- ============================================================
-- 1. fleet_actions (~30 rows)
-- ============================================================
INSERT INTO fleet_actions (action_type, from_zone, to_zone, vehicle_count, city, reason, priority, status, executed_at) VALUES
  ('rebalance',       'LV-DOWNTOWN',   'LV-SPHERE',     4, 'Las Vegas',     'Sphere show ending 10pm - pre-position for demand surge',                        'high',     'executed',  NOW() - INTERVAL '655 hours'),
  ('rebalance',       'LV-CONVENTION', 'LV-STRIP',      3, 'Las Vegas',     'Convention ended - redirect to Strip nightlife demand',                           'medium',   'executed',  NOW() - INTERVAL '115 hours'),
  ('surge_deploy',    'LV-ARENA',      'LV-SPHERE',     5, 'Las Vegas',     'VGK game overlapping with Sphere show - maximum surge expected',                  'critical', 'executed',  NOW() - INTERVAL '26 hours'),
  ('rebalance',       'LV-STRIP',      'LV-ARENA',      2, 'Las Vegas',     'Knights game starting in 2 hours - stage vehicles near T-Mobile Arena',           'medium',   'executed',  NOW() - INTERVAL '282 hours'),
  ('charge_dispatch', 'LV-SPHERE',     'LV-DOWNTOWN',   3, 'Las Vegas',     'Low battery vehicles recalled to downtown charging hub',                          'low',      'executed',  NOW() - INTERVAL '251 hours'),
  ('rebalance',       'SF-CASTRO',     'SF-SOMA',        2, 'San Francisco', 'Morning commute demand shift to SoMa district',                                  'medium',   'executed',  NOW() - INTERVAL '229 hours'),
  ('surge_deploy',    'SF-MISSION',    'SF-EMBARCADERO', 3, 'San Francisco', 'Warriors game at Chase Center - deploy to Embarcadero',                           'high',     'executed',  NOW() - INTERVAL '143 hours'),
  ('rebalance',       'SF-EMBARCADERO','SF-MISSION',     2, 'San Francisco', 'Evening demand shifting to Mission district restaurants',                         'low',      'executed',  NOW() - INTERVAL '105 hours'),
  ('maintenance_pull','LV-STRIP',      'LV-DOWNTOWN',   1, 'Las Vegas',     'ZX-012 sensor calibration overdue - pull to maintenance bay',                     'medium',   'executed',  NOW() - INTERVAL '693 hours'),
  ('recall',          'LV-SPHERE',     'LV-CONVENTION',  2, 'Las Vegas',     'Post-show excess vehicles - redistribute to convention area',                     'low',      'executed',  NOW() - INTERVAL '559 hours'),
  ('rebalance',       'LV-DOWNTOWN',   'LV-ARENA',      3, 'Las Vegas',     'UFC fight night at T-Mobile Arena - pre-position vehicles',                       'high',     'executed',  NOW() - INTERVAL '90 hours'),
  ('surge_deploy',    'SF-SOMA',       'SF-EMBARCADERO', 4, 'San Francisco', 'Tech conference ending at Moscone - surge to Embarcadero transit',                'high',     'executed',  NOW() - INTERVAL '605 hours'),
  ('charge_dispatch', 'SF-MISSION',    'SF-CASTRO',      2, 'San Francisco', 'Battery levels critical in Mission fleet - rotate to charging',                   'medium',   'executed',  NOW() - INTERVAL '433 hours'),
  ('rebalance',       'LV-STRIP',      'LV-SPHERE',     3, 'Las Vegas',     'Sphere matinee show - afternoon pre-positioning',                                 'medium',   'executed',  NOW() - INTERVAL '33 hours'),
  ('rebalance',       'LV-ARENA',      'LV-DOWNTOWN',   2, 'Las Vegas',     'Post-game redistribution to downtown hotels',                                     'low',      'executed',  NOW() - INTERVAL '31 hours'),
  ('rebalance',       'LV-CONVENTION', 'LV-ARENA',      2, 'Las Vegas',     'Concert at T-Mobile Arena tonight',                                               'medium',   'approved',  NULL),
  ('surge_deploy',    'LV-DOWNTOWN',   'LV-SPHERE',     4, 'Las Vegas',     'Double Sphere show tonight - deploy maximum vehicles',                            'critical', 'approved',  NULL),
  ('rebalance',       'SF-EMBARCADERO','SF-SOMA',        2, 'San Francisco', 'Dreamforce attendees arriving at Moscone',                                        'medium',   'approved',  NULL),
  ('charge_dispatch', 'LV-STRIP',      'LV-CONVENTION',  2, 'Las Vegas',     'Overnight charging rotation',                                                    'low',      'approved',  NULL),
  ('rebalance',       'SF-CASTRO',     'SF-EMBARCADERO', 1, 'San Francisco', 'Chase Center event - need additional vehicles',                                   'medium',   'approved',  NULL),
  ('surge_deploy',    'LV-STRIP',      'LV-SPHERE',     5, 'Las Vegas',     'U2 residency final show - maximum demand expected',                               'critical', 'pending',   NULL),
  ('rebalance',       'LV-ARENA',      'LV-STRIP',      3, 'Las Vegas',     'Late night Strip demand after arena events',                                      'high',     'pending',   NULL),
  ('rebalance',       'SF-SOMA',       'SF-MISSION',     2, 'San Francisco', 'Weekend dinner rush in Mission',                                                  'medium',   'pending',   NULL),
  ('surge_deploy',    'LV-DOWNTOWN',   'LV-ARENA',      3, 'Las Vegas',     'Boxing match at T-Mobile Arena',                                                  'high',     'pending',   NULL),
  ('maintenance_pull','SF-EMBARCADERO','SF-SOMA',        1, 'San Francisco', 'ZX-045 tire pressure warning',                                                   'medium',   'pending',   NULL),
  ('rebalance',       'LV-SPHERE',     'LV-STRIP',      2, 'Las Vegas',     'Cancelled show - redistribute to Strip',                                          'low',      'dismissed', NOW() - INTERVAL '96 hours'),
  ('surge_deploy',    'SF-MISSION',    'SF-CASTRO',      1, 'San Francisco', 'False alarm - parade cancelled',                                                  'low',      'dismissed', NOW() - INTERVAL '224 hours'),
  ('rebalance',       'LV-DOWNTOWN',   'LV-CONVENTION',  3, 'Las Vegas',     'Convention postponed to next week',                                               'medium',   'dismissed', NOW() - INTERVAL '239 hours'),
  ('charge_dispatch', 'LV-ARENA',      'LV-DOWNTOWN',   2, 'Las Vegas',     'System error - vehicles already charged',                                         'low',      'failed',    NULL),
  ('rebalance',       'SF-SOMA',       'SF-EMBARCADERO', 3, 'San Francisco', 'Network timeout during execution',                                               'high',     'failed',    NULL)
ON CONFLICT DO NOTHING;

-- ============================================================
-- 2. surge_alerts (~20 rows)
-- ============================================================
INSERT INTO surge_alerts (zone_id, city, event_name, predicted_demand_score, current_supply, severity, status, recommended_action, resolved_at) VALUES
  ('LV-SPHERE',      'Las Vegas',     'Sphere: U2 Residency',        0.92, 4,  'critical', 'open',         'Deploy 6 vehicles from LV-DOWNTOWN and LV-CONVENTION to LV-SPHERE',              NULL),
  ('LV-ARENA',       'Las Vegas',     'VGK vs Edmonton Oilers',      0.85, 5,  'high',     'open',         'Deploy 4 vehicles from LV-STRIP to LV-ARENA',                                    NULL),
  ('LV-SPHERE',      'Las Vegas',     'Sphere: Postcard from Earth', 0.88, 3,  'critical', 'open',         'Deploy 5 vehicles from adjacent zones to LV-SPHERE',                             NULL),
  ('SF-EMBARCADERO', 'San Francisco', 'Warriors vs Lakers',          0.78, 4,  'high',     'open',         'Deploy 3 vehicles from SF-CASTRO and SF-MISSION',                                 NULL),
  ('LV-CONVENTION',  'Las Vegas',     'CES 2026 Opening Day',        0.72, 6,  'high',     'open',         'Stage 4 additional vehicles at LV-CONVENTION',                                    NULL),
  ('LV-STRIP',       'Las Vegas',     'New Year''s Eve',             0.95, 8,  'critical', 'open',         'Maximum deployment - all available vehicles to LV-STRIP',                         NULL),
  ('SF-SOMA',        'San Francisco', 'Dreamforce 2025',             0.68, 5,  'medium',   'acknowledged', 'Deploy 2 vehicles from SF-CASTRO',                                                NULL),
  ('LV-ARENA',       'Las Vegas',     'UFC 310 Main Event',          0.82, 6,  'high',     'acknowledged', 'Deploy 3 vehicles from LV-DOWNTOWN',                                              NULL),
  ('LV-SPHERE',      'Las Vegas',     'Sphere: Dead & Company',      0.90, 4,  'critical', 'acknowledged', 'Deploy 5 vehicles from LV-STRIP and LV-DOWNTOWN',                                 NULL),
  ('SF-EMBARCADERO', 'San Francisco', 'Chase Center Concert',        0.65, 5,  'medium',   'acknowledged', 'Deploy 2 vehicles from SF-MISSION',                                                NULL),
  ('LV-SPHERE',      'Las Vegas',     'Sphere: Eagles Residency',    0.87, 5,  'high',     'resolved',     'Deployed 4 vehicles - demand met successfully',                                    NOW() - INTERVAL '259 hours'),
  ('LV-ARENA',       'Las Vegas',     'VGK vs Calgary Flames',       0.75, 7,  'medium',   'resolved',     'Pre-positioned 3 vehicles - wait times within target',                             NOW() - INTERVAL '309 hours'),
  ('SF-SOMA',        'San Francisco', 'Google I/O Overflow',         0.62, 6,  'medium',   'resolved',     'Deployed 2 vehicles - resolved within 30 min',                                     NOW() - INTERVAL '14 hours'),
  ('LV-CONVENTION',  'Las Vegas',     'SEMA Show',                   0.70, 4,  'medium',   'resolved',     'Convention shuttle demand handled by existing fleet',                               NOW() - INTERVAL '288 hours'),
  ('LV-STRIP',       'Las Vegas',     'Friday Night Rush',           0.80, 10, 'high',     'resolved',     'Deployed 5 vehicles from LV-CONVENTION - wait times normalized',                   NOW() - INTERVAL '102 hours'),
  ('SF-MISSION',     'San Francisco', 'Dia de los Muertos Festival', 0.58, 4,  'medium',   'resolved',     'Demand lower than predicted - no action needed',                                   NOW() - INTERVAL '367 hours'),
  ('LV-DOWNTOWN',    'Las Vegas',     'Fremont Street Event',        0.55, 7,  'low',      'resolved',     'Adequate supply - monitored only',                                                 NOW() - INTERVAL '333 hours'),
  ('SF-CASTRO',      'San Francisco', 'Pride Week Pre-Events',       0.60, 3,  'medium',   'resolved',     'Deployed 1 vehicle from SF-SOMA',                                                  NOW() - INTERVAL '360 hours'),
  ('LV-ARENA',       'Las Vegas',     'Cancelled Concert',           0.45, 8,  'low',      'dismissed',    'Event cancelled - alert dismissed',                                                NOW() - INTERVAL '280 hours'),
  ('SF-SOMA',        'San Francisco', 'False Positive Detection',    0.42, 7,  'low',      'dismissed',    'Sensor anomaly - no actual demand spike',                                          NOW() - INTERVAL '215 hours')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 3. dispatch_overrides (~15 rows)
-- ============================================================
INSERT INTO dispatch_overrides (vehicle_id, from_zone, to_zone, city, reason, override_by, status) VALUES
  ('ZX-005', 'LV-STRIP',      'LV-SPHERE',     'Las Vegas',     'VIP customer pickup request at Sphere entrance',                   'fleet_manager',   'pending'),
  ('ZX-012', 'LV-ARENA',      'LV-DOWNTOWN',   'Las Vegas',     'Maintenance facility closest to downtown',                          'maintenance_tech','cancelled'),
  ('ZX-003', 'LV-DOWNTOWN',   'LV-STRIP',      'Las Vegas',     'High-priority airport transfer request',                            'dispatch_lead',   'pending'),
  ('ZX-018', 'LV-CONVENTION', 'LV-ARENA',      'Las Vegas',     'Arena VIP pre-positioning for celebrity event',                     'fleet_manager',   'executed'),
  ('ZX-022', 'LV-SPHERE',     'LV-CONVENTION', 'Las Vegas',     'Convention center executive shuttle',                               'dispatch_lead',   'cancelled'),
  ('ZX-035', 'SF-SOMA',       'SF-EMBARCADERO','San Francisco', 'Chase Center corporate event pickup',                              'fleet_manager',   'executed'),
  ('ZX-041', 'SF-MISSION',    'SF-SOMA',       'San Francisco', 'Moscone tech demo - showcase vehicle',                             'fleet_manager',   'pending'),
  ('ZX-038', 'SF-EMBARCADERO','SF-CASTRO',     'San Francisco', 'Medical appointment transport request',                            'dispatch_lead',   'executed'),
  ('ZX-033', 'SF-CASTRO',     'SF-SOMA',       'San Francisco', 'Morning corporate shuttle commitment',                             'operator',        'executed'),
  ('ZX-008', 'LV-STRIP',      'LV-ARENA',      'Las Vegas',     'Pre-game VIP transport',                                           'operator',        'executed'),
  ('ZX-015', 'LV-DOWNTOWN',   'LV-SPHERE',     'Las Vegas',     'Sphere show - wheelchair accessible vehicle needed',                'dispatch_lead',   'executed'),
  ('ZX-025', 'LV-ARENA',      'LV-STRIP',      'Las Vegas',     'Post-game hotel drop-off priority',                                 'operator',        'executed'),
  ('ZX-042', 'SF-SOMA',       'SF-MISSION',    'San Francisco', 'Restaurant reservation pickup commitment',                         'operator',        'executed'),
  ('ZX-010', 'LV-STRIP',      'LV-CONVENTION', 'Las Vegas',     'Override cancelled - vehicle reassigned',                           'fleet_manager',   'executed'),
  ('ZX-047', 'SF-EMBARCADERO','SF-CASTRO',     'San Francisco', 'Route cancelled - passenger no-show',                              'operator',        'executed')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 4. workflows (~40 rows)
-- Rows 0-14: rebalancing_request
-- Rows 15-29: surge_response
-- Rows 30-39: dispatch_override
-- ============================================================
INSERT INTO workflows (workflow_type, trigger_source, severity, summary, entity_type, entity_id, status, reasoning_chain, completed_at, headline, enriched_summary) VALUES
  -- Rebalancing requests (15)
  ('rebalancing_request', 'monitor', 'medium',   'Detected demand surge at LV-SPHERE. Sphere show ending at 10pm, predicted 2.8x demand multiplier. Current supply: 4 vehicles, recommended: 10. Initiating rebalance from LV-DOWNTOWN and LV-CONVENTION.',
   'zone', 'LV-SPHERE', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-SPHERE demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Detected demand surge at LV-SPHERE. Sphere show ending at 10pm, predicted 2.8x","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: LV-SPHERE',
   'Detected demand surge at LV-SPHERE. Sphere show ending at 10pm, predicted 2.8x demand multiplier. Current supply: 4 vehicles, recommended: 10. Initiating rebalance from LV-DOWNTOWN and LV-CONVENTION.'),

  ('rebalancing_request', 'monitor', 'high',     'VGK game night - T-Mobile Arena expects 18,000 attendees. Current zone supply: 5 vehicles, recommended: 8. Pulling vehicles from LV-STRIP and LV-CONVENTION.',
   'zone', 'LV-ARENA', 'dismissed',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-ARENA demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"VGK game night - T-Mobile Arena expects 18,000 attendees. Current zone supply: 5","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '501 hours', 'Fleet Rebalancing: LV-ARENA',
   'VGK game night - T-Mobile Arena expects 18,000 attendees. Current zone supply: 5 vehicles, recommended: 8. Pulling vehicles from LV-STRIP and LV-CONVENTION.'),

  ('rebalancing_request', 'chat',    'high',     'Weekend nightlife demand spike on the Strip. Historical pattern shows 3.2x base demand after 10pm. Need 12 vehicles, currently have 8.',
   'zone', 'LV-STRIP', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-STRIP demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Weekend nightlife demand spike on the Strip. Historical pattern shows 3.2x base d","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '20 hours', 'Fleet Rebalancing: LV-STRIP',
   'Weekend nightlife demand spike on the Strip. Historical pattern shows 3.2x base demand after 10pm. Need 12 vehicles, currently have 8.'),

  ('rebalancing_request', 'monitor', 'critical', 'Warriors home game at Chase Center. Predicted 2.5x demand for Embarcadero zone. Rebalancing 3 vehicles from SF-CASTRO.',
   'zone', 'SF-EMBARCADERO', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-EMBARCADERO demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Warriors home game at Chase Center. Predicted 2.5x demand for Embarcadero zone","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '115 hours', 'Fleet Rebalancing: SF-EMBARCADERO',
   'Warriors home game at Chase Center. Predicted 2.5x demand for Embarcadero zone. Rebalancing 3 vehicles from SF-CASTRO.'),

  ('rebalancing_request', 'chat',    'medium',   'Moscone Center tech conference. 15,000 attendees expected. Morning arrival surge predicted. Deploy 4 vehicles from SF-MISSION.',
   'zone', 'SF-SOMA', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-SOMA demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Moscone Center tech conference. 15,000 attendees expected. Morning arrival surge ","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: SF-SOMA',
   'Moscone Center tech conference. 15,000 attendees expected. Morning arrival surge predicted. Deploy 4 vehicles from SF-MISSION.'),

  ('rebalancing_request', 'monitor', 'medium',   'CES 2026 day 2. Convention center demand remains elevated. Maintaining enhanced vehicle staging.',
   'zone', 'LV-CONVENTION', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-CONVENTION demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"CES 2026 day 2. Convention center demand remains elevated. Maintaining enhanced","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '372 hours', 'Fleet Rebalancing: LV-CONVENTION',
   'CES 2026 day 2. Convention center demand remains elevated. Maintaining enhanced vehicle staging.'),

  ('rebalancing_request', 'chat',    'high',     'Double Sphere show today. Matinee at 2pm, evening at 8pm. Maximum demand expected between shows and after evening show.',
   'zone', 'LV-SPHERE', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-SPHERE demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Double Sphere show today. Matinee at 2pm, evening at 8pm. Maximum demand expect","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '315 hours', 'Fleet Rebalancing: LV-SPHERE',
   'Double Sphere show today. Matinee at 2pm, evening at 8pm. Maximum demand expected between shows and after evening show.'),

  ('rebalancing_request', 'chat',    'high',     'Friday evening dinner rush. Mission district restaurants generating 1.8x base demand. Rebalancing from SF-SOMA post-conference.',
   'zone', 'SF-MISSION', 'failed',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-MISSION demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Friday evening dinner rush. Mission district restaurants generating 1.8x base de","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '246 hours', 'Fleet Rebalancing: SF-MISSION',
   'Friday evening dinner rush. Mission district restaurants generating 1.8x base demand. Rebalancing from SF-SOMA post-conference.'),

  ('rebalancing_request', 'chat',    'high',     'Downtown Fremont Street Experience event. Moderate demand increase expected. Moving 2 vehicles from LV-CONVENTION.',
   'zone', 'LV-DOWNTOWN', 'in_progress',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-DOWNTOWN demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Downtown Fremont Street Experience event. Moderate demand increase expected. Mov","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: LV-DOWNTOWN',
   'Downtown Fremont Street Experience event. Moderate demand increase expected. Moving 2 vehicles from LV-CONVENTION.'),

  ('rebalancing_request', 'chat',    'medium',   'Ferry building farmers market Saturday. Predicted 1.5x morning demand. Pre-positioning 2 vehicles.',
   'zone', 'SF-EMBARCADERO', 'dismissed',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-EMBARCADERO demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Ferry building farmers market Saturday. Predicted 1.5x morning demand. Pre-posi","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '60 hours', 'Fleet Rebalancing: SF-EMBARCADERO',
   'Ferry building farmers market Saturday. Predicted 1.5x morning demand. Pre-positioning 2 vehicles.'),

  ('rebalancing_request', 'monitor', 'high',     'New Year''s Eve preparation. Maximum fleet deployment to LV-STRIP starting 6pm. All non-essential zones reduced to minimum.',
   'zone', 'LV-STRIP', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-STRIP demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"New Year''s Eve preparation. Maximum fleet deployment to LV-STRIP starting 6pm.","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: LV-STRIP',
   'New Year''s Eve preparation. Maximum fleet deployment to LV-STRIP starting 6pm. All non-essential zones reduced to minimum.'),

  ('rebalancing_request', 'monitor', 'medium',   'UFC fight night. T-Mobile Arena sold out at 20,000. High-value ride demand expected post-event.',
   'zone', 'LV-ARENA', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-ARENA demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"UFC fight night. T-Mobile Arena sold out at 20,000. High-value ride demand expec","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '247 hours', 'Fleet Rebalancing: LV-ARENA',
   'UFC fight night. T-Mobile Arena sold out at 20,000. High-value ride demand expected post-event.'),

  ('rebalancing_request', 'monitor', 'medium',   'Dreamforce closing ceremony. 30,000 attendees departing Moscone. Maximum SOMA deployment.',
   'zone', 'SF-SOMA', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-SOMA demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Dreamforce closing ceremony. 30,000 attendees departing Moscone. Maximum SOMA de","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: SF-SOMA',
   'Dreamforce closing ceremony. 30,000 attendees departing Moscone. Maximum SOMA deployment.'),

  ('rebalancing_request', 'monitor', 'high',     'U2 final residency show. Record ticket prices suggest high-value riders. Premium positioning requested.',
   'zone', 'LV-SPHERE', 'in_progress',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"LV-SPHERE demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"U2 final residency show. Record ticket prices suggest high-value riders. Premium","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NULL, 'Fleet Rebalancing: LV-SPHERE',
   'U2 final residency show. Record ticket prices suggest high-value riders. Premium positioning requested.'),

  ('rebalancing_request', 'monitor', 'high',     'Castro neighborhood festival. Moderate demand increase. Routing 1 vehicle from SF-SOMA.',
   'zone', 'SF-CASTRO', 'approved',
   '[{"step":1,"tool":"monitor","label":"Demand spike detected","output":"SF-CASTRO demand elevated","status":"completed"},{"step":2,"tool":"analyze","label":"Supply-demand analysis","output":"Castro neighborhood festival. Moderate demand increase. Routing 1 vehicle from S","status":"completed"},{"step":3,"tool":"action","label":"Rebalance initiated","output":"Fleet action created","status":"completed"}]',
   NOW() - INTERVAL '581 hours', 'Fleet Rebalancing: SF-CASTRO',
   'Castro neighborhood festival. Moderate demand increase. Routing 1 vehicle from SF-SOMA.'),

  -- Surge responses (15)
  ('surge_response', 'monitor', 'critical', 'Sphere show U2 Residency creating 3.2x demand surge. Deploying 6 additional vehicles from LV-DOWNTOWN (3) and LV-CONVENTION (3). ETA: 15 minutes.',
   'zone', 'LV-SPHERE', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-SPHERE demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '81 hours', 'Surge Response: LV-SPHERE',
   'Sphere show U2 Residency creating 3.2x demand surge. Deploying 6 additional vehicles from LV-DOWNTOWN (3) and LV-CONVENTION (3). ETA: 15 minutes.'),

  ('surge_response', 'monitor', 'high',     'VGK playoff game. 20,000 capacity sold out. Post-game surge expected at 10:30pm. Pre-deploying 5 vehicles.',
   'zone', 'LV-ARENA', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-ARENA demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '88 hours', 'Surge Response: LV-ARENA',
   'VGK playoff game. 20,000 capacity sold out. Post-game surge expected at 10:30pm. Pre-deploying 5 vehicles.'),

  ('surge_response', 'manual',  'critical', 'Chase Center Warriors game. 18,000 attendees. Deploying 4 vehicles from SF-CASTRO and SF-MISSION for post-game demand.',
   'zone', 'SF-EMBARCADERO', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"SF-EMBARCADERO demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '498 hours', 'Surge Response: SF-EMBARCADERO',
   'Chase Center Warriors game. 18,000 attendees. Deploying 4 vehicles from SF-CASTRO and SF-MISSION for post-game demand.'),

  ('surge_response', 'manual',  'high',     'NYE countdown surge. All available vehicles routing to LV-STRIP. 15 vehicles deployed from all other zones.',
   'zone', 'LV-STRIP', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-STRIP demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NULL, 'Surge Response: LV-STRIP',
   'NYE countdown surge. All available vehicles routing to LV-STRIP. 15 vehicles deployed from all other zones.'),

  ('surge_response', 'manual',  'high',     'Dreamforce keynote ending. 25,000 departing Moscone simultaneously. Maximum SOMA deployment with overflow to SF-EMBARCADERO.',
   'zone', 'SF-SOMA', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"SF-SOMA demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '71 hours', 'Surge Response: SF-SOMA',
   'Dreamforce keynote ending. 25,000 departing Moscone simultaneously. Maximum SOMA deployment with overflow to SF-EMBARCADERO.'),

  ('surge_response', 'manual',  'high',     'CES opening day. 50,000 registered attendees. Convention center zone at maximum capacity. Overflow staging at LV-DOWNTOWN.',
   'zone', 'LV-CONVENTION', 'in_progress',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-CONVENTION demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NULL, 'Surge Response: LV-CONVENTION',
   'CES opening day. 50,000 registered attendees. Convention center zone at maximum capacity. Overflow staging at LV-DOWNTOWN.'),

  ('surge_response', 'monitor', 'medium',   'Dead & Company Sphere residency. 18,000 capacity. Deploying 5 vehicles pre-show and 8 vehicles post-show.',
   'zone', 'LV-SPHERE', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-SPHERE demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '546 hours', 'Surge Response: LV-SPHERE',
   'Dead & Company Sphere residency. 18,000 capacity. Deploying 5 vehicles pre-show and 8 vehicles post-show.'),

  ('surge_response', 'monitor', 'critical', 'Boxing championship at T-Mobile Arena. Premium ride demand expected. VIP pre-positioning 3 vehicles.',
   'zone', 'LV-ARENA', 'in_progress',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-ARENA demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NULL, 'Surge Response: LV-ARENA',
   'Boxing championship at T-Mobile Arena. Premium ride demand expected. VIP pre-positioning 3 vehicles.'),

  ('surge_response', 'manual',  'high',     'Giants game at Oracle Park overflow. Embarcadero demand 2.1x. Deploying 2 vehicles from SF-CASTRO.',
   'zone', 'SF-EMBARCADERO', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"SF-EMBARCADERO demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '129 hours', 'Surge Response: SF-EMBARCADERO',
   'Giants game at Oracle Park overflow. Embarcadero demand 2.1x. Deploying 2 vehicles from SF-CASTRO.'),

  ('surge_response', 'manual',  'critical', 'Saturday night Strip surge. Historical pattern: 2.5x demand 10pm-2am. Deploying 8 vehicles from LV-CONVENTION and LV-DOWNTOWN.',
   'zone', 'LV-STRIP', 'in_progress',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-STRIP demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NULL, 'Surge Response: LV-STRIP',
   'Saturday night Strip surge. Historical pattern: 2.5x demand 10pm-2am. Deploying 8 vehicles from LV-CONVENTION and LV-DOWNTOWN.'),

  ('surge_response', 'monitor', 'high',     'Google I/O conference at Moscone. Day 2 keynote ending at 5pm. Preparing for departure surge.',
   'zone', 'SF-SOMA', 'dismissed',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"SF-SOMA demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '132 hours', 'Surge Response: SF-SOMA',
   'Google I/O conference at Moscone. Day 2 keynote ending at 5pm. Preparing for departure surge.'),

  ('surge_response', 'monitor', 'critical', 'Eagles Sphere residency. Concert ending at 11pm. Deploying 6 vehicles for post-show surge.',
   'zone', 'LV-SPHERE', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-SPHERE demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '676 hours', 'Surge Response: LV-SPHERE',
   'Eagles Sphere residency. Concert ending at 11pm. Deploying 6 vehicles for post-show surge.'),

  ('surge_response', 'monitor', 'critical', 'UFC main event. T-Mobile Arena. Late-night ride demand expected through 1am. Staging 4 vehicles.',
   'zone', 'LV-ARENA', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-ARENA demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '487 hours', 'Surge Response: LV-ARENA',
   'UFC main event. T-Mobile Arena. Late-night ride demand expected through 1am. Staging 4 vehicles.'),

  ('surge_response', 'monitor', 'high',     'Dia de los Muertos celebration. Mission district. Moderate demand increase 6pm-midnight.',
   'zone', 'SF-MISSION', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"SF-MISSION demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NULL, 'Surge Response: SF-MISSION',
   'Dia de los Muertos celebration. Mission district. Moderate demand increase 6pm-midnight.'),

  ('surge_response', 'manual',  'critical', 'Fremont Street holiday event. Downtown surge expected. Moving 3 vehicles from LV-CONVENTION.',
   'zone', 'LV-DOWNTOWN', 'approved',
   '[{"step":1,"tool":"monitor","label":"Surge detected","output":"LV-DOWNTOWN demand spike","status":"completed"},{"step":2,"tool":"analyze","label":"Event correlation","output":"Event-driven demand confirmed","status":"completed"},{"step":3,"tool":"action","label":"Vehicles deployed","output":"Surge response executed","status":"completed"}]',
   NOW() - INTERVAL '563 hours', 'Surge Response: LV-DOWNTOWN',
   'Fremont Street holiday event. Downtown surge expected. Moving 3 vehicles from LV-CONVENTION.'),

  -- Dispatch overrides (10)
  ('dispatch_override', 'manual', 'low',    'Manual override: VIP pickup at Sphere main entrance. ZX-005 rerouted from LV-STRIP to LV-SPHERE. Priority: immediate.',
   'vehicle', 'ZX-005', 'approved',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-005 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '170 hours', 'Dispatch Override: ZX-005',
   'Manual override: VIP pickup at Sphere main entrance. ZX-005 rerouted from LV-STRIP to LV-SPHERE. Priority: immediate.'),

  ('dispatch_override', 'chat',   'low',    'Maintenance override: ZX-012 pulled from service for sensor recalibration. Routed to downtown maintenance bay.',
   'vehicle', 'ZX-012', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-012 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NULL, 'Dispatch Override: ZX-012',
   'Maintenance override: ZX-012 pulled from service for sensor recalibration. Routed to downtown maintenance bay.'),

  ('dispatch_override', 'manual', 'high',   'Corporate event override: ZX-035 assigned to Chase Center VIP pickup. Removed from general dispatch pool.',
   'vehicle', 'ZX-035', 'approved',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-035 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '272 hours', 'Dispatch Override: ZX-035',
   'Corporate event override: ZX-035 assigned to Chase Center VIP pickup. Removed from general dispatch pool.'),

  ('dispatch_override', 'manual', 'medium', 'Celebrity transport: ZX-018 assigned to arena VIP entrance. Security protocol engaged.',
   'vehicle', 'ZX-018', 'dismissed',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-018 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '541 hours', 'Dispatch Override: ZX-018',
   'Celebrity transport: ZX-018 assigned to arena VIP entrance. Security protocol engaged.'),

  ('dispatch_override', 'chat',   'low',    'Demo vehicle: ZX-041 assigned to Moscone Center for technology showcase. Removed from ride pool.',
   'vehicle', 'ZX-041', 'approved',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-041 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '622 hours', 'Dispatch Override: ZX-041',
   'Demo vehicle: ZX-041 assigned to Moscone Center for technology showcase. Removed from ride pool.'),

  ('dispatch_override', 'chat',   'high',   'Airport priority: ZX-003 redirected for high-priority airport transfer from LV-DOWNTOWN.',
   'vehicle', 'ZX-003', 'dismissed',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-003 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '434 hours', 'Dispatch Override: ZX-003',
   'Airport priority: ZX-003 redirected for high-priority airport transfer from LV-DOWNTOWN.'),

  ('dispatch_override', 'manual', 'medium', 'Medical transport: ZX-038 assigned for medical appointment transport in SF-CASTRO. Accessibility mode enabled.',
   'vehicle', 'ZX-038', 'approved',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-038 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '217 hours', 'Dispatch Override: ZX-038',
   'Medical transport: ZX-038 assigned for medical appointment transport in SF-CASTRO. Accessibility mode enabled.'),

  ('dispatch_override', 'chat',   'medium', 'Executive shuttle: ZX-022 assigned to convention center executive transport loop.',
   'vehicle', 'ZX-022', 'pending_approval',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-022 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NULL, 'Dispatch Override: ZX-022',
   'Executive shuttle: ZX-022 assigned to convention center executive transport loop.'),

  ('dispatch_override', 'manual', 'medium', 'Accessibility override: ZX-015 assigned for wheelchair-accessible Sphere pickup.',
   'vehicle', 'ZX-015', 'failed',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-015 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '553 hours', 'Dispatch Override: ZX-015',
   'Accessibility override: ZX-015 assigned for wheelchair-accessible Sphere pickup.'),

  ('dispatch_override', 'manual', 'medium', 'Route override cancelled: ZX-047 passenger no-show at SF-EMBARCADERO. Returning to general pool.',
   'vehicle', 'ZX-047', 'approved',
   '[{"step":1,"tool":"monitor","label":"Override requested","output":"ZX-047 override","status":"completed"},{"step":2,"tool":"action","label":"Vehicle reassigned","output":"Dispatch updated","status":"completed"}]',
   NOW() - INTERVAL '707 hours', 'Dispatch Override: ZX-047',
   'Route override cancelled: ZX-047 passenger no-show at SF-EMBARCADERO. Returning to general pool.')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 5. agent_actions (~50 rows)
-- ============================================================
INSERT INTO agent_actions (action_type, severity, entity_type, entity_id, description, action_taken, status, created_at) VALUES
  ('demand_forecast',   'high',     'zone',    'LV-SPHERE',      'Generated 24h demand forecast for LV-SPHERE: peak demand score 0.92 at 10pm (Sphere show ending)',                                   'Forecast published to demand_forecasts table',    'executed',  NOW() - INTERVAL '137 hours'),
  ('demand_forecast',   'medium',   'zone',    'LV-ARENA',       'Generated 24h demand forecast for LV-ARENA: peak demand score 0.78 at 10:30pm (VGK game)',                                            'Forecast published',                               'dismissed', NOW() - INTERVAL '114 hours'),
  ('demand_forecast',   'medium',   'zone',    'SF-EMBARCADERO', 'Generated 24h demand forecast for SF-EMBARCADERO: peak demand score 0.72 at 10pm (Chase Center event)',                                 'Forecast published',                               'executed',  NOW() - INTERVAL '35 hours'),
  ('rebalance_trigger', 'high',     'zone',    'LV-SPHERE',      'Triggered rebalance: LV-SPHERE supply deficit detected. 4 vehicles available, 10 recommended.',                                       'Created fleet_action #1: rebalance from LV-DOWNTOWN', 'executed', NOW() - INTERVAL '108 hours'),
  ('rebalance_trigger', 'medium',   'zone',    'LV-STRIP',       'Triggered rebalance: LV-STRIP weekend demand pattern detected. Pre-positioning 5 vehicles.',                                          'Created fleet_action #2: rebalance from LV-CONVENTION', 'executed', NOW() - INTERVAL '46 hours'),
  ('rebalance_trigger', 'high',     'zone',    'SF-EMBARCADERO', 'Triggered rebalance: Warriors game demand surge imminent. Deploying 3 vehicles to SF-EMBARCADERO.',                                    'Created fleet_action #7',                          'pending',   NOW() - INTERVAL '71 hours'),
  ('surge_detection',   'critical', 'zone',    'LV-SPHERE',      'SURGE DETECTED: Sphere show demand 3.2x base. Current wait time 18 min, target 8 min.',                                               'Created surge_alert: critical severity',            'executed',  NOW() - INTERVAL '118 hours'),
  ('surge_detection',   'high',     'zone',    'LV-ARENA',       'Surge detected: VGK post-game demand 2.5x base at LV-ARENA. 12,000 fans departing.',                                                  'Created surge_alert: high severity',                'failed',    NOW() - INTERVAL '63 hours'),
  ('surge_detection',   'medium',   'zone',    'SF-SOMA',        'Moderate surge detected: Moscone conference ending. 1.8x demand in SF-SOMA.',                                                          'Created surge_alert: medium severity',              'executed',  NOW() - INTERVAL '19 hours'),
  ('surge_detection',   'critical', 'zone',    'LV-STRIP',       'NYE surge detected: LV-STRIP demand 4.0x base. All vehicles deploying.',                                                               'Created surge_alert: critical severity',            'executed',  NOW() - INTERVAL '113 hours'),
  ('battery_alert',     'medium',   'vehicle', 'ZX-008',         'ZX-008 battery at 22%. Scheduling charge rotation. Current zone: LV-STRIP.',                                                           'Dispatched to charging hub',                        'executed',  NOW() - INTERVAL '140 hours'),
  ('battery_alert',     'medium',   'vehicle', 'ZX-015',         'ZX-015 battery at 18%. Urgent charge needed. Removing from ride pool.',                                                                 'Dispatched to LV-DOWNTOWN charging hub',            'dismissed', NOW() - INTERVAL '25 hours'),
  ('battery_alert',     'low',      'vehicle', 'ZX-033',         'ZX-033 battery at 25%. Scheduling next available charge slot in SF-SOMA.',                                                              'Queued for charging',                               'pending',   NOW() - INTERVAL '12 hours'),
  ('battery_alert',     'medium',   'vehicle', 'ZX-042',         'ZX-042 battery at 20%. Rerouting to SF-MISSION charging station.',                                                                      'Dispatched to charging',                            'executed',  NOW() - INTERVAL '166 hours'),
  ('zone_optimization', 'medium',   'zone',    'LV-STRIP',       'Zone optimization: LV-STRIP has 12 vehicles, optimal is 10 at current demand. Redistributing 2.',                                      'Redistribution initiated',                          'executed',  NOW() - INTERVAL '138 hours'),
  ('zone_optimization', 'low',      'zone',    'SF-CASTRO',      'Zone optimization: SF-CASTRO over-supplied. 5 vehicles present, 3 optimal. Moving 2 to SF-SOMA.',                                      'Redistribution initiated',                          'executed',  NOW() - INTERVAL '3 hours'),
  ('zone_optimization', 'medium',   'zone',    'LV-DOWNTOWN',    'Zone optimization: LV-DOWNTOWN under-supplied for morning shift. Requesting 2 vehicles from LV-STRIP.',                                'Request created',                                   'executed',  NOW() - INTERVAL '23 hours'),
  ('demand_forecast',   'medium',   'zone',    'LV-CONVENTION',  'Generated weekly forecast for LV-CONVENTION: CES 2026 expected to drive 2.5x demand all week.',                                        'Published weekly forecast',                         'executed',  NOW() - INTERVAL '60 hours'),
  ('demand_forecast',   'low',      'zone',    'SF-CASTRO',      'Generated 24h forecast for SF-CASTRO: normal demand expected, no events.',                                                              'Forecast published',                                'executed',  NOW() - INTERVAL '42 hours'),
  ('demand_forecast',   'high',     'zone',    'LV-STRIP',       'Generated 24h forecast for LV-STRIP: NYE demand predicted at 4.0x base. Maximum deployment recommended.',                               'Published critical forecast',                       'executed',  NOW() - INTERVAL '104 hours'),
  ('rebalance_trigger', 'critical', 'zone',    'LV-SPHERE',      'Emergency rebalance: Sphere show sold out, current supply 3 vehicles, need 10. Wait time 22 min.',                                     'Created priority fleet_action',                     'dismissed', NOW() - INTERVAL '124 hours'),
  ('surge_detection',   'high',     'zone',    'LV-CONVENTION',  'Surge detected: CES 2026 registration overflow. LV-CONVENTION demand 2.2x base.',                                                      'Created surge_alert',                               'executed',  NOW() - INTERVAL '123 hours'),
  ('battery_alert',     'high',     'vehicle', 'ZX-023',         'ZX-023 battery critical at 12%. Emergency pull from LV-ARENA ride pool.',                                                               'Emergency dispatch to charging',                    'failed',    NOW() - INTERVAL '54 hours'),
  ('zone_optimization', 'low',      'zone',    'SF-EMBARCADERO', 'Zone optimization: SF-EMBARCADERO balanced at 7 vehicles. No action needed.',                                                           'Monitoring continued',                              'executed',  NOW() - INTERVAL '102 hours'),
  ('demand_forecast',   'medium',   'zone',    'SF-EMBARCADERO', 'Generated 48h forecast for SF-EMBARCADERO: Warriors double-header weekend. Elevated demand Sat-Sun.',                                   'Published multi-day forecast',                      'executed',  NOW() - INTERVAL '15 hours'),
  ('rebalance_trigger', 'medium',   'zone',    'SF-SOMA',        'Pre-emptive rebalance: Dreamforce Day 1 starting. Moving 3 vehicles to SF-SOMA from SF-CASTRO.',                                        'Created fleet_action',                              'pending',   NOW() - INTERVAL '42 hours'),
  ('surge_detection',   'medium',   'zone',    'SF-MISSION',     'Moderate surge: Friday dinner rush in Mission district. 1.5x demand detected.',                                                        'Monitoring - no action needed',                     'executed',  NOW() - INTERVAL '97 hours'),
  ('battery_alert',     'low',      'vehicle', 'ZX-048',         'ZX-048 battery at 28%. Next charge slot available in 45 minutes.',                                                                      'Scheduled charging',                                'executed',  NOW() - INTERVAL '0 hours'),
  ('zone_optimization', 'high',     'zone',    'LV-SPHERE',      'Post-show zone optimization: LV-SPHERE has 10 vehicles, demand dropping. Redistributing 5 vehicles.',                                   'Redistribution fleet_action created',               'executed',  NOW() - INTERVAL '99 hours'),
  ('demand_forecast',   'high',     'zone',    'LV-ARENA',       'Emergency forecast update: UFC main card extended. LV-ARENA demand window extended to 1:30am.',                                         'Updated forecast',                                  'pending',   NOW() - INTERVAL '67 hours'),
  ('rebalance_trigger', 'medium',   'zone',    'LV-CONVENTION',  'Convention day 3 rebalance: Reduced attendance expected. Pulling 2 vehicles to LV-STRIP.',                                              'Created fleet_action',                              'pending',   NOW() - INTERVAL '116 hours'),
  ('surge_detection',   'high',     'zone',    'SF-EMBARCADERO', 'Concert surge at Chase Center. 17,000 attendees. Post-concert demand at 11pm.',                                                        'Created surge_alert',                               'executed',  NOW() - INTERVAL '73 hours'),
  ('battery_alert',     'medium',   'vehicle', 'ZX-019',         'ZX-019 battery degradation detected. Charge efficiency 82%. Scheduling diagnostics.',                                                   'Maintenance ticket created',                        'pending',   NOW() - INTERVAL '108 hours'),
  ('zone_optimization', 'medium',   'zone',    'LV-ARENA',       'Pre-game zone prep: Moving vehicles to optimal positions around T-Mobile Arena perimeter.',                                             '3 vehicles repositioned',                           'executed',  NOW() - INTERVAL '142 hours'),
  ('demand_forecast',   'low',      'zone',    'LV-DOWNTOWN',    'Quiet Tuesday forecast for LV-DOWNTOWN. Base demand only. No events.',                                                                  'Published routine forecast',                        'executed',  NOW() - INTERVAL '124 hours'),
  ('rebalance_trigger', 'high',     'zone',    'LV-STRIP',       'Friday night Strip rebalance. Historical 2.8x pattern confirmed by real-time data.',                                                    'Created fleet_action for 5 vehicles',               'pending',   NOW() - INTERVAL '39 hours'),
  ('surge_detection',   'medium',   'zone',    'LV-DOWNTOWN',    'Fremont Street Experience event surge. 1.6x demand detected in LV-DOWNTOWN.',                                                          'Monitoring - threshold not met for alert',           'pending',   NOW() - INTERVAL '48 hours'),
  ('battery_alert',     'low',      'vehicle', 'ZX-036',         'ZX-036 scheduled maintenance charging complete. Battery at 95%. Returning to SF-SOMA pool.',                                            'Vehicle returned to service',                       'executed',  NOW() - INTERVAL '75 hours'),
  ('zone_optimization', 'medium',   'zone',    'SF-SOMA',        'Morning commute optimization: SF-SOMA demand rising. Routing 2 idle vehicles from SF-CASTRO.',                                          'Redistribution complete',                           'executed',  NOW() - INTERVAL '55 hours'),
  ('demand_forecast',   'medium',   'zone',    'SF-SOMA',        'Generated commute forecast: SF-SOMA peak demand 8-9am, secondary peak 5-6pm.',                                                         'Published commute forecast',                        'dismissed', NOW() - INTERVAL '14 hours'),
  ('rebalance_trigger', 'low',      'zone',    'SF-CASTRO',      'Light demand in SF-CASTRO. Reducing to minimum 2 vehicles. Excess to SF-MISSION.',                                                      'Created fleet_action',                              'failed',    NOW() - INTERVAL '148 hours'),
  ('surge_detection',   'critical', 'zone',    'LV-SPHERE',      'Double show surge: Sphere matinee ending + evening show arriving simultaneously. Maximum alert.',                                        'Created critical surge_alert',                      'executed',  NOW() - INTERVAL '138 hours'),
  ('battery_alert',     'medium',   'vehicle', 'ZX-027',         'ZX-027 showing unusual power consumption. 15% higher than fleet average. Monitoring.',                                                  'Added to watchlist',                                'dismissed', NOW() - INTERVAL '15 hours'),
  ('zone_optimization', 'low',      'zone',    'LV-CONVENTION',  'Convention center quiet period. Reducing to 3 vehicles. Excess to LV-STRIP for nightlife.',                                             'Redistribution initiated',                          'executed',  NOW() - INTERVAL '80 hours'),
  ('demand_forecast',   'high',     'zone',    'LV-SPHERE',      'Sphere double-show forecast: Peak demand 0.95 at 11pm. Highest forecast this month.',                                                   'Published critical forecast',                       'executed',  NOW() - INTERVAL '14 hours'),
  ('rebalance_trigger', 'medium',   'zone',    'SF-EMBARCADERO', 'Weekend harbor cruise traffic. Embarcadero demand 1.4x. Minor rebalance from SF-CASTRO.',                                               'Created fleet_action',                              'failed',    NOW() - INTERVAL '12 hours'),
  ('surge_detection',   'low',      'zone',    'SF-CASTRO',      'Minor demand increase in SF-CASTRO. Below alert threshold. Continued monitoring.',                                                       'No action taken',                                   'failed',    NOW() - INTERVAL '149 hours'),
  ('battery_alert',     'high',     'vehicle', 'ZX-011',         'ZX-011 rapid battery drain. 40% to 15% in 2 hours. Possible hardware issue. Emergency pull.',                                            'Emergency maintenance dispatch',                    'executed',  NOW() - INTERVAL '122 hours'),
  ('zone_optimization', 'medium',   'zone',    'LV-STRIP',       'Late night optimization: Redistributing post-midnight vehicles. 8 vehicles to staging, 4 to charging.',                                  '12 vehicle moves initiated',                        'pending',   NOW() - INTERVAL '128 hours'),
  ('demand_forecast',   'medium',   'zone',    'LV-ARENA',       'Next week forecast: 3 VGK home games + 1 concert. Elevated demand Mon/Wed/Sat.',                                                        'Published weekly forecast',                         'pending',   NOW() - INTERVAL '135 hours')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 6. notes (~30 rows)
-- ============================================================
INSERT INTO notes (entity_type, entity_id, note_text, author) VALUES
  ('vehicle', 'ZX-015',         'ZX-015 showing intermittent sensor readings in rain conditions. Scheduled for diagnostic.',                                                    'maintenance_tech'),
  ('vehicle', 'ZX-008',         'ZX-008 battery degradation tracking: 92% health, down from 95% last month. Within normal range.',                                              'maintenance_tech'),
  ('vehicle', 'ZX-003',         'ZX-003 consistently highest-rated vehicle in passenger surveys. Consider for VIP assignments.',                                                 'fleet_manager'),
  ('vehicle', 'ZX-023',         'ZX-023 had emergency battery pull on 2/15. Root cause: software bug in charge management. Patched.',                                           'maintenance_tech'),
  ('vehicle', 'ZX-041',         'ZX-041 designated as demo vehicle for Moscone Center tech showcases. Keep in pristine condition.',                                              'fleet_manager'),
  ('vehicle', 'ZX-012',         'ZX-012 sensor recalibration completed. All systems nominal. Returned to active duty.',                                                          'maintenance_tech'),
  ('vehicle', 'ZX-035',         'ZX-035 assigned to corporate events rotation for Chase Center. Premium interior cleaning weekly.',                                              'fleet_manager'),
  ('vehicle', 'ZX-019',         'ZX-019 charging efficiency at 82%. Below fleet average of 91%. Hardware inspection scheduled.',                                                 'ai_agent'),
  ('vehicle', 'ZX-027',         'ZX-027 power consumption anomaly detected. 15% above fleet average. Under observation for 48h.',                                               'ai_agent'),
  ('vehicle', 'ZX-011',         'ZX-011 emergency maintenance: rapid battery drain identified as faulty thermal management module. Replaced.',                                   'maintenance_tech'),
  ('zone',    'LV-SPHERE',      'LV-SPHERE zone: Consider permanent staging area for post-show demand. Current ad-hoc staging causes 5-min delays.',                            'fleet_manager'),
  ('zone',    'LV-STRIP',       'LV-STRIP Friday/Saturday pattern: demand consistently 2.5-3x base after 10pm. Pre-positioning by 9:30pm recommended.',                         'ai_agent'),
  ('zone',    'LV-ARENA',       'LV-ARENA: T-Mobile Arena events highly predictable from schedule. Auto-deployment working well.',                                               'operator'),
  ('zone',    'LV-CONVENTION',  'LV-CONVENTION: CES week requires special planning. Convention goers prefer pickup at LVCC loop road, not main entrance.',                       'operator'),
  ('zone',    'SF-SOMA',        'SF-SOMA: Moscone Center events cause parking congestion. Recommend pickup zone on Howard St, not 4th St.',                                      'operator'),
  ('zone',    'SF-EMBARCADERO', 'SF-EMBARCADERO: Chase Center post-game traffic blocks Terry Francois Blvd. Use alternative pickup on 3rd St.',                                  'operator'),
  ('zone',    'LV-DOWNTOWN',    'LV-DOWNTOWN charging hub utilization at 78%. Consider adding 2 charging slots for peak demand periods.',                                        'fleet_manager'),
  ('zone',    'SF-MISSION',     'SF-MISSION: Weekend dinner rush 7-9pm. Valencia St restaurants generate consistent demand. Auto-detection working.',                             'ai_agent'),
  ('zone',    'SF-CASTRO',      'SF-CASTRO: Lowest demand zone in SF. Consider reducing minimum vehicle allocation from 4 to 3.',                                                'ai_agent'),
  ('event',   'VGK-2025',       'VGK games: Average post-game demand multiplier 2.3x. Deploy vehicles 30 min before game end for optimal positioning.',                          'ai_agent'),
  ('event',   'SPHERE-2025',    'Sphere shows: Demand varies by artist. U2/Eagles: 3.5x, Postcard from Earth: 2.0x, Dead & Company: 3.0x.',                                     'fleet_manager'),
  ('event',   'CES-2026',       'CES 2026: Week-long elevated demand. Day 1 highest (50K attendees), tapering to Day 4 (25K). Plan daily rebalancing.',                          'fleet_manager'),
  ('event',   'NYE-2025',       'NYE 2025: Record demand expected on Strip. All vehicles deployed. Consider temporary additional capacity.',                                      'fleet_manager'),
  ('event',   'WARRIORS-2025',  'Warriors home games: Chase Center capacity 18,064. Post-game surge lasts 45 min. Pre-position by 4th quarter.',                                 'operator'),
  ('event',   'DREAMFORCE-2025','Dreamforce: 3-day event at Moscone. Keynote days (Day 1, 3) have 2x demand of regular sessions (Day 2).',                                       'ai_agent'),
  ('event',   'UFC-2025',       'UFC events at T-Mobile Arena: Fights run late (past midnight). Need vehicles staged until 1:30am minimum.',                                      'operator'),
  ('vehicle', 'ZX-050',         'ZX-050 newest vehicle in fleet. Commissioned 2026-01-15. All systems nominal. Assigned to SF-EMBARCADERO.',                                     'fleet_manager'),
  ('vehicle', 'ZX-001',         'ZX-001 fleet veteran. Commissioned 2025-08-10. 12,000+ rides completed. Highest mileage in fleet.',                                             'fleet_manager'),
  ('zone',    'LV-SPHERE',      'LV-SPHERE staging optimization result: Moving staging from parking lot B to valet loop reduced avg wait by 3.2 min.',                            'ai_agent'),
  ('zone',    'LV-STRIP',       'LV-STRIP: Wynn/Encore corridor generates 22% of Strip zone demand. Consider micro-zone staging.',                                               'ai_agent')
ON CONFLICT DO NOTHING;

COMMIT;

-- Verify seeded data
SELECT 'fleet_actions' AS table_name, COUNT(*) AS row_count FROM fleet_actions
UNION ALL SELECT 'surge_alerts', COUNT(*) FROM surge_alerts
UNION ALL SELECT 'dispatch_overrides', COUNT(*) FROM dispatch_overrides
UNION ALL SELECT 'workflows', COUNT(*) FROM workflows
UNION ALL SELECT 'agent_actions', COUNT(*) FROM agent_actions
UNION ALL SELECT 'notes', COUNT(*) FROM notes
ORDER BY table_name;

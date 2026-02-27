-- Zoox Fleet Intelligence — Domain-specific Lakebase tables
-- Apply this AFTER core_schema.sql.

-- ============================================================
-- Table: fleet_actions
-- Rebalancing commands and fleet movement orders
-- ============================================================
CREATE TABLE IF NOT EXISTS fleet_actions (
    action_id       SERIAL PRIMARY KEY,
    action_type     VARCHAR(50) NOT NULL
                    CHECK (action_type IN ('rebalance', 'surge_deploy', 'recall', 'charge_dispatch', 'maintenance_pull')),
    from_zone       VARCHAR(50) NOT NULL,
    to_zone         VARCHAR(50) NOT NULL,
    vehicle_count   INTEGER NOT NULL DEFAULT 1,
    city            VARCHAR(50) NOT NULL,
    reason          TEXT,
    priority        VARCHAR(20) NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status          VARCHAR(30) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'executed', 'dismissed', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_fleet_actions_status ON fleet_actions(status);
CREATE INDEX IF NOT EXISTS idx_fleet_actions_city ON fleet_actions(city);

-- ============================================================
-- Table: surge_alerts
-- Demand surge alerts from event prediction
-- ============================================================
CREATE TABLE IF NOT EXISTS surge_alerts (
    alert_id                SERIAL PRIMARY KEY,
    zone_id                 VARCHAR(50) NOT NULL,
    city                    VARCHAR(50) NOT NULL,
    event_name              VARCHAR(200),
    predicted_demand_score  NUMERIC(5, 2) NOT NULL DEFAULT 0.0,
    current_supply          INTEGER NOT NULL DEFAULT 0,
    severity                VARCHAR(20) NOT NULL DEFAULT 'medium'
                            CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status                  VARCHAR(20) NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'acknowledged', 'resolved', 'dismissed')),
    recommended_action      TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_surge_alerts_status ON surge_alerts(status);
CREATE INDEX IF NOT EXISTS idx_surge_alerts_zone ON surge_alerts(zone_id);

-- ============================================================
-- Table: dispatch_overrides
-- Manual dispatch overrides by fleet operators
-- ============================================================
CREATE TABLE IF NOT EXISTS dispatch_overrides (
    override_id     SERIAL PRIMARY KEY,
    vehicle_id      VARCHAR(20) NOT NULL,
    from_zone       VARCHAR(50) NOT NULL,
    to_zone         VARCHAR(50) NOT NULL,
    city            VARCHAR(50) NOT NULL,
    reason          TEXT,
    override_by     VARCHAR(100) NOT NULL DEFAULT 'operator',
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'executed', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_overrides_status ON dispatch_overrides(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_overrides_vehicle ON dispatch_overrides(vehicle_id);

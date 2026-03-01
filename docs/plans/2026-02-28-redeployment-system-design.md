# Redeployment System Design

**Date:** 2026-02-28
**Status:** Approved
**Problem:** Moving a demo to a new Databricks workspace requires ~15 manual steps across 6+ APIs. When FEVM workspaces break (IAM roles die, SPs get purged), rebuilding is a multi-hour ordeal.

## Goal

A reusable deployer module in the vibe-demo-accelerator scaffold that makes any demo redeployable to any workspace with a single command.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interface | CLI + vibe skill | Core Python module shared by both; max flexibility |
| MCP server scope | Per-demo only | Assumes lakebase-mcp-server is pre-deployed in target workspace |
| Config management | Auto-update in place | Deployer writes discovered IDs back to demo-config.yaml and app.yaml |
| Data generation | SQL-only via Statement API | No notebook/cluster dependency; runs from local CLI |
| Architecture | Phase-based with state tracking | Resumable, modular, skip completed steps on re-run |

## File Structure

```
deploy/
  __main__.py              CLI entry point
  deployer.py              Orchestrator: reads config, runs phases, manages state
  config.py                Reads/writes demo-config.yaml + app/app.yaml
  state.py                 deploy-state.json management
  databricks_api.py        Thin wrapper: auth, SQL statements, REST calls
  phases/
    __init__.py
    phase_1_delta_lake.py  Create catalog, schema, generate tables via SQL
    phase_2_lakebase.py    Create/reuse instance, database, apply schemas, seed
    phase_3_ai_layer.py    Genie Space, MAS, UC HTTP connection
    phase_4_app.py         Deploy app, register resources, redeploy
    phase_5_permissions.py All permission grants to the new SP
  sql/
    create_zones.sql       Pure SQL data generation (per-demo)
    create_vehicles.sql
    create_events.sql
    create_rides.sql
    create_demand_forecasts.sql
```

## Interactive Setup

Before any phase runs, the deployer interactively gathers workspace-specific info:

1. **Workspace URL** (e.g., `https://my-workspace.cloud.databricks.com`)
2. **CLI profile** -- use existing or create new via `databricks auth login`
3. **Catalog** -- auto-discover from workspace, let user pick or enter
4. **Schema name** -- default from demo-config.yaml, user can override
5. **SQL warehouse** -- auto-discover available warehouses, pick serverless
6. **Lakebase** -- reuse existing instance or create new, database name

All answers written to `demo-config.yaml` infrastructure section before phases run.

## State Tracking

`deploy-state.json` (gitignored, repo root) records what was created:

```json
{
  "workspace_url": "https://...",
  "profile": "new-ws",
  "started_at": "2026-03-01T10:00:00Z",
  "phases": {
    "delta_lake": {
      "status": "completed",
      "catalog": "...",
      "schema": "...",
      "warehouse_id": "...",
      "tables_created": ["zones", "vehicles", "events", "rides", "demand_forecasts"]
    },
    "lakebase": {
      "status": "completed",
      "instance_name": "...",
      "database_name": "...",
      "core_schema_applied": true,
      "domain_schema_applied": true,
      "seeded": true
    },
    "ai_layer": {
      "status": "completed|failed|pending",
      "genie_space_id": "...",
      "mas_tile_id": "...",
      "mas_full_tile_id": "...",
      "uc_connection_name": "..."
    },
    "app": {
      "status": "completed|failed|pending",
      "app_name": "...",
      "sp_client_id": "...",
      "app_url": "..."
    },
    "permissions": {
      "status": "completed|failed|pending"
    }
  }
}
```

**Resumability rules:**
- `completed` phases skipped on re-run
- `failed` phases restart from last successful sub-step
- `pending` phases run normally
- `--force` resets all to pending (full rebuild)
- `--phase=X` runs only that phase (checks dependencies)

**Config writeback:** After each phase, deployer updates:
- `demo-config.yaml` -- infrastructure section
- `app/app.yaml` -- env vars and resources
- `agent_bricks/mas_config.json` -- agent IDs
- `genie_spaces/config.json` -- warehouse ID and table names

## Phase Details

### Phase 1: Delta Lake

1. Create schema: `CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}`
2. Execute each SQL file in `deploy/sql/` via Statement Execution API
3. Verify row counts for each table

SQL files use pure Databricks SQL -- SEQUENCE, EXPLODE, hash functions, date arithmetic. No Python, no notebooks, no clusters.

### Phase 2: Lakebase

1. Check if instance exists; create if not (`CU_1`), poll until `AVAILABLE`
2. Check if database exists; create if not
3. Apply `lakebase/core_schema.sql` via `databricks psql`
4. Apply `lakebase/domain_schema.sql` via `databricks psql`
5. Seed operational data via `databricks psql` (converted from Python to SQL)

### Phase 3: AI Layer

1. **Genie Space:** POST blank -> PATCH title -> PATCH tables (sorted, serialized_space) -> PATCH instructions -> verify
2. **MAS Supervisor:** POST with simple agents -> PATCH to add MCP agents -> discover tile ID from serving endpoints
3. **UC HTTP Connection:** Create pointing to shared MCP server at `/db/{database}/mcp/`

### Phase 4: App Deployment

1. `databricks apps create {name}` (skip if exists)
2. Set user API scopes (serving.serving-endpoints, sql)
3. Sync code + deploy
4. Register resources (warehouse, MAS endpoint, database)
5. Redeploy to inject PGHOST/PGPORT/PGDATABASE/PGUSER

### Phase 5: Permissions

1. Get app SP client ID from `databricks apps get`
2. Grant USE_CATALOG + USE_SCHEMA + SELECT on Delta Lake tables
3. Grant CAN_QUERY on MAS serving endpoint (via UUID)
4. Grant CAN_RUN on Genie Space
5. Grant ALL on Lakebase tables to app SP
6. Verify: health endpoint returns all checks passing

## CLI Interface

```bash
python -m deploy                              # Full interactive deploy
python -m deploy --profile=X                  # Deploy to existing profile
python -m deploy --profile=X --resume         # Resume from failure
python -m deploy --profile=X --phase=lakebase # Single phase
python -m deploy --profile=X --force          # Full rebuild
python -m deploy --status                     # Show current state
```

## Vibe Skill Interface

`/deploy-demo` skill calls the same deployer module:
1. Reads demo-config.yaml
2. Asks for workspace URL + profile via AskUserQuestion
3. Auto-discovers warehouse and catalog
4. Runs all phases with progress output
5. Reports final app URL

## What Lives Where

**In scaffold (reusable):** `deploy/` module, phase logic, state management, vibe skill
**Per-demo (generated by vibe):** `deploy/sql/*.sql` files, schema files, demo-config.yaml

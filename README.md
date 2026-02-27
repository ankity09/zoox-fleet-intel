# Zoox Fleet Intelligence Platform

Databricks demo: event-driven demand prediction, dynamic fleet rebalancing, ride operations analytics, and an AI fleet ops assistant for Zoox's autonomous ride-hail fleet.

**Stack:** FastAPI + single-file HTML/JS frontend, deployed as a Databricks App.
**Data:** Delta Lake (analytics) + Lakebase/PostgreSQL (OLTP) + Genie Space (NL queries) + MAS Agent Bricks (AI chat).

## Live Demo

- **App:** https://zoox-fleet-intel-7474648424393858.aws.databricksapps.com
- **Workspace:** https://fe-sandbox-serverless-simplot-v1.cloud.databricks.com

## Redeploying to a Fresh Workspace

If the original workspace has expired or you want to run this in your own environment, follow these steps.

### Clone the Repo

```bash
git clone --recurse-submodules https://github.com/ankit-yadav_data/zoox-demo.git
cd zoox-demo
```

### Prerequisites

- Databricks CLI installed (`brew install databricks/tap/databricks`)
- `gh` CLI or git configured
- Access to an FEVM workspace (or any serverless-enabled workspace)

### Step 1: Create a New Workspace

```bash
# Option A: Use vibe's FEVM skill
# /databricks-fe-vm-workspace-deployment → Template 3 (Serverless), AWS, name: zoox-demo

# Option B: Manual FEVM request
# Request at go/fevm, choose serverless template
```

### Step 2: Authenticate CLI

```bash
databricks auth login https://fe-sandbox-serverless-<your-name>.cloud.databricks.com --profile=<your-profile>
databricks current-user me --profile=<your-profile>
```

### Step 3: Update Config Values

You need to update these values across the project to match your new workspace:

| Value | Where to find it | Files to update |
|-------|-----------------|-----------------|
| **Catalog** | Auto-created: `serverless_<name_underscored>_catalog` | `app/app.yaml`, `notebooks/01_setup_schema.sql`, `notebooks/02_generate_data.py`, `genie_spaces/config.json`, `CLAUDE.md` |
| **Schema** | Keep `zoox_fleet_intel` or rename | Same as above |
| **SQL Warehouse ID** | Workspace UI → SQL Warehouses → copy ID | `app/app.yaml`, `CLAUDE.md` |
| **CLI Profile** | Whatever you used in Step 2 | `.mcp.json`, `CLAUDE.md` |

### Step 4: Create Delta Lake Tables

Run notebooks in order from the workspace UI (import as notebooks):

```bash
# 1. Create schema
# Import notebooks/01_setup_schema.sql → Run All

# 2. Generate synthetic data (~50 vehicles, 180 days of rides, events, forecasts)
# Import notebooks/02_generate_data.py → Run All
```

### Step 5: Set Up Lakebase

```bash
PROFILE=<your-profile>
INSTANCE=<pick-a-name>  # use hyphens, e.g. zoox-fleet-db
DATABASE=zoox_fleet_intel

# Create instance (~6 min)
databricks database create-database-instance $INSTANCE --capacity CU_1 --profile=$PROFILE

# Poll until AVAILABLE (not RUNNING)
databricks database get-database-instance $INSTANCE --profile=$PROFILE -o json | jq '.state'

# Create database
databricks psql $INSTANCE --profile=$PROFILE -- -c "CREATE DATABASE $DATABASE;"

# Apply schemas
databricks psql $INSTANCE --profile=$PROFILE -- -d $DATABASE -f lakebase/core_schema.sql
databricks psql $INSTANCE --profile=$PROFILE -- -d $DATABASE -f lakebase/domain_schema.sql

# Seed data
databricks psql $INSTANCE --profile=$PROFILE -- -d $DATABASE -f notebooks/03_seed_lakebase.py
# Or use: python notebooks/03_seed_lakebase.py (with local psycopg2 + generate-database-credential)
```

### Step 6: Create Genie Space

```bash
PROFILE=<your-profile>
CATALOG=<your-catalog>
SCHEMA=zoox_fleet_intel
WH_ID=<your-warehouse-id>

# Create blank space
databricks api post /api/2.0/genie/spaces --json "{
  \"serialized_space\": \"{\\\"version\\\": 2}\",
  \"warehouse_id\": \"$WH_ID\"
}" --profile=$PROFILE
# Save the space_id from response

SPACE_ID=<from-above>

# Set title
databricks api patch /api/2.0/genie/spaces/$SPACE_ID --json '{
  "title": "Zoox Fleet Data Space",
  "description": "Query fleet operations data — vehicles, rides, events, zones, demand forecasts"
}' --profile=$PROFILE

# Attach tables (MUST be sorted alphabetically)
databricks api patch /api/2.0/genie/spaces/$SPACE_ID --json "{
  \"serialized_space\": \"{\\\"version\\\":2,\\\"data_sources\\\":{\\\"tables\\\":[{\\\"identifier\\\":\\\"$CATALOG.$SCHEMA.demand_forecasts\\\"},{\\\"identifier\\\":\\\"$CATALOG.$SCHEMA.events\\\"},{\\\"identifier\\\":\\\"$CATALOG.$SCHEMA.rides\\\"},{\\\"identifier\\\":\\\"$CATALOG.$SCHEMA.vehicles\\\"},{\\\"identifier\\\":\\\"$CATALOG.$SCHEMA.zones\\\"}]}}\"
}" --profile=$PROFILE

# Grant access
databricks api patch /api/2.0/permissions/genie/$SPACE_ID --json '{
  "access_control_list": [{"group_name": "users", "permission_level": "CAN_RUN"}]
}' --profile=$PROFILE
```

Update `GENIE_SPACE_ID` in `app/app.yaml`.

### Step 7: Create MAS (Multi-Agent Supervisor)

```bash
# Create MAS with genie agent first (POST can't include external-mcp-server)
databricks api post /api/2.0/multi-agent-supervisors --json @agent_bricks/mas_config.json --profile=$PROFILE

# Find the tile ID
databricks api get /api/2.0/serving-endpoints --profile=$PROFILE | \
  jq '.endpoints[] | select(.name | startswith("mas-")) | .tile_endpoint_metadata.tile_id'
```

Update `MAS_TILE_ID` (first 8 chars) in `app/app.yaml`.

### Step 8: Deploy the App

```bash
PROFILE=<your-profile>
APP_NAME=zoox-fleet-intel
YOUR_EMAIL=<your-databricks-email>

# Sync code to workspace
databricks sync ./app /Workspace/Users/$YOUR_EMAIL/zoox-fleet-intel/app --profile=$PROFILE --watch=false

# Create app
databricks apps create $APP_NAME --profile=$PROFILE

# Deploy
databricks apps deploy $APP_NAME --source-code-path /Workspace/Users/$YOUR_EMAIL/zoox-fleet-intel/app --profile=$PROFILE

# Register resources (CRITICAL — app.yaml resources are NOT auto-registered)
databricks apps update $APP_NAME --json '{
  "resources": [
    {"name": "sql-warehouse", "sql_warehouse": {"id": "<warehouse-id>", "permission": "CAN_USE"}},
    {"name": "mas-endpoint", "serving_endpoint": {"name": "mas-<tile-8-chars>-endpoint", "permission": "CAN_QUERY"}},
    {"name": "database", "database": {"instance_name": "<instance>", "database_name": "zoox_fleet_intel", "permission": "CAN_CONNECT_AND_CREATE"}}
  ]
}' --profile=$PROFILE

# Redeploy (injects PGHOST/PGPORT/PGDATABASE/PGUSER env vars)
databricks apps deploy $APP_NAME --source-code-path /Workspace/Users/$YOUR_EMAIL/zoox-fleet-intel/app --profile=$PROFILE
```

### Step 9: Grant Permissions

```bash
PROFILE=<your-profile>

# Get app SP client ID
databricks apps get $APP_NAME --profile=$PROFILE -o json | jq '.service_principal.client_id'

SP_ID=<app-sp-client-id>

# Grant catalog/schema access
databricks api post /api/2.0/sql/statements --json "{
  \"warehouse_id\": \"<warehouse-id>\",
  \"statement\": \"GRANT USE_CATALOG ON CATALOG <catalog> TO \\\`$SP_ID\\\`\"
}" --profile=$PROFILE

databricks api post /api/2.0/sql/statements --json "{
  \"warehouse_id\": \"<warehouse-id>\",
  \"statement\": \"GRANT USE_SCHEMA ON SCHEMA <catalog>.zoox_fleet_intel TO \\\`$SP_ID\\\`\"
}" --profile=$PROFILE

databricks api post /api/2.0/sql/statements --json "{
  \"warehouse_id\": \"<warehouse-id>\",
  \"statement\": \"GRANT SELECT ON SCHEMA <catalog>.zoox_fleet_intel TO \\\`$SP_ID\\\`\"
}" --profile=$PROFILE

# Grant CAN_QUERY on MAS endpoint (use endpoint UUID, not name)
ENDPOINT_UUID=$(databricks api get /api/2.0/serving-endpoints --profile=$PROFILE | \
  jq -r '.endpoints[] | select(.name | startswith("mas-")) | .id')

databricks api patch /api/2.0/permissions/serving-endpoints/$ENDPOINT_UUID \
  --json "{\"access_control_list\":[{\"service_principal_name\":\"$SP_ID\",\"permission_level\":\"CAN_QUERY\"}]}" \
  --profile=$PROFILE

# Grant Lakebase table access to SP
databricks psql <instance> --profile=$PROFILE -- -d zoox_fleet_intel -c "
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"$SP_ID\";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"$SP_ID\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"$SP_ID\";
"
```

### Step 10: Verify

Open the app URL in a browser (OAuth login required). Check:
- `GET /api/health` returns `{"status": "healthy"}` with all three checks passing
- Dashboard shows KPI data
- AI Chat responds (may take 30s for cold start)

## Project Structure

```
app/
  app.yaml              # Databricks App config (env vars, resources)
  backend/
    main.py             # FastAPI app — all routes
    core/               # Shared modules (DO NOT MODIFY)
      lakehouse.py      # Delta Lake query execution
      lakebase.py       # Lakebase PostgreSQL pool
      streaming.py      # MAS SSE streaming proxy
      health.py         # Health check endpoint
      helpers.py        # Input validation, response parsing
  frontend/src/
    index.html          # Single-file frontend (HTML + CSS + JS)
notebooks/
  01_setup_schema.sql   # Create catalog + schema
  02_generate_data.py   # Generate Delta Lake tables
  03_seed_lakebase.py   # Seed Lakebase tables
lakebase/
  core_schema.sql       # Required tables (notes, agent_actions, workflows)
  domain_schema.sql     # Domain tables (fleet_actions, surge_alerts, dispatch_overrides)
agent_bricks/
  mas_config.json       # MAS agent configuration
genie_spaces/
  config.json           # Genie Space configuration
demo-config.yaml        # Full demo config (customer, infra, AI layer, UI)
CLAUDE.md               # Vibe instructions for Claude Code
```

## Quick Tips

- **Workspace expired?** Create a new FEVM workspace and follow Steps 1-10 above.
- **Lakebase instance limit (~10)?** Reuse an existing instance: `databricks psql <instance> -- -c "CREATE DATABASE zoox_fleet_intel;"`
- **App shows empty data?** Run `notebooks/02_generate_data.py` first — the app reads from Delta Lake tables it creates.
- **Chat returns 403?** Grant `CAN_QUERY` on the MAS serving endpoint to the app SP (Step 9).
- **Health shows `lakebase: error`?** Register database resource via API + redeploy (Step 8).

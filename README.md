# Zoox Fleet Intelligence Platform

Databricks demo: event-driven demand prediction, dynamic fleet rebalancing, ride operations analytics, and an AI fleet ops assistant for Zoox's autonomous ride-hail fleet.

**Stack:** FastAPI + single-file HTML/JS frontend, deployed as a Databricks App.
**Data:** Delta Lake (analytics) + Lakebase/PostgreSQL (OLTP) + Genie Space (NL queries) + MAS Agent Bricks (AI chat).

## Live Demo

- **App:** https://zoox-fleet-intel-7474648424393858.aws.databricksapps.com
- **Workspace:** https://fe-sandbox-serverless-simplot-v1.cloud.databricks.com

## Quick Redeploy (New Workspace)

The `deploy/` module automates the entire redeployment. One command handles all 5 phases: Delta Lake tables, Lakebase setup, AI layer (Genie + MAS), app deployment, and permissions.

```bash
# Prerequisites: Databricks CLI installed, PyYAML installed (pip install pyyaml)

# 1. Authenticate to the new workspace
databricks auth login https://your-new-workspace.cloud.databricks.com --profile=new-ws

# 2. Update demo-config.yaml with new workspace info
#    - infrastructure.workspace_url
#    - infrastructure.cli_profile
#    - infrastructure.catalog
#    - infrastructure.schema
#    - infrastructure.sql_warehouse_id

# 3. Run the deployer
python -m deploy --profile=new-ws
```

### Deployer Options

```bash
python -m deploy --profile=new-ws              # Full deploy (all 5 phases)
python -m deploy --profile=new-ws --phase=app  # Run a single phase
python -m deploy --profile=new-ws --force      # Force full rebuild
python -m deploy --status                      # Show current deploy state
```

### What Each Phase Does

| Phase | What it creates |
|-------|----------------|
| **delta_lake** | Schema + 5 tables (zones, vehicles, events, rides, demand_forecasts) via pure SQL |
| **lakebase** | Instance + database + core/domain schemas + seed data (6 tables) |
| **ai_layer** | Genie Space + MAS Supervisor + UC HTTP Connection |
| **app** | Databricks App + resource registration + redeploy for env var injection |
| **permissions** | Catalog/schema/table grants, MAS CAN_QUERY, Genie CAN_RUN, Lakebase grants |

State is tracked in `deploy-state.json` (gitignored). Completed phases are skipped on re-run. Failed phases restart automatically.

### Manual Redeployment

<details>
<summary>If you prefer to run each step manually (click to expand)</summary>

#### Prerequisites

- Databricks CLI installed (`brew install databricks/tap/databricks`)
- Access to an FEVM workspace (or any serverless-enabled workspace)

#### Clone the Repo

```bash
git clone --recurse-submodules https://github.com/ankit-yadav_data/zoox-demo.git
cd zoox-demo
```

#### Step 1: Create a New Workspace

```bash
# Option A: Use vibe's FEVM skill
# /databricks-fe-vm-workspace-deployment → Template 3 (Serverless), AWS

# Option B: Manual FEVM request at go/fevm
```

#### Step 2: Authenticate CLI

```bash
databricks auth login https://fe-sandbox-serverless-<name>.cloud.databricks.com --profile=<profile>
databricks current-user me --profile=<profile>
```

#### Step 3: Create Delta Lake Tables

```bash
# Update catalog/schema in demo-config.yaml, then:
python -m deploy --profile=<profile> --phase=delta_lake
```

#### Step 4: Set Up Lakebase

```bash
python -m deploy --profile=<profile> --phase=lakebase
```

#### Step 5: Create AI Layer (Genie + MAS)

```bash
python -m deploy --profile=<profile> --phase=ai_layer
```

#### Step 6: Deploy the App

```bash
python -m deploy --profile=<profile> --phase=app
```

#### Step 7: Grant Permissions

```bash
python -m deploy --profile=<profile> --phase=permissions
```

#### Step 8: Verify

Open the app URL in a browser (OAuth login required). Check:
- `GET /api/health` returns `{"status": "healthy"}` with all three checks passing
- Dashboard shows KPI data
- AI Chat responds (may take 30s for cold start)

</details>

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
deploy/                 # Redeployment orchestrator
  __main__.py           # CLI entry point (python -m deploy)
  deployer.py           # Phase orchestrator with state tracking
  state.py              # deploy-state.json management
  config.py             # Read/write demo-config.yaml + app.yaml
  databricks_api.py     # Thin CLI/REST/SQL wrapper
  phases/
    phase_1_delta_lake.py   # Schema + SQL data generation
    phase_2_lakebase.py     # Instance, database, schemas, seed
    phase_3_ai_layer.py     # Genie Space, MAS, UC Connection
    phase_4_app.py          # App deploy + resource registration
    phase_5_permissions.py  # All permission grants
  sql/
    create_zones.sql        # 9 zone definitions
    create_vehicles.sql     # 50 vehicles (hash-based)
    create_events.sql       # ~200 venue events
    create_rides.sql        # ~50K ride records
    create_demand_forecasts.sql  # ~5K forecasts
    seed_lakebase.sql       # Lakebase operational seed data
notebooks/
  01_setup_schema.sql   # Create catalog + schema
  02_generate_data.py   # Generate Delta Lake tables (notebook version)
  03_seed_lakebase.py   # Seed Lakebase tables (notebook version)
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

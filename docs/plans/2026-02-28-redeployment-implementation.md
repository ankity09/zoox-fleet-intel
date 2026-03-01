# Redeployment System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a phase-based deployer module that redeploys any vibe-demo-accelerator demo to any Databricks workspace with a single command.

**Architecture:** A `deploy/` Python package at the repo root with an orchestrator that runs 5 phases (Delta Lake, Lakebase, AI Layer, App, Permissions) in order, tracking state in `deploy-state.json` for resumability. Config is read from `demo-config.yaml` and written back with discovered resource IDs.

**Tech Stack:** Python 3.11+, databricks-cli (subprocess), databricks-sdk (for auth), PyYAML, argparse

---

## Task 1: Scaffold the deploy/ package structure

**Files:**
- Create: `deploy/__init__.py`
- Create: `deploy/__main__.py`
- Create: `deploy/state.py`
- Create: `deploy/config.py`
- Create: `deploy/databricks_api.py`
- Create: `deploy/deployer.py`
- Create: `deploy/phases/__init__.py`
- Modify: `.gitignore` (add `deploy-state.json`)

**Step 1: Create deploy/__init__.py**

```python
"""Vibe Demo Accelerator — Deployment Orchestrator."""
```

**Step 2: Create deploy/state.py — state tracking**

Manages `deploy-state.json`. Supports read/write/update of phase status and metadata.

```python
"""Deploy state tracking — persists progress across runs."""
import json
import os
from datetime import datetime, timezone

STATE_FILE = "deploy-state.json"

def _default_state():
    return {
        "workspace_url": None,
        "profile": None,
        "started_at": None,
        "phases": {
            "delta_lake": {"status": "pending"},
            "lakebase": {"status": "pending"},
            "ai_layer": {"status": "pending"},
            "app": {"status": "pending"},
            "permissions": {"status": "pending"},
        },
    }

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return _default_state()

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def reset_state():
    state = _default_state()
    save_state(state)
    return state

def update_phase(state: dict, phase: str, **kwargs):
    state["phases"][phase].update(kwargs)
    save_state(state)

def mark_phase(state: dict, phase: str, status: str, **kwargs):
    state["phases"][phase]["status"] = status
    state["phases"][phase].update(kwargs)
    save_state(state)

def init_state(workspace_url: str, profile: str) -> dict:
    state = load_state()
    state["workspace_url"] = workspace_url
    state["profile"] = profile
    state["started_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return state
```

**Step 3: Create deploy/config.py — config reader/writer**

Reads `demo-config.yaml` and `app/app.yaml`. Writes back discovered IDs after each phase.

```python
"""Read and write demo-config.yaml and app/app.yaml."""
import os
import yaml

DEMO_CONFIG = "demo-config.yaml"
APP_YAML = os.path.join("app", "app.yaml")
GENIE_CONFIG = os.path.join("genie_spaces", "config.json")
MAS_CONFIG = os.path.join("agent_bricks", "mas_config.json")

def load_demo_config() -> dict:
    with open(DEMO_CONFIG) as f:
        return yaml.safe_load(f)

def save_demo_config(cfg: dict):
    with open(DEMO_CONFIG, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

def load_app_yaml() -> dict:
    with open(APP_YAML) as f:
        return yaml.safe_load(f)

def save_app_yaml(cfg: dict):
    with open(APP_YAML, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

def update_app_yaml_env(key: str, value: str):
    """Update a single env var in app.yaml."""
    cfg = load_app_yaml()
    for env_entry in cfg.get("env", []):
        if env_entry.get("name") == key:
            env_entry["value"] = value
            break
    save_app_yaml(cfg)

def update_app_yaml_resource(name: str, resource: dict):
    """Update or add a resource in app.yaml."""
    cfg = load_app_yaml()
    resources = cfg.setdefault("resources", [])
    for i, r in enumerate(resources):
        if r.get("name") == name:
            resources[i] = {"name": name, **resource}
            save_app_yaml(cfg)
            return
    resources.append({"name": name, **resource})
    save_app_yaml(cfg)

def get_infra(cfg: dict) -> dict:
    """Shortcut to get infrastructure section."""
    return cfg.get("infrastructure", {})
```

**Step 4: Create deploy/databricks_api.py — thin CLI/API wrapper**

Wraps `databricks` CLI calls and REST API calls via subprocess.

```python
"""Thin wrapper around Databricks CLI and REST API calls."""
import json
import subprocess
import sys
import time

def cli(args: list[str], profile: str, timeout: int = 120) -> str:
    """Run a databricks CLI command and return stdout."""
    cmd = ["databricks"] + args + [f"--profile={profile}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"CLI failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()

def cli_json(args: list[str], profile: str, timeout: int = 120) -> dict:
    """Run CLI command and parse JSON output."""
    out = cli(args + ["-o", "json"], profile, timeout)
    return json.loads(out) if out else {}

def api_get(path: str, profile: str) -> dict:
    """GET a Databricks REST API endpoint."""
    out = cli(["api", "get", path], profile)
    return json.loads(out) if out else {}

def api_post(path: str, body: dict, profile: str) -> dict:
    """POST to a Databricks REST API endpoint."""
    out = cli(["api", "post", path, "--json", json.dumps(body)], profile)
    return json.loads(out) if out else {}

def api_patch(path: str, body: dict, profile: str) -> dict:
    """PATCH a Databricks REST API endpoint."""
    out = cli(["api", "patch", path, "--json", json.dumps(body)], profile)
    return json.loads(out) if out else {}

def sql_execute(statement: str, warehouse_id: str, profile: str, timeout: str = "30s") -> dict:
    """Execute a SQL statement via the Statement Execution API."""
    body = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": timeout,
    }
    result = api_post("/api/2.0/sql/statements", body, profile)
    status = result.get("status", {})
    if status.get("state") == "FAILED":
        err = status.get("error", {}).get("message", "Unknown SQL error")
        raise RuntimeError(f"SQL failed: {err}\nStatement: {statement[:200]}")
    return result

def sql_execute_rows(statement: str, warehouse_id: str, profile: str) -> list[list]:
    """Execute SQL and return data_array."""
    result = sql_execute(statement, warehouse_id, profile)
    return result.get("result", {}).get("data_array", [])

def psql(instance: str, database: str, sql_or_file: str, profile: str, is_file: bool = False):
    """Run SQL against Lakebase via databricks psql."""
    cmd = ["databricks", "psql", instance, f"--profile={profile}", "--", "-d", database]
    if is_file:
        cmd += ["-f", sql_or_file]
    else:
        cmd += ["-c", sql_or_file]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr.strip()}")
    return result.stdout.strip()

def wait_for_instance(instance: str, profile: str, timeout_sec: int = 600):
    """Poll Lakebase instance until AVAILABLE."""
    start = time.time()
    while time.time() - start < timeout_sec:
        info = cli_json(["database", "get-database-instance", instance], profile)
        state = info.get("state", "")
        if state == "AVAILABLE":
            return info
        print(f"  Instance {instance}: {state} (waiting...)")
        time.sleep(15)
    raise TimeoutError(f"Lakebase instance {instance} not AVAILABLE after {timeout_sec}s")

def log(msg: str):
    """Print a deploy progress message."""
    print(f"  {'→'} {msg}")
```

**Step 5: Create deploy/phases/__init__.py**

```python
"""Deploy phases — each module implements a single deployment phase."""
```

**Step 6: Create deploy/deployer.py — orchestrator stub**

```python
"""Deployment orchestrator — runs phases in order with state tracking."""
from deploy import state, config
from deploy.databricks_api import log

PHASE_ORDER = ["delta_lake", "lakebase", "ai_layer", "app", "permissions"]

def run_all(profile: str, force: bool = False, single_phase: str = None):
    """Run all phases (or a single phase) for the given profile."""
    cfg = config.load_demo_config()
    infra = config.get_infra(cfg)

    workspace_url = infra.get("workspace_url", "")
    deploy_state = state.load_state()

    if force:
        deploy_state = state.reset_state()

    deploy_state = state.init_state(workspace_url, profile)

    phases_to_run = [single_phase] if single_phase else PHASE_ORDER

    for phase_name in phases_to_run:
        phase_state = deploy_state["phases"].get(phase_name, {})
        if phase_state.get("status") == "completed" and not force:
            log(f"Phase {phase_name}: already completed, skipping")
            continue

        log(f"Phase {phase_name}: starting...")
        try:
            _run_phase(phase_name, cfg, deploy_state)
            state.mark_phase(deploy_state, phase_name, "completed")
            log(f"Phase {phase_name}: completed")
        except Exception as e:
            state.mark_phase(deploy_state, phase_name, "failed", error=str(e))
            log(f"Phase {phase_name}: FAILED — {e}")
            raise

    log("All phases completed successfully!")
    app_url = deploy_state["phases"].get("app", {}).get("app_url", "")
    if app_url:
        log(f"App URL: {app_url}")

def _run_phase(name: str, cfg: dict, deploy_state: dict):
    """Import and run a phase module."""
    if name == "delta_lake":
        from deploy.phases.phase_1_delta_lake import run
    elif name == "lakebase":
        from deploy.phases.phase_2_lakebase import run
    elif name == "ai_layer":
        from deploy.phases.phase_3_ai_layer import run
    elif name == "app":
        from deploy.phases.phase_4_app import run
    elif name == "permissions":
        from deploy.phases.phase_5_permissions import run
    else:
        raise ValueError(f"Unknown phase: {name}")
    run(cfg, deploy_state)
```

**Step 7: Create deploy/__main__.py — CLI entry point**

```python
"""CLI entry point: python -m deploy"""
import argparse
import json
from deploy import state, deployer

def main():
    parser = argparse.ArgumentParser(description="Deploy demo to a Databricks workspace")
    parser.add_argument("--profile", help="Databricks CLI profile name")
    parser.add_argument("--phase", help="Run a single phase", choices=[
        "delta_lake", "lakebase", "ai_layer", "app", "permissions"
    ])
    parser.add_argument("--force", action="store_true", help="Force full rebuild")
    parser.add_argument("--status", action="store_true", help="Show current deploy state")
    args = parser.parse_args()

    if args.status:
        s = state.load_state()
        print(json.dumps(s, indent=2))
        return

    if not args.profile:
        # Interactive mode: read from demo-config.yaml
        from deploy.config import load_demo_config, get_infra
        cfg = load_demo_config()
        infra = get_infra(cfg)
        profile = infra.get("cli_profile")
        if not profile:
            print("Error: No --profile provided and no cli_profile in demo-config.yaml")
            return
        args.profile = profile

    deployer.run_all(
        profile=args.profile,
        force=args.force,
        single_phase=args.phase,
    )

if __name__ == "__main__":
    main()
```

**Step 8: Add deploy-state.json to .gitignore**

Append `deploy-state.json` to `.gitignore`.

**Step 9: Commit**

```bash
git add deploy/ .gitignore
git commit -m "feat: scaffold deploy/ package with state, config, API wrapper, CLI entry point"
```

---

## Task 2: Phase 1 — Delta Lake (schema + SQL data generation)

**Files:**
- Create: `deploy/phases/phase_1_delta_lake.py`
- Create: `deploy/sql/create_zones.sql`
- Create: `deploy/sql/create_vehicles.sql`
- Create: `deploy/sql/create_events.sql`
- Create: `deploy/sql/create_rides.sql`
- Create: `deploy/sql/create_demand_forecasts.sql`

**Step 1: Create phase_1_delta_lake.py**

This phase creates the schema and runs each SQL file. It reads catalog/schema/warehouse from `demo-config.yaml` infrastructure section and substitutes `${CATALOG}` and `${SCHEMA}` placeholders in SQL files.

```python
"""Phase 1: Create Delta Lake schema and generate tables via SQL."""
import os
import glob
from deploy import state, config
from deploy.databricks_api import sql_execute, sql_execute_rows, log

SQL_DIR = os.path.join("deploy", "sql")

def run(cfg: dict, deploy_state: dict):
    infra = config.get_infra(cfg)
    profile = deploy_state["profile"]
    catalog = infra["catalog"]
    schema = infra["schema"]
    warehouse_id = infra["sql_warehouse_id"]

    # 1. Create schema
    log(f"Creating schema {catalog}.{schema}")
    sql_execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}", warehouse_id, profile)

    # 2. Run each SQL file
    sql_files = sorted(glob.glob(os.path.join(SQL_DIR, "create_*.sql")))
    tables_created = deploy_state["phases"]["delta_lake"].get("tables_created", [])

    for sql_path in sql_files:
        table_name = os.path.basename(sql_path).replace("create_", "").replace(".sql", "")
        if table_name in tables_created:
            log(f"  Table {table_name}: already created, skipping")
            continue

        log(f"  Creating table: {table_name}")
        with open(sql_path) as f:
            sql_template = f.read()

        # Substitute placeholders
        sql = sql_template.replace("${CATALOG}", catalog).replace("${SCHEMA}", schema)

        # SQL files may contain multiple statements separated by "-- SPLIT"
        statements = [s.strip() for s in sql.split("-- SPLIT") if s.strip()]
        for stmt in statements:
            sql_execute(stmt, warehouse_id, profile, timeout="120s")

        tables_created.append(table_name)
        state.update_phase(deploy_state, "delta_lake",
                          tables_created=tables_created,
                          catalog=catalog, schema=schema,
                          warehouse_id=warehouse_id)

    # 3. Verify row counts
    log("Verifying table row counts:")
    for table_name in tables_created:
        rows = sql_execute_rows(
            f"SELECT COUNT(*) FROM {catalog}.{schema}.{table_name}",
            warehouse_id, profile
        )
        count = rows[0][0] if rows else "?"
        log(f"  {table_name}: {count} rows")
```

**Step 2: Create SQL data generation files**

Convert the Python notebook logic to pure Databricks SQL. Each file uses `${CATALOG}` and `${SCHEMA}` placeholders. Use `-- SPLIT` to separate multiple statements.

**create_zones.sql** — 9 rows, pure INSERT VALUES.

**create_vehicles.sql** — 50 rows, pure INSERT VALUES.

**create_events.sql** — ~200 rows, use EXPLODE + SEQUENCE for date generation.

**create_rides.sql** — ~50K rows, use SEQUENCE + hash(concat()) for deterministic generation. This is the biggest SQL conversion — translate Python's `_hash_float`/`_hash_choice` logic to `conv(substr(sha2(...),1,8),16)` SQL expressions.

**create_demand_forecasts.sql** — ~5K rows, use SEQUENCE + date arithmetic.

Each SQL file follows this pattern:
```sql
DROP TABLE IF EXISTS ${CATALOG}.${SCHEMA}.table_name;
-- SPLIT
CREATE TABLE ${CATALOG}.${SCHEMA}.table_name USING DELTA AS
SELECT ...
```

**Step 3: Test locally**

```bash
python -m deploy --profile=simplot-v1 --phase=delta_lake
```

Verify each table has expected row counts.

**Step 4: Commit**

```bash
git add deploy/phases/phase_1_delta_lake.py deploy/sql/
git commit -m "feat: Phase 1 — Delta Lake schema + SQL data generation"
```

---

## Task 3: Phase 2 — Lakebase (instance, database, schemas, seed)

**Files:**
- Create: `deploy/phases/phase_2_lakebase.py`
- Create: `deploy/sql/seed_lakebase.sql` (converted from 03_seed_lakebase.py)

**Step 1: Create phase_2_lakebase.py**

```python
"""Phase 2: Lakebase instance, database, schemas, and seed data."""
import os
from deploy import state, config
from deploy.databricks_api import cli, cli_json, psql, wait_for_instance, log

CORE_SCHEMA = os.path.join("lakebase", "core_schema.sql")
DOMAIN_SCHEMA = os.path.join("lakebase", "domain_schema.sql")
SEED_SQL = os.path.join("deploy", "sql", "seed_lakebase.sql")

def run(cfg: dict, deploy_state: dict):
    profile = deploy_state["profile"]
    ai = cfg.get("ai_layer", {})
    instance = ai.get("lakebase_instance", "")
    database = ai.get("lakebase_database", "")

    if not instance or not database:
        raise ValueError("lakebase_instance and lakebase_database must be set in demo-config.yaml ai_layer section")

    phase = deploy_state["phases"]["lakebase"]

    # 1. Check/create Lakebase instance
    log(f"Checking Lakebase instance: {instance}")
    try:
        info = cli_json(["database", "get-database-instance", instance], profile)
        inst_state = info.get("state", "UNKNOWN")
        log(f"  Instance exists, state: {inst_state}")
        if inst_state != "AVAILABLE":
            log("  Waiting for instance to become AVAILABLE...")
            wait_for_instance(instance, profile)
    except RuntimeError:
        log(f"  Instance not found, creating {instance} (CU_1)...")
        cli(["database", "create-database-instance", instance, "--capacity", "CU_1"], profile)
        wait_for_instance(instance, profile)

    # 2. Check/create database
    log(f"Checking database: {database}")
    try:
        psql(instance, "postgres", f"SELECT 1 FROM pg_database WHERE datname = '{database}'", profile)
        # Check if it returned a row
        result = psql(instance, "postgres",
                      f"SELECT COUNT(*) FROM pg_database WHERE datname = '{database}'", profile)
        if "0" in result:
            raise RuntimeError("not found")
        log(f"  Database {database} exists")
    except RuntimeError:
        log(f"  Creating database: {database}")
        psql(instance, "postgres", f"CREATE DATABASE {database}", profile)

    # 3. Apply core schema
    if not phase.get("core_schema_applied"):
        log("Applying core schema...")
        psql(instance, database, CORE_SCHEMA, profile, is_file=True)
        state.update_phase(deploy_state, "lakebase", core_schema_applied=True)
    else:
        log("Core schema already applied, skipping")

    # 4. Apply domain schema
    if not phase.get("domain_schema_applied"):
        log("Applying domain schema...")
        psql(instance, database, DOMAIN_SCHEMA, profile, is_file=True)
        state.update_phase(deploy_state, "lakebase", domain_schema_applied=True)
    else:
        log("Domain schema already applied, skipping")

    # 5. Seed data
    if not phase.get("seeded"):
        log("Seeding Lakebase operational data...")
        psql(instance, database, SEED_SQL, profile, is_file=True)
        state.update_phase(deploy_state, "lakebase", seeded=True)
    else:
        log("Lakebase already seeded, skipping")

    state.update_phase(deploy_state, "lakebase",
                      instance_name=instance, database_name=database)
```

**Step 2: Create deploy/sql/seed_lakebase.sql**

Convert `notebooks/03_seed_lakebase.py` Python INSERT logic into a pure SQL file with INSERT statements for all 6 tables (fleet_actions, surge_alerts, dispatch_overrides, workflows, agent_actions, notes). Use `ON CONFLICT DO NOTHING` to make it idempotent.

**Step 3: Test locally**

```bash
python -m deploy --profile=simplot-v1 --phase=lakebase
```

**Step 4: Commit**

```bash
git add deploy/phases/phase_2_lakebase.py deploy/sql/seed_lakebase.sql
git commit -m "feat: Phase 2 — Lakebase instance, database, schemas, seed data"
```

---

## Task 4: Phase 3 — AI Layer (Genie Space, MAS, UC Connection)

**Files:**
- Create: `deploy/phases/phase_3_ai_layer.py`

**Step 1: Create phase_3_ai_layer.py**

This is the most complex phase. It creates Genie Space (3-step PATCH), MAS Supervisor (POST then PATCH for MCP agents), and UC HTTP Connection.

```python
"""Phase 3: AI Layer — Genie Space, MAS Supervisor, UC HTTP Connection."""
import json
import time
from deploy import state, config
from deploy.databricks_api import api_get, api_post, api_patch, log

def run(cfg: dict, deploy_state: dict):
    profile = deploy_state["profile"]
    infra = config.get_infra(cfg)
    ai = cfg.get("ai_layer", {})
    phase = deploy_state["phases"]["ai_layer"]
    warehouse_id = infra["sql_warehouse_id"]
    catalog = infra["catalog"]
    schema = infra["schema"]

    # --- 1. Genie Space ---
    genie_id = phase.get("genie_space_id")
    if not genie_id:
        genie_id = _create_genie_space(cfg, profile, warehouse_id, catalog, schema)
        state.update_phase(deploy_state, "ai_layer", genie_space_id=genie_id)
        # Write back to demo-config and app.yaml
        cfg["ai_layer"]["genie_space_id"] = genie_id
        config.save_demo_config(cfg)
        config.update_app_yaml_env("GENIE_SPACE_ID", genie_id)
    else:
        log(f"Genie Space already created: {genie_id}")

    # --- 2. MAS Supervisor ---
    mas_tile = phase.get("mas_tile_id")
    mas_full = phase.get("mas_full_tile_id")
    if not mas_tile:
        mas_tile, mas_full = _create_mas(cfg, profile, genie_id)
        state.update_phase(deploy_state, "ai_layer",
                          mas_tile_id=mas_tile, mas_full_tile_id=mas_full)
        cfg["ai_layer"]["mas_tile_id"] = mas_tile
        cfg["ai_layer"]["mas_full_tile_id"] = mas_full
        config.save_demo_config(cfg)
        config.update_app_yaml_env("MAS_TILE_ID", mas_tile)
        # Update MAS endpoint resource in app.yaml
        config.update_app_yaml_resource("mas-endpoint", {
            "serving_endpoint": {
                "name": f"mas-{mas_tile}-endpoint",
                "permission": "CAN_QUERY",
            }
        })
    else:
        log(f"MAS already created: tile={mas_tile}")

    # --- 3. UC HTTP Connection (only if MCP agent configured) ---
    mcp_agents = [a for a in ai.get("sub_agents", []) if a.get("type") == "external-mcp-server"]
    if mcp_agents:
        conn_name = phase.get("uc_connection_name")
        if not conn_name:
            conn_name = _create_uc_connection(cfg, profile)
            state.update_phase(deploy_state, "ai_layer", uc_connection_name=conn_name)
            cfg["ai_layer"]["mcp_connection_name"] = conn_name
            config.save_demo_config(cfg)
        else:
            log(f"UC HTTP Connection already created: {conn_name}")


def _create_genie_space(cfg, profile, warehouse_id, catalog, schema):
    """Create Genie Space with the 3-step PATCH dance."""
    ai = cfg.get("ai_layer", {})
    story = cfg.get("story", {})
    tables = ai.get("genie_tables", [])

    # Step 1: POST blank space
    log("Creating Genie Space...")
    resp = api_post("/api/2.0/genie/spaces", {
        "serialized_space": '{"version": 2}',
        "warehouse_id": warehouse_id,
    }, profile)
    space_id = resp.get("space_id")
    if not space_id:
        raise RuntimeError(f"Genie Space creation failed: {resp}")
    log(f"  Created space: {space_id}")

    # Step 2: PATCH title + description
    title = f"{story.get('customer_name', 'Demo')} Fleet Data"
    api_patch(f"/api/2.0/genie/spaces/{space_id}", {
        "title": title,
        "description": f"Query {story.get('demo_name', 'demo')} data",
    }, profile)

    # Step 3: PATCH tables via serialized_space (sorted!)
    table_ids = sorted([f"{catalog}.{schema}.{t}" for t in tables])
    table_entries = [{"identifier": tid} for tid in table_ids]
    serialized = json.dumps({
        "version": 2,
        "data_sources": {"tables": table_entries},
    })
    api_patch(f"/api/2.0/genie/spaces/{space_id}", {
        "serialized_space": serialized,
    }, profile)

    # Step 4: PATCH instructions
    api_patch(f"/api/2.0/genie/spaces/{space_id}", {
        "instructions": ai.get("mas_persona", ""),
    }, profile)

    log(f"  Genie Space configured with {len(tables)} tables")
    return space_id


def _create_mas(cfg, profile, genie_space_id):
    """Create MAS Supervisor — POST simple agents, then PATCH to add MCP."""
    ai = cfg.get("ai_layer", {})
    story = cfg.get("story", {})
    infra = config.get_infra(cfg)

    # Build agents list — start with simple types only (POST fails with external-mcp-server)
    simple_agents = []
    mcp_agents = []
    for agent in ai.get("sub_agents", []):
        agent_def = _build_agent_def(agent, cfg, genie_space_id)
        if agent.get("type") == "external-mcp-server":
            mcp_agents.append(agent_def)
        else:
            simple_agents.append(agent_def)

    mas_name = ai.get("app_name", story.get("customer_name", "demo").lower().replace(" ", "-"))

    # Step 1: POST with simple agents
    log("Creating MAS Supervisor...")
    body = {
        "name": mas_name,
        "instructions": ai.get("mas_persona", ""),
        "agents": simple_agents,
    }
    resp = api_post("/api/2.0/multi-agent-supervisors", body, profile)
    tile_id = resp.get("tile_id", "")
    if not tile_id:
        raise RuntimeError(f"MAS creation failed: {resp}")
    log(f"  MAS created (tile: {tile_id[:8]})")

    # Step 2: PATCH to add MCP agents
    if mcp_agents:
        log(f"  Adding {len(mcp_agents)} MCP agent(s) via PATCH...")
        all_agents = simple_agents + mcp_agents
        api_patch(f"/api/2.0/multi-agent-supervisors/{tile_id}", {
            "name": mas_name,
            "agents": all_agents,
        }, profile)

    # Step 3: Wait for serving endpoint
    log("  Waiting for MAS endpoint to provision...")
    tile_8 = tile_id[:8]
    ep_name = f"mas-{tile_8}-endpoint"
    for attempt in range(20):
        eps = api_get("/api/2.0/serving-endpoints", profile)
        for ep in eps.get("endpoints", []):
            if ep.get("name") == ep_name:
                ep_state = ep.get("state", {}).get("ready", "")
                if ep_state == "READY":
                    log(f"  Endpoint {ep_name} is READY")
                    return tile_8, tile_id
                log(f"  Endpoint state: {ep_state}")
                break
        time.sleep(15)

    log(f"  Warning: endpoint not READY after 5 min, continuing anyway")
    return tile_8, tile_id


def _build_agent_def(agent_cfg, cfg, genie_space_id):
    """Build a MAS agent definition from demo-config sub_agents entry."""
    atype = agent_cfg["type"]
    name = agent_cfg["name"]
    desc = agent_cfg.get("description", "")
    infra = config.get_infra(cfg)
    ai = cfg.get("ai_layer", {})

    if atype == "genie-space":
        return {
            "agent_type": "genie-space",
            "genie_space": {"id": genie_space_id},
            "name": name,
            "description": desc,
        }
    elif atype == "knowledge-assistant":
        ka_id = ai.get("ka_tile_id", "")
        return {
            "agent_type": "knowledge-assistant",
            "knowledge_assistant": {"knowledge_assistant_id": ka_id},
            "name": name,
            "description": desc,
        }
    elif atype == "unity-catalog-function":
        return {
            "agent_type": "unity-catalog-function",
            "unity_catalog_function": {
                "uc_path": {
                    "catalog": infra["catalog"],
                    "schema": infra["schema"],
                    "name": name,
                },
            },
            "name": name,
            "description": desc,
        }
    elif atype == "external-mcp-server":
        conn_name = ai.get("mcp_connection_name", "")
        return {
            "agent_type": "external-mcp-server",
            "external_mcp_server": {"connection_name": conn_name},
            "name": name,
            "description": desc,
        }
    else:
        raise ValueError(f"Unknown agent type: {atype}")


def _create_uc_connection(cfg, profile):
    """Create UC HTTP connection pointing to shared Lakebase MCP server."""
    ai = cfg.get("ai_layer", {})
    infra = config.get_infra(cfg)
    mcp = infra.get("shared_mcp_server", {})
    mcp_url = mcp.get("app_url", "")
    database = ai.get("lakebase_database", "")
    conn_name = ai.get("mcp_connection_name", f"{ai.get('app_name', 'demo')}-lakebase-mcp")

    log(f"Creating UC HTTP Connection: {conn_name}")
    log(f"  MCP server: {mcp_url}/db/{database}/mcp/")

    # Note: Creating UC HTTP connections requires SP OAuth credentials
    # which must be configured manually. This step logs the required
    # configuration and creates a placeholder.
    log(f"  NOTE: UC HTTP Connection must be created manually or via the workspace UI.")
    log(f"  Connection name: {conn_name}")
    log(f"  Host: {mcp_url}")
    log(f"  Base path: /db/{database}/mcp/")

    return conn_name
```

**Step 2: Test**

```bash
python -m deploy --profile=simplot-v1 --phase=ai_layer
```

**Step 3: Commit**

```bash
git add deploy/phases/phase_3_ai_layer.py
git commit -m "feat: Phase 3 — Genie Space, MAS Supervisor, UC HTTP Connection"
```

---

## Task 5: Phase 4 — App Deployment

**Files:**
- Create: `deploy/phases/phase_4_app.py`

**Step 1: Create phase_4_app.py**

```python
"""Phase 4: Deploy Databricks App — create, deploy, register resources, redeploy."""
import os
import time
from deploy import state, config
from deploy.databricks_api import cli, cli_json, api_patch, log

def run(cfg: dict, deploy_state: dict):
    profile = deploy_state["profile"]
    ai = cfg.get("ai_layer", {})
    infra = config.get_infra(cfg)
    phase = deploy_state["phases"]["app"]
    app_name = ai.get("app_name", "demo-app")

    # 1. Create app (skip if exists)
    sp_client_id = phase.get("sp_client_id")
    if not sp_client_id:
        log(f"Creating app: {app_name}")
        try:
            info = cli_json(["apps", "create", app_name], profile)
        except RuntimeError as e:
            if "already exists" in str(e):
                log(f"  App already exists, fetching info...")
                info = cli_json(["apps", "get", app_name], profile)
            else:
                raise
        sp_client_id = info.get("service_principal_client_id", "")
        app_url = info.get("url", "")
        state.update_phase(deploy_state, "app",
                          app_name=app_name, sp_client_id=sp_client_id, app_url=app_url)
        # Write back to config
        cfg["ai_layer"]["app_sp_client_id"] = sp_client_id
        cfg["ai_layer"]["app_url"] = app_url
        config.save_demo_config(cfg)
    else:
        log(f"App already created: {app_name} (SP: {sp_client_id[:8]}...)")

    # 2. Set user API scopes
    log("Setting user API scopes...")
    api_patch(f"/api/2.0/apps/{app_name}", {
        "user_api_scopes": ["serving.serving-endpoints", "sql"],
    }, profile)

    # 3. Sync + Deploy
    workspace_user = _get_current_user(profile)
    source_path = f"/Workspace/Users/{workspace_user}/{app_name}/app"
    log(f"Syncing code to {source_path}...")
    cli(["sync", "./app", source_path, "--watch=false"], profile, timeout=300)

    log("Deploying app (first deploy)...")
    cli(["apps", "deploy", app_name, "--source-code-path", source_path], profile, timeout=300)

    # 4. Register resources
    log("Registering resources...")
    mas_tile = deploy_state["phases"].get("ai_layer", {}).get("mas_tile_id", ai.get("mas_tile_id", ""))
    lakebase_instance = ai.get("lakebase_instance", "")
    lakebase_database = ai.get("lakebase_database", "")

    resources = [
        {"name": "sql-warehouse", "sql_warehouse": {
            "id": infra["sql_warehouse_id"], "permission": "CAN_USE"}},
    ]
    if mas_tile:
        resources.append({"name": "mas-endpoint", "serving_endpoint": {
            "name": f"mas-{mas_tile}-endpoint", "permission": "CAN_QUERY"}})
    if lakebase_instance and lakebase_database:
        resources.append({"name": "database", "database": {
            "instance_name": lakebase_instance,
            "database_name": lakebase_database,
            "permission": "CAN_CONNECT_AND_CREATE"}})

    cli(["apps", "update", app_name, "--json",
         __import__("json").dumps({"resources": resources})], profile)

    # 5. Redeploy to inject PGHOST/PGPORT/PGDATABASE/PGUSER
    log("Redeploying (to inject Lakebase env vars)...")
    cli(["apps", "deploy", app_name, "--source-code-path", source_path], profile, timeout=300)

    log(f"App deployed: {deploy_state['phases']['app'].get('app_url', '')}")


def _get_current_user(profile: str) -> str:
    info = cli_json(["current-user", "me"], profile)
    return info.get("userName", "")
```

**Step 2: Commit**

```bash
git add deploy/phases/phase_4_app.py
git commit -m "feat: Phase 4 — App deployment with resource registration"
```

---

## Task 6: Phase 5 — Permissions

**Files:**
- Create: `deploy/phases/phase_5_permissions.py`

**Step 1: Create phase_5_permissions.py**

```python
"""Phase 5: Grant all permissions to the app's service principal."""
from deploy import config
from deploy.databricks_api import sql_execute, api_get, api_patch, psql, log

def run(cfg: dict, deploy_state: dict):
    profile = deploy_state["profile"]
    infra = config.get_infra(cfg)
    ai = cfg.get("ai_layer", {})
    app_phase = deploy_state["phases"]["app"]
    ai_phase = deploy_state["phases"]["ai_layer"]
    sp = app_phase.get("sp_client_id", ai.get("app_sp_client_id", ""))
    warehouse_id = infra["sql_warehouse_id"]
    catalog = infra["catalog"]
    schema = infra["schema"]

    if not sp:
        raise RuntimeError("App SP client ID not found — run app phase first")

    # 1. Delta Lake: catalog + schema + tables
    log(f"Granting Delta Lake access to SP {sp[:8]}...")
    for grant_sql in [
        f"GRANT USE_CATALOG ON CATALOG {catalog} TO `{sp}`",
        f"GRANT USE_SCHEMA ON SCHEMA {catalog}.{schema} TO `{sp}`",
        f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{sp}`",
    ]:
        sql_execute(grant_sql, warehouse_id, profile)

    # 2. MAS endpoint: CAN_QUERY (needs UUID, not name)
    mas_tile = ai_phase.get("mas_tile_id", ai.get("mas_tile_id", ""))
    if mas_tile:
        ep_name = f"mas-{mas_tile}-endpoint"
        log(f"Granting CAN_QUERY on {ep_name}...")
        eps = api_get("/api/2.0/serving-endpoints", profile)
        ep_uuid = None
        for ep in eps.get("endpoints", []):
            if ep.get("name") == ep_name:
                ep_uuid = ep.get("id")
                break
        if ep_uuid:
            api_patch(f"/api/2.0/permissions/serving-endpoints/{ep_uuid}", {
                "access_control_list": [
                    {"service_principal_name": sp, "permission_level": "CAN_QUERY"},
                ],
            }, profile)
        else:
            log(f"  Warning: endpoint {ep_name} not found, skipping CAN_QUERY grant")

    # 3. Genie Space: CAN_RUN
    genie_id = ai_phase.get("genie_space_id", ai.get("genie_space_id", ""))
    if genie_id:
        log(f"Granting CAN_RUN on Genie Space {genie_id[:8]}...")
        api_patch(f"/api/2.0/permissions/genie/{genie_id}", {
            "access_control_list": [
                {"service_principal_name": sp, "permission_level": "CAN_RUN"},
                {"group_name": "users", "permission_level": "CAN_RUN"},
            ],
        }, profile)

    # 4. Lakebase: table access
    instance = ai.get("lakebase_instance", "")
    database = ai.get("lakebase_database", "")
    if instance and database:
        log("Granting Lakebase table access...")
        grants_sql = f"""
GRANT ALL ON ALL TABLES IN SCHEMA public TO "{sp}";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{sp}";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{sp}";
"""
        psql(instance, database, grants_sql, profile)

    log("All permissions granted successfully")
```

**Step 2: Commit**

```bash
git add deploy/phases/phase_5_permissions.py
git commit -m "feat: Phase 5 — Permission grants for app SP"
```

---

## Task 7: SQL Data Generation Files (Delta Lake)

**Files:**
- Create: `deploy/sql/create_zones.sql`
- Create: `deploy/sql/create_vehicles.sql`
- Create: `deploy/sql/create_events.sql`
- Create: `deploy/sql/create_rides.sql`
- Create: `deploy/sql/create_demand_forecasts.sql`

This is the most labor-intensive task — converting the Python data generation in `notebooks/02_generate_data.py` (666 lines) to pure Databricks SQL.

**Step 1:** Read `notebooks/02_generate_data.py` in full. Understand every table schema, every constant, every hash function.

**Step 2:** For each table, write a self-contained SQL file that produces identical (or equivalent) data using only SQL functions: `sha2()`, `conv()`, `explode()`, `sequence()`, `date_add()`, `concat()`, `CASE WHEN`, CTEs.

**Step 3:** Test each SQL file individually:
```bash
python -m deploy --profile=simplot-v1 --phase=delta_lake
```

**Step 4: Commit**

```bash
git add deploy/sql/
git commit -m "feat: SQL data generation files for Delta Lake tables"
```

---

## Task 8: Lakebase Seed SQL File

**Files:**
- Create: `deploy/sql/seed_lakebase.sql`

**Step 1:** Read `notebooks/03_seed_lakebase.py` (440 lines). Extract all INSERT data.

**Step 2:** Convert to pure PostgreSQL INSERT statements with `ON CONFLICT DO NOTHING` for idempotency.

**Step 3:** Test via:
```bash
python -m deploy --profile=simplot-v1 --phase=lakebase
```

**Step 4: Commit**

```bash
git add deploy/sql/seed_lakebase.sql
git commit -m "feat: Lakebase seed SQL file"
```

---

## Task 9: End-to-End Test

**Step 1:** Reset state and run full deploy
```bash
python -m deploy --profile=simplot-v1 --force
```

**Step 2:** Verify all phases complete without error

**Step 3:** Check `deploy-state.json` shows all phases `completed`

**Step 4:** Verify `demo-config.yaml` and `app/app.yaml` were updated with new IDs

**Step 5:** Visit app URL in browser, verify health endpoint and data loads

**Step 6:** Test resumability — manually fail a phase, re-run, verify it picks up

**Step 7:** Commit any fixes

```bash
git add -A
git commit -m "fix: end-to-end deploy test fixes"
```

---

## Task 10: Update scaffold documentation

**Files:**
- Modify: `README.md` — add deploy section
- Modify: `CLAUDE.md` — add deploy module documentation

**Step 1:** Add a "Quick Redeploy" section to README.md:
```markdown
## Quick Redeploy (New Workspace)
python -m deploy --profile=<new-profile>
```

**Step 2:** Add deploy module docs to CLAUDE.md under a new "## Deployer Module" section.

**Step 3:** Commit

```bash
git add README.md CLAUDE.md
git commit -m "docs: add deployer module documentation"
```

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
        if os.path.exists(SEED_SQL):
            log("Seeding Lakebase operational data...")
            psql(instance, database, SEED_SQL, profile, is_file=True)
            state.update_phase(deploy_state, "lakebase", seeded=True)
        else:
            log("Warning: seed_lakebase.sql not found, skipping seed")
    else:
        log("Lakebase already seeded, skipping")

    state.update_phase(deploy_state, "lakebase",
                      instance_name=instance, database_name=database)

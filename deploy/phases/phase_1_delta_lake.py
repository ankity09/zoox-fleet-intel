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

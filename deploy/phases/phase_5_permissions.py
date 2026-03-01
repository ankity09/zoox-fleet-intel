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
        grants_sql = (
            f'GRANT ALL ON ALL TABLES IN SCHEMA public TO "{sp}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{sp}";'
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{sp}";'
        )
        psql(instance, database, grants_sql, profile)

    log("All permissions granted successfully")

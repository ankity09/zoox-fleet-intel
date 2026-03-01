"""Phase 4: Deploy Databricks App — create, deploy, register resources, redeploy."""
import json
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

    cli(["apps", "update", app_name, "--json", json.dumps({"resources": resources})], profile)

    # 5. Redeploy to inject PGHOST/PGPORT/PGDATABASE/PGUSER
    log("Redeploying (to inject Lakebase env vars)...")
    cli(["apps", "deploy", app_name, "--source-code-path", source_path], profile, timeout=300)

    log(f"App deployed: {deploy_state['phases']['app'].get('app_url', '')}")


def _get_current_user(profile: str) -> str:
    info = cli_json(["current-user", "me"], profile)
    return info.get("userName", "")

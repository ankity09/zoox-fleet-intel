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
    instructions = ai.get("mas_persona", "")
    if instructions:
        api_patch(f"/api/2.0/genie/spaces/{space_id}", {
            "instructions": instructions,
        }, profile)

    log(f"  Genie Space configured with {len(tables)} tables")
    return space_id


def _create_mas(cfg, profile, genie_space_id):
    """Create MAS Supervisor — POST simple agents, then PATCH to add MCP."""
    ai = cfg.get("ai_layer", {})
    story = cfg.get("story", {})

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
    # which must be configured manually. This step logs the required config.
    log(f"  NOTE: UC HTTP Connection must be created manually or via the workspace UI.")
    log(f"  Connection name: {conn_name}")
    log(f"  Host: {mcp_url}")
    log(f"  Base path: /db/{database}/mcp/")

    return conn_name

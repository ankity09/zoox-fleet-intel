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
            log(f"Phase {phase_name}: FAILED \u2014 {e}")
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

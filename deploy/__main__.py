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

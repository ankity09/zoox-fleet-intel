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

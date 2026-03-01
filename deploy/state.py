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

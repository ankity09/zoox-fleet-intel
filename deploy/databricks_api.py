"""Thin wrapper around Databricks CLI and REST API calls."""
import json
import subprocess
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
        log(f"  Instance {instance}: {state} (waiting...)")
        time.sleep(15)
    raise TimeoutError(f"Lakebase instance {instance} not AVAILABLE after {timeout_sec}s")


def log(msg: str):
    """Print a deploy progress message."""
    print(f"  \u2192 {msg}")

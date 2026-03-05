#!/usr/bin/env bash
# fix-permissions.sh — Run after every deploy or app config change
# Fixes: resources + user_api_scopes (single PATCH), warehouse CAN_USE, MAS CAN_QUERY
# NOTE: demo-database (provisioned Lakebase) handles SP role + SECURITY LABEL automatically.
# No ALTER ROLE or SECURITY LABEL steps needed (unlike autoscale).
#
# USAGE:
#   ./scripts/fix-permissions.sh              # uses ay-sandbox profile
#   ./scripts/fix-permissions.sh ay-sandbox   # explicit profile
set -euo pipefail

PROFILE="${1:-ay-sandbox}"
APP="zoox-fleet-intel"
WAREHOUSE="ed02571b45fb8e8b"
SP="c14fde51-747f-4294-959c-1f13ad5f7f37"
MAS_ENDPOINT="mas-7bd87eff-endpoint"

echo "=== Fix: re-register resources + user_api_scopes (single PATCH) ==="
# IMPORTANT: Must be ONE call — separate calls for resources vs scopes clear each other
databricks api patch /api/2.0/apps/"$APP" --json '{
  "user_api_scopes": ["serving.serving-endpoints", "sql"],
  "resources": [
    {"name": "sql-warehouse", "sql_warehouse": {"id": "'"$WAREHOUSE"'", "permission": "CAN_USE"}},
    {"name": "mas-endpoint", "serving_endpoint": {"name": "'"$MAS_ENDPOINT"'", "permission": "CAN_QUERY"}},
    {"name": "database", "database": {"instance_name": "demo-database", "database_name": "zoox_fleet_intel", "permission": "CAN_CONNECT_AND_CREATE"}}
  ]
}' --profile="$PROFILE" -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('  resources:', len(d.get('resources') or []))
print('  user_api_scopes:', d.get('user_api_scopes', []))
"

echo "=== Fix: re-grant warehouse CAN_USE ==="
databricks api patch /api/2.0/permissions/warehouses/"$WAREHOUSE" \
  --json '{"access_control_list":[{"service_principal_name":"'"$SP"'","permission_level":"CAN_USE"}]}' \
  --profile="$PROFILE" > /dev/null && echo "  warehouse: OK"

echo "=== Fix: re-grant MAS endpoint CAN_QUERY ==="
MAS_EP_UUID=$(databricks api get /api/2.0/serving-endpoints --profile="$PROFILE" -o json | \
  python3 -c "import sys,json; eps=json.load(sys.stdin).get('endpoints',[]); [print(e['id']) for e in eps if e.get('name')=='$MAS_ENDPOINT']")
databricks api patch /api/2.0/permissions/serving-endpoints/"$MAS_EP_UUID" \
  --json '{"access_control_list":[{"service_principal_name":"'"$SP"'","permission_level":"CAN_QUERY"}]}' \
  --profile="$PROFILE" > /dev/null && echo "  MAS endpoint: OK"

echo ""
echo "Done. Open app in INCOGNITO window to re-authenticate with new scopes."
echo ""
echo "NOTE: After a NEW deploy (not just resource fix), if Lakebase errors appear, run:"
echo "  databricks psql demo-database --profile=$PROFILE -- -d zoox_fleet_intel -c \\"
echo "    \"GRANT ALL ON ALL TABLES IN SCHEMA public TO \\\"$SP\\\"\""

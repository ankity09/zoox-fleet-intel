# /deploy-demo — Quick Redeploy

Redeploy the current demo app to Databricks. This is the command you run after making code changes.

## Steps

1. **Read `demo-config.yaml`** to get the CLI profile, app name, and workspace path.
2. **Read `CLAUDE.md`** Project Identity section if `demo-config.yaml` doesn't exist.

3. **`[PARALLEL]` — Launch simultaneously using Task tool:**
   - **Task 1:** Sync app code to workspace:
     ```bash
     databricks sync ./app /Workspace/Users/<email>/demos/<app-name>/app --profile=<profile> --watch=false
     ```
   - **Task 2:** Check if resources are registered:
     ```bash
     databricks apps get <app-name> --profile=<profile>
     ```
     Verify the response includes `resources` with sql-warehouse, mas-endpoint, and database.

4. **Deploy:**
   ```bash
   databricks apps deploy <app-name> --source-code-path /Workspace/Users/<email>/demos/<app-name>/app --profile=<profile>
   ```

5. **If resources were missing in step 3**, register them now:
   ```bash
   databricks apps update <app-name> --json '{
     "resources": [
       {"name": "sql-warehouse", "sql_warehouse": {"id": "<id>", "permission": "CAN_USE"}},
       {"name": "mas-endpoint", "serving_endpoint": {"name": "mas-<tile>-endpoint", "permission": "CAN_QUERY"}},
       {"name": "database", "database": {"instance_name": "<instance>", "database_name": "<db>", "permission": "CAN_CONNECT_AND_CREATE"}}
     ]
   }' --profile=<profile>
   ```
   Then **redeploy again** (PGHOST is only injected at deploy time).

6. **Wait for deployment** to reach RUNNING state.

7. **Verify health:**
   - Hit `/api/health` endpoint
   - Report status of all 3 checks (SDK, SQL warehouse, Lakebase)
   - If any fail, diagnose using CLAUDE.md troubleshooting table and suggest fixes

8. **Report:**
   ```
   Deploy complete.
   App URL: <url>
   Health:  <status>
   ```

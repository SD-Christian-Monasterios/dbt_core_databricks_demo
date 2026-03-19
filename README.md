# CI/CD Pipeline — Databricks Asset Bundle + dbt Core

This repository implements a CI/CD pipeline for deploying a **Databricks Asset Bundle (DAB)** containing dbt Core jobs, using GitHub Actions across two(three) environments: `dev`, `stg`, and `prod`.

---

## Repository Structure

```
repo/
├── .github/
│   └── workflows/
│       ├── action_on_PR.yml       # CI: runs on pull requests
│       └── action_on_MERGE.yml    # CD: runs on merge to dev or main
├── dab/                           # Databricks Asset Bundle
│   ├── databricks.yml             # Bundle config + environment targets
│   └── resources/
│       └── jobs.yml               # Job definitions
├── dbt/                           # dbt Core project
│   ├── dbt_project.yml
│   │── models/
│   └── profiles.yml               # For local test, is not part of the CICD
└── README.md
```

---

## Branching Strategy

```
feature/xyz  →  PR →  dev  →  PR →  main
```

| Branch | Maps to environment   |
|--------|-----------------------|
| `feature/*` | local / dev workspace |
| `dev` | dev (dev)             |
| `main` | production (prod)     |

PRs and merges trigger different pipeline steps depending on the **target branch**.

---

## Pipeline Overview

### On Pull Request (`action_on_PR.yml`)

| PR target branch | `dbt compile`            | `bundle validate` |
|-----------------|--------------------------|-------------------|
| `dev` | ✅ against dev warehouse  | ⏭️ skipped |
| `main` | ✅ against prod warehouse | ✅ against prod target |

### On Merge (`action_on_MERGE.yml`)

| Merged into | `bundle validate` | `bundle deploy` |
|-------------|-------------------|-----------------|
| `dev` | ✅ against dev     | ⏭️ skipped |
| `main` | ✅ against prod    | ✅ to prod (only if validate passes) |

> `bundle deploy` on merge to `main` only runs if `bundle validate` succeeds, enforced via `needs` in the workflow.

---

## Key Design Decisions

### Databricks is the dbt orchestrator
Databricks Jobs use **dbt task types** to execute the dbt project. The CI/CD pipeline only deploys job definitions — it never runs `dbt build` directly. Databricks handles dbt execution on its own schedule after deployment.

### `bundle deploy` ≠ job execution
Running `databricks bundle deploy` updates the job definitions in the Databricks workspace. It does **not** trigger the jobs. Jobs run on their configured cron schedule (For Instance: `0 0 11 * * ?` UTC by default).

### dbt compile on CI — no model materialization
`dbt compile` is used in CI only to validate Jinja syntax and SQL structure. It requires a live warehouse connection but does **not** write anything to the catalog. For actual model materialization, the Databricks job uses `dbt build`.

### `DATABRICKS_HOST` format differs by tool
| Context | Format |
|---------|--------|
| Databricks CLI / `databricks.yml` | `https://dbc-xxxxx.cloud.databricks.com` |
| dbt `profiles.yml` (`host:` field) | `dbc-xxxxx.cloud.databricks.com` (no `https://`) |

The workflows handle this automatically: `DATABRICKS_HOST_DEV` / `DATABRICKS_HOST_PROD` are stored as bare hostnames in GitHub Variables, and `https://` is prepended only where the CLI requires it.

### Bundle variables are injected at deploy time
`warehouse_id` and `git_url` are not hardcoded in `jobs.yml`. They are declared as variables in `databricks.yml` and passed via `--var` flags in the GitHub Actions workflow steps. This keeps environment-specific values out of the codebase.

### Job names are environment-scoped
Jobs are named `dbt-demo-job-${bundle.target}` so each environment (`dev`, `stg`, `prod`) gets its own independent job in the Databricks workspace, avoiding naming conflicts.

### `git_branch` per target
Each bundle target points the Databricks job to a different branch:

| Target | Git branch |
|--------|-----------|
| `dev` | `dev` |
| `stg` | `dev` |
| `prod` | `main` |

This ensures that when a Databricks job runs in production, it always pulls dbt code from `main`.

---

## GitHub Actions — Required Variables and Secrets

Configure these in `Settings → Secrets and variables → Actions` in your GitHub repository.

### Variables (non-sensitive)

| Variable                    | Description | Example |
|-----------------------------|-------------|---------|
| `DATABRICKS_HOST_DEV`       | Bare hostname of the staging Databricks workspace | `dbc-xxxxxx-stg.cloud.databricks.com` |
| `DATABRICKS_HOST_PROD`      | Bare hostname of the production Databricks workspace | `dbc-xxxxxx-prod.cloud.databricks.com` |
| `DATABRICKS_HTTP_PATH_DEV`  | HTTP path of the staging SQL warehouse | `/sql/1.0/warehouses/xxxxxxxx` |
| `DATABRICKS_HTTP_PATH_PROD` | HTTP path of the production SQL warehouse | `/sql/1.0/warehouses/xxxxxxxx` |
| `WAREHOUSE_ID_DEV`          | Warehouse ID used by the Databricks job in staging | `c4d20a2db40ba654` |
| `WAREHOUSE_ID_PROD`         | Warehouse ID used by the Databricks job in production | `a1b2c3d4e5f6g7h8` |
| `GIT_URL`                   | Full HTTPS URL of this GitHub repository | `https://github.com/org/repo.git` |

### Secrets (sensitive)

| Secret                  | Description |
|-------------------------|-------------|
| `DATABRICKS_TOKEN_DEV`  | Personal access token for the staging Databricks workspace |
| `DATABRICKS_TOKEN_PROD` | Personal access token for the production Databricks workspace |

> **Note:** Tokens should be service principal tokens in production environments, not personal access tokens. (TODO<---)

---

## dbt profiles.yml — CI only

The `profiles.yml` used during CI is generated dynamically within the workflow and is never committed to the repository. It uses a dedicated `dbt_ci` schema to avoid interfering with dev or production data.

```yaml
dbt_core_databricks_demo:
  target: ci
  outputs:
    ci:
      type: databricks
      host: "<DATABRICKS_HOST>"         # injected by workflow
      http_path: "<DATABRICKS_HTTP_PATH>" # injected by workflow
      token: "<DATABRICKS_TOKEN>"       # injected by workflow
      schema: dbt_ci
      threads: 4
```

---

## Local Development

For local bundle operations, configure your Databricks CLI credentials in `~/.databrickscfg`:

```ini
[DEFAULT]
host  = https://dbc-xxxxx.cloud.databricks.com
token = dapiXXXXXXXX
```

Then run bundle commands targeting the `dev` environment (default):

```bash
cd dab
databricks bundle validate
databricks bundle deploy
```

For dbt local development and testing, create your own `dbt/profiles.yml` pointing to your personal dev schema.
Then run commands targeting the `dev` environment (default):

```bash
cd dbt
dbt deps
dbt compile
dbt debug
dbt build
```

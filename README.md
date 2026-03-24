# CI/CD Pipeline — Databricks Asset Bundle + dbt Core

This repository implements a CI/CD pipeline for deploying a **Databricks Asset Bundle (DAB)** containing dbt Core jobs, using GitHub Actions across two environments: `dev` and `prod`.

---

## Repository Structure

```
repo/
├── .github/
│   └── workflows/
│       ├── action_on_PR.yml         # CI: runs on every pull request
│       ├── action_on_MERGE.yml      # CD: runs on merge to dev or main
│       └── check_source_branch.yml  # Branch protection: enforces PR source
├── dab/                             # Databricks Asset Bundle
│   ├── databricks.yml               # Bundle config + environment targets
│   └── resources/
│       └── jobs.yml                 # Job definitions
├── dbt/                             # dbt Core project
│   ├── dbt_project.yml
│   └── models/
└── README.md
```

---

## Environments

This pipeline uses **two environments only** — there is no staging or QA environment.

| Environment | Databricks workspace | Branch |
|-------------|---------------------|--------|
| `dev` | DEV workspace | `dev` |
| `prod` | PROD workspace | `main` |

---

## Branching Strategy

```
feature/xyz  →  PR →  dev  →  PR →  main
```

| Branch | Purpose |
|--------|---------|
| `feature/*` | Individual development work |
| `dev` | Integration branch, maps to DEV workspace |
| `main` | Production branch, maps to PROD workspace |

PRs can only be merged by an authorized team member after all required checks pass. PRs to `main` are restricted to originate **only from the `dev` branch** — direct PRs from feature branches to `main` are blocked.

---

## Pipeline Overview

### On Pull Request (`action_on_PR.yml`)

The CI workflow runs on **every PR regardless of which files changed**. This ensures the merge button is never left in a blocked/orphan state when non-code files (like the README) are modified.

| PR target | `dbt compile` | `bundle validate` |
|-----------|--------------|-------------------|
| `dev` | ✅ against DEV warehouse | ⏭️ skipped |
| `main` | ✅ against PROD warehouse | ✅ against prod target |

### On Merge (`action_on_MERGE.yml`)

The CD workflow only triggers when `dbt/**` or `dab/**` files are changed. A merge that only touches documentation will not trigger a deploy.

| Merged into | `bundle validate` | `bundle deploy` |
|-------------|-------------------|-----------------|
| `dev` | ✅ against DEV | ⏭️ skipped |
| `main` | ✅ against PROD | ✅ to prod (only if validate passes) |

> `bundle deploy` only runs if `bundle validate` succeeds, enforced via `needs` in the workflow.

---

## Key Design Decisions

### Databricks is the dbt orchestrator
Databricks Jobs use **dbt task types** to execute the dbt project. The CI/CD pipeline only deploys job definitions — it never runs `dbt build` directly. Databricks handles dbt execution on its own schedule after deployment.

### `bundle deploy` ≠ job execution
Running `databricks bundle deploy` updates the job definitions in the Databricks workspace. It does **not** trigger the jobs. Jobs run on their configured cron schedule (`0 0 8 * * ?` UTC by default).

### dbt compile on CI — no model materialization
`dbt compile` validates Jinja syntax and SQL structure. It requires a live warehouse connection but does **not** write anything to the catalog. It uses a dedicated `dbt_ci` schema to avoid any interference with dev or prod data.

### No paths filter on CI
The CI workflow (`action_on_PR.yml`) intentionally has no `paths` filter. If paths were filtered, a PR that only modifies the README would never trigger the required status checks, leaving the merge button permanently blocked. The CD workflow (`action_on_MERGE.yml`) does use a paths filter since a skipped deploy on a README change is acceptable.

### `DATABRICKS_HOST` format differs by tool

| Context | Format |
|---------|--------|
| Databricks CLI / `databricks.yml` | `https://dbc-xxxxx.cloud.databricks.com` |
| dbt `profiles.yml` (`host:` field) | `dbc-xxxxx.cloud.databricks.com` (no `https://`) |

GitHub Variables store bare hostnames. The workflows prepend `https://` only where the CLI requires it.

### Bundle variables are injected at deploy time
`warehouse_id` and `git_url` are not hardcoded in `jobs.yml`. They are declared as variables in `databricks.yml` and passed via `--var` flags at runtime. This keeps environment-specific values out of the codebase.

### `git_branch` per target
Each bundle target points the Databricks job to a specific branch:

| Target | Git branch |
|--------|-----------|
| `dev` | `dev` |
| `prod` | `main` |

This ensures the Databricks job always pulls dbt code from the correct branch for each environment.

---

## GitHub Actions — Required Variables and Secrets

Configure these in `Settings → Secrets and variables → Actions`.

### Variables (non-sensitive)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABRICKS_HOST_DEV` | Bare hostname of the DEV Databricks workspace | `dbc-xxxxxx-dev.cloud.databricks.com` |
| `DATABRICKS_HOST_PROD` | Bare hostname of the PROD Databricks workspace | `dbc-xxxxxx-prod.cloud.databricks.com` |
| `DATABRICKS_HTTP_PATH_DEV` | HTTP path of the DEV SQL warehouse | `/sql/1.0/warehouses/xxxxxxxx` |
| `DATABRICKS_HTTP_PATH_PROD` | HTTP path of the PROD SQL warehouse | `/sql/1.0/warehouses/xxxxxxxx` |
| `WAREHOUSE_ID_DEV` | Warehouse ID used by the Databricks job in DEV | `c4d20a2db40ba654` |
| `WAREHOUSE_ID_PROD` | Warehouse ID used by the Databricks job in PROD | `a1b2c3d4e5f6g7h8` |
| `GIT_URL` | Full HTTPS URL of this GitHub repository | `https://github.com/org/repo.git` |

### Secrets (sensitive)

| Secret | Description |
|--------|-------------|
| `DATABRICKS_TOKEN_DEV` | Personal access token for the DEV Databricks workspace |
| `DATABRICKS_TOKEN_PROD` | Personal access token for the PROD Databricks workspace |

> **Note:** Tokens should be service principal tokens in production environments, not personal access tokens.

---

## dbt profiles.yml — CI only

The `profiles.yml` used during CI is generated dynamically within the workflow and is **never committed to the repository**. 
```yaml
dbt_core_databricks_demo:
  target: ci
  outputs:
    ci:
      type: databricks
      host: "<DATABRICKS_HOST>"            # injected by workflow, no https://
      http_path: "<DATABRICKS_HTTP_PATH>"  # injected by workflow
      token: "<DATABRICKS_TOKEN>"          # injected by workflow
      schema: default
      threads: 4
```

---

## Branch Protection Rules

Branch protection is enforced through two mechanisms working together: a **GitHub Actions workflow** that validates the source branch, and a **GitHub Ruleset** that blocks the merge button until all required checks pass.

### Workflow — `check_source_branch.yml`

Validates that any PR targeting `main` originates from the `dev` branch. The workflow fails with a clear message if the source branch is anything other than `dev`.

The workflow alone produces a visible failure on the PR but does **not** block the merge button by itself. The Ruleset below is required to enforce the block.

### GitHub Ruleset configuration

```
Settings → Rules → Rulesets → New branch ruleset

Ruleset name:  protect-main
Enforcement:   Active
Target:        main

Rules to enable:
  ✅ Require a pull request before merging
  ✅ Require status checks to pass
       → Add check: "Source branch must be dev"
       → Add check: "dbt compile"
       → Add check: "Bundle validate (prod)"
```

> **Important:** Status check names must match the `name:` field of the **job** in the workflow exactly — not the workflow name or step name. These checks only appear in the GitHub search box after the workflow has run at least once.

### Result

| Scenario | PR opens | Merge allowed |
|----------|----------|---------------|
| `feature/xyz` → `main` | ✅ | ❌ blocked — source branch check fails |
| `dev` → `main` (checks failing) | ✅ | ❌ blocked — required checks not green |
| `dev` → `main` (all checks pass) | ✅ | ✅ merge allowed |

---

## Local Development

---- >>>> TODO: ADD manual steps for DEMO. <<<<<-----
# Parallel pipeline setup

Run **multiple independent data chains at the same time** by giving each chain a unique `WORKLOAD_ID`.

## After upgrading Jenkinsfiles (important)

1. **Push** the latest repo to GitHub.
2. On **each** job (`p1-bq-to-gcs` … `p4-gcs-to-bq`), use **Build with Parameters** — not plain **Build Now** on the first run after the upgrade.
3. Set **`WORKLOAD_ID`** = **`default`** to keep the same behavior as before (flat `bq-exports/`, table `target_table`).
4. Run **one successful build per job** with `default` before using the parallel orchestrator or new workload ids.
5. In job **Configure**, remove any **Parameters** you added manually in the UI (let the Jenkinsfile define them).

If builds fail with empty workload paths, pull the commit that adds the `environment { WORKLOAD_ID = ... }` block.

## How it works

| `WORKLOAD_ID` | GCS paths | MySQL table | Still uses credentials |
|---------------|-----------|-------------|-------------------------|
| `default` | Legacy: `bq-exports/`, `sql-exports/` (flat) | `target_table` | Same Jenkins credentials |
| `customers` | `bq-exports/customers/`, `sql-exports/customers/` | `target_customers` | Same |
| `orders` | `bq-exports/orders/`, `sql-exports/orders/` | `target_orders` | Same |

Each workload writes a `LATEST` pointer file in its GCS folder so P2/P4 do not pick another workload's CSV.

**Inside one chain:** still sequential `P1 -> P2 -> P3 -> P4`.

**Across chains:** run different `WORKLOAD_ID` values in parallel.

## Before first parallel run

For each new `WORKLOAD_ID` (example `customers`):

1. Create BigQuery source table (or use `OVERRIDE_SOURCE_TABLE` on P1).
2. Create MySQL table `target_customers` matching the CSV schema (after you know columns from one P1 export).
3. Create BigQuery destination `dest_customers` (or pass `OVERRIDE_DEST_TABLE` on P4).

## Option A — Manual parallel (four jobs × N workloads)

Run with **Build with Parameters** on each job, same `WORKLOAD_ID` for all four:

```text
WORKLOAD_ID=customers  ->  p1, then p2, then p3, then p4
WORKLOAD_ID=orders     ->  p1, then p2, then p3, then p4   (can overlap in time with customers)
```

## Option B — Orchestrator job (recommended)

1. Install plugin: **Pipeline: Build Step** (if not already present).
2. New Pipeline job: `parallel-orchestrator`
3. Script Path: `Jenkinsfile.parallel-orchestrator`
4. Build with Parameters:

   `WORKLOAD_IDS=customers,orders`

This runs two full chains **in parallel** (each chain sequential internally).

### Different BQ tables per workload

On manual runs, set optional parameters:

| Job | Parameter | Example |
|-----|-----------|---------|
| P1 | `OVERRIDE_SOURCE_TABLE` | `source_customers` |
| P4 | `OVERRIDE_DEST_TABLE` | `dest_customers` |

Orchestrator currently passes only `WORKLOAD_ID`; extend `Jenkinsfile.parallel-orchestrator` if you need per-workload table overrides.

## Agent capacity

Parallel chains share agents labeled `gcp-slave`. With 2 agents and 2 parallel chains, both can run simultaneously. Add agents or limit parallel workload count if queues grow.

## What not to do

- Do not run two P2 jobs with the same `WORKLOAD_ID` at once.
- Do not mix `WORKLOAD_ID` across P1–P4 (always use the same id for one chain).

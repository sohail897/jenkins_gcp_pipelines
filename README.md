# Jenkins on GCP: master–agent CI and BigQuery ↔ GCS ↔ Cloud SQL pipelines

This repository contains four **declarative** Jenkins pipelines and helper scripts that move data in order:

1. **Pipeline 1** (`Jenkinsfile.bq-to-gcs`): BigQuery → GCS (`bq-exports/`)
2. **Pipeline 2** (`Jenkinsfile.gcs-to-cloudsql`): GCS → Cloud SQL (MySQL). **Requires Pipeline 1** to have produced at least one `bq-exports/*.csv` object.
3. **Pipeline 3** (`Jenkinsfile.cloudsql-to-gcs`): Cloud SQL → GCS (`sql-exports/`). Expects `target_table` to exist and be populated (for example by Pipeline 2).
4. **Pipeline 4** (`Jenkinsfile.gcs-to-bq`): GCS → BigQuery. **Requires Pipeline 3** to have produced at least one `sql-exports/*.csv` object.

All pipeline steps run on agents labeled **`gcp-slave`**. The Jenkins controller must be configured with **0 executors** so it never runs pipeline steps.

## Target architecture (GCP + Jenkins)

| Role | GCE shape | OS | Notes |
|------|-----------|----|--------|
| Jenkins controller | `e2-medium` | Ubuntu 22.04 LTS | Jenkins UI, `executors = 0`, SSH server for inbound agents |
| Jenkins agent ×2 | `e2-standard-2` | Ubuntu 22.04 LTS | Label: `gcp-slave`, outbound SSH to controller, tooling from `scripts/setup_agent.sh` |

**GCP service account (example name):** `jenkins-pipeline-sa` with roles:

- BigQuery Admin  
- Storage Admin  
- Cloud SQL Admin  
- Cloud SQL Client  

Create a JSON key for this account and store it only in Jenkins (credential `gcp-sa-key`). Grant the same project access your Cloud SQL instance needs (private IP connectivity from agent subnets, or authorized networks if applicable).

## Prerequisites: enable GCP APIs

In your GCP project, enable at least:

- **BigQuery API** (`bigquery.googleapis.com`)
- **Cloud Storage API** (`storage.googleapis.com`)
- **Cloud SQL Admin API** (`sqladmin.googleapis.com`)
- **Compute Engine API** (`compute.googleapis.com`)

Use Cloud Console **APIs & Services → Library**, or:

```bash
gcloud services enable bigquery.googleapis.com storage.googleapis.com sqladmin.googleapis.com compute.googleapis.com --project=YOUR_PROJECT_ID
```

## GCS layout

| Prefix | Written by | Read by |
|--------|------------|---------|
| `gs://BUCKET/bq-exports/*.csv` | Pipeline 1 | Pipeline 2 |
| `gs://BUCKET/sql-exports/*.csv` | Pipeline 3 | Pipeline 4 |

Create the bucket once; pipelines assume these prefixes exist or can be created by export/upload commands.

## Cloud SQL and table name

Pipelines 2–4 use the MySQL table name **`target_table`**. Create it in your database before running Pipeline 2 so the CSV schema matches (columns aligned with the BigQuery extract from Pipeline 1). Pipeline 2’s CSV validation treats the **first column** as the primary key column: it must not contain nulls.

## Jenkins controller setup (summary)

1. Provision an Ubuntu 22.04 VM (`e2-medium`), static internal IP recommended for agent SSH targets.
2. Install Jenkins (LTS), **OpenJDK 21** (current Jenkins LTS requires Java 21+), and open inbound **8080** (or your chosen UI port) from your admin network only. Set `JAVA=/usr/lib/jvm/java-21-openjdk-amd64/bin/java` in `/etc/default/jenkins` if the service still picks Java 17.
3. Under **Manage Jenkins → Nodes → Built-In Node → Configure**, set **Number of executors** to **0** and save. The built-in node must not run jobs.
4. Install plugins as needed: **SSH Agent**, **Pipeline**, **Credentials Binding** (usually bundled).
5. Create credentials and agent nodes (below).

## Register SSH build agents (Manage Jenkins → Nodes)

For **each** agent VM:

1. On the agent, run `scripts/setup_agent.sh` (as a user with `sudo`). Ensure the controller’s SSH **public** key is in `/home/jenkins/.ssh/authorized_keys` for the `jenkins` user (paste from the key pair whose **private** key is stored in Jenkins as `gcp-slave-ssh-key`).
2. In Jenkins: **Manage Jenkins → Nodes → New Node**.
3. **Name:** e.g. `gcp-agent-1` (unique per VM). **Type:** Permanent Agent.
4. **# of executors:** `2` (or `1` per your capacity). **Remote root directory:** `/home/jenkins` (or your chosen workspace root).
5. **Labels:** `gcp-slave` (both agents share this label).
6. **Launch method:** Launch agents via SSH.  
   - **Host:** agent VM IP or DNS  
   - **Credentials:** select `gcp-slave-ssh-key` (SSH Username with private key; username `jenkins`)  
   - **Host Key Verification Strategy:** Non verifying Verification Strategy (acceptable only in controlled lab setups; prefer known hosts in production).
7. Save and connect; confirm the agent is **online** before running pipelines.

## Jenkins credentials (create each ID exactly)

Create under **Manage Jenkins → Credentials** (appropriate domain/folder):

| Credential ID | Kind | Value / usage |
|---------------|------|----------------|
| `gcp-sa-key` | Secret file | Upload JSON key for `jenkins-pipeline-sa` |
| `gcs-bucket-name` | Secret text | GCS bucket name (no `gs://` prefix) |
| `bq-project-id` | Secret text | GCP project ID for BigQuery |
| `bq-dataset` | Secret text | BigQuery dataset id |
| `bq-table-source` | Secret text | Source table for Pipeline 1 (`dataset.table` is built as `${BQ_PROJECT}:${BQ_DATASET}.${BQ_TABLE_SOURCE}`) |
| `bq-table-dest` | Secret text | Destination table id for Pipeline 4 (table id only; full name is `${BQ_PROJECT}:${BQ_DATASET}.${BQ_TABLE_DEST}`) |
| `cloudsql-host` | Secret text | Cloud SQL **private IP** (or host your network can reach) |
| `cloudsql-db` | Secret text | MySQL database name |
| `cloudsql-user` | Secret text | MySQL username |
| `cloudsql-pass` | Secret text | MySQL password |
| `gcp-slave-ssh-key` | SSH Username with private key | Username `jenkins`, private key matching agent `authorized_keys` |

**`gcp-slave-ssh-key`** is for the SSH connection from the controller to agents, not for GCP APIs. API access uses `gcp-sa-key` on the agent via `gcloud auth activate-service-account`.

## SCM jobs for this repository

Create four **Pipeline** jobs (or a Multibranch Pipeline) pointing at this repo, each with its own **Script Path**:

- Job A → `Jenkinsfile.bq-to-gcs`  
- Job B → `Jenkinsfile.gcs-to-cloudsql`  
- Job C → `Jenkinsfile.cloudsql-to-gcs`  
- Job D → `Jenkinsfile.gcs-to-bq`  

Ensure the repository is checked out on the agent so `scripts/` is available for Pipelines 2 and 3.

## Run order

Run jobs in strict sequence:

**P1 → P2 → P3 → P4**

Pipeline 2 fails fast if no `bq-exports/*.csv` exists (you must run Pipeline 1 first). Pipeline 4 fails fast if no `sql-exports/*.csv` exists (you must run Pipeline 3 first).

Optional hardening: use the **Build Pipeline** or **Parameterized Trigger** plugin to chain jobs automatically after success.

## Agent VM bootstrap

On each agent (after base Ubuntu 22.04):

```bash
sudo bash scripts/setup_agent.sh
```

Then install the controller’s SSH public key for user `jenkins`. Confirm `gcloud`, `bq`, `gsutil`, `mysql`, and `python3` work when SSH’d in as `jenkins`.

Jenkins SSH steps often run **non-login** shells, so `~/.bashrc` may not apply. On each agent node in Jenkins, under **Configure → Node Properties → Environment variables**, add `PATH` with value `/home/jenkins/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` (or prepend `/home/jenkins/.local/bin` to the agent’s existing `PATH`). That ensures `pymysql` and `pandas` installed with `pip install --user` are importable.

## Troubleshooting

### Agent offline in Jenkins

- From the controller: `ssh -i PRIVATE_KEY jenkins@AGENT_IP` and fix firewall, routes, or SSH keys.  
- Verify the agent Java process can reach the controller if using inbound agents (here we use **SSH** from controller to agent, so controller outbound to agent **port 22** must be allowed).  
- Check Jenkins agent log for auth or path errors.

### `bq extract` permission denied

- Confirm `gcp-sa-key` is the JSON for `jenkins-pipeline-sa` with **BigQuery Admin** and **Storage Admin**.  
- Ensure the bucket is in the same or a permitted project and the SA has `storage.objects.create` on `bq-exports/`.  
- Re-run **Authenticate** stage or `gcloud auth activate-service-account` manually on the agent to verify the key.

### Cloud SQL authentication failed

- Validate `cloudsql-host`, `cloudsql-db`, `cloudsql-user`, `cloudsql-pass` in Jenkins match the instance.  
- Ensure the agent VPC can reach the **private IP** (VPC peering / subnet).  
- For SSL requirements, extend the scripts to pass `--ssl-mode` as needed.

### GCS file not found (`gsutil ls` empty or `cp` fails)

- Run pipelines in order (P1 before P2, P3 before P4).  
- Confirm `gcs-bucket-name` and object prefixes (`bq-exports/`, `sql-exports/`).  
- List manually on an agent: `gsutil ls gs://BUCKET/bq-exports/` and `gs://BUCKET/sql-exports/`.

## File layout

```text
jenkins-gcp-pipelines/
├── Jenkinsfile.bq-to-gcs
├── Jenkinsfile.gcs-to-cloudsql
├── Jenkinsfile.cloudsql-to-gcs
├── Jenkinsfile.gcs-to-bq
├── scripts/
│   ├── load_gcs_to_sql.py
│   ├── export_sql_to_csv.py
│   └── setup_agent.sh
└── README.md
```

Each `Jenkinsfile*` in this repo is **45 lines** by design; if you edit them, re-check line count and Groovy syntax.

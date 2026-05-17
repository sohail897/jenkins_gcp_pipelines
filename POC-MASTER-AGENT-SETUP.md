# POC: Jenkins controller + GCP SSH agents

Concise record of how this environment was brought up. **Insert your screenshots** where noted (`[Screenshot: …]`).

## 1. Architecture

| Role | GCE | OS | Purpose |
|------|-----|----|-----------|
| **Controller** | e.g. `e2-medium` | Ubuntu 22.04 LTS | Jenkins UI only; **0 executors** on built-in node |
| **Agent ×2** | e.g. `e2-standard-2` | Ubuntu 22.04 LTS | Label **`gcp-slave`**; all pipeline steps run here |

Controller connects to agents over **SSH** (TCP 22) using credential **`gcp-slave-ssh-key`**.

---

## 2. Controller VM (GCP)

**[Screenshot: VM list — `jenkins-controller`, zone, internal/external IP]**

- Image: **Ubuntu 22.04 LTS** (`ubuntu-os-cloud`, `ubuntu-2204-lts`).
- Open **TCP 8080** to your admin IP (custom firewall rule + network tag on the controller VM).  
  *Note: “HTTP/HTTPS traffic” toggles only open 80/443, not 8080.*

---

## 3. Java 21 + Jenkins (controller)

Current Jenkins LTS from `pkg.jenkins.io` requires **Java 21+** (not 17).

**[Screenshot: `java -version` and Jenkins UI reachable on `:8080`]**

```bash
sudo apt-get update -y
sudo apt-get install -y fontconfig openjdk-21-jre-headless curl gnupg

curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key | sudo gpg --dearmor -o /usr/share/keyrings/jenkins-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.gpg] https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list >/dev/null

sudo apt-get update -y
sudo apt-get install -y jenkins
```

If the service still picks Java 17:

```bash
grep -E '^JAVA=' /etc/default/jenkins || echo 'JAVA=/usr/lib/jvm/java-21-openjdk-amd64/bin/java' | sudo tee -a /etc/default/jenkins
sudo systemctl restart jenkins
```

Initial admin password:

```bash
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```

---

## 4. Built-in node: no builds on controller

**[Screenshot: Built-In Node → Configure → Executors = 0]**

**Manage Jenkins → Nodes → Built-In Node → Configure** → **# of executors** = **0** → Save.

---

## 5. Agent VMs + firewall (GCP)

**[Screenshot: `jenkins-agent-1` / `jenkins-agent-2` with internal IPs]**

Create two VMs (same VPC/zone pattern as your design). Allow **SSH from controller to agents** using **source tag** on the controller and **target tag** on agents, for example:

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export NETWORK="default"
export ZONE="us-central1-a"

gcloud config set project "${PROJECT_ID}"

gcloud compute firewall-rules create allow-ssh-from-jenkins-controller-to-agents \
  --network="${NETWORK}" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-tags=jenkins-ctrl \
  --target-tags=gcp-agent \
  --description="SSH: controller tag -> agent tag"
```

Ensure the **controller** has tag `jenkins-ctrl` and both **agents** have tag `gcp-agent` (or match whatever you used in the rule).

---

## 6. Agent bootstrap

On **each** agent (as `ubuntu` or your admin user), run the repo script:

**[Screenshot: terminal showing `Agent setup complete`]**

```bash
sudo bash scripts/setup_agent.sh
```

This installs Java 21, `mysql-client`, `pip` user packages (`pymysql`, `pandas`, GCP clients), `gcloud` CLI, and user **`jenkins`** with `~/.ssh` permissions.

---

## 7. SSH keypair (controller → `jenkins` on agents)

On the **controller** (as your login user):

**[Screenshot: optional — redact key material]**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/jenkins_agent_key -N "" -C "jenkins-controller-to-agents"
chmod 600 ~/.ssh/jenkins_agent_key
cat ~/.ssh/jenkins_agent_key.pub
```

On **each agent**, append that **one-line public key** to `jenkins`’s `authorized_keys`:

```bash
sudo install -d -o jenkins -g jenkins -m 0700 /home/jenkins/.ssh
echo 'PASTE_PUBLIC_KEY_LINE_HERE' | sudo tee -a /home/jenkins/.ssh/authorized_keys
sudo chown jenkins:jenkins /home/jenkins/.ssh/authorized_keys
sudo chmod 600 /home/jenkins/.ssh/authorized_keys
```

Test from **controller** (use **internal** agent IPs if same VPC):

```bash
ssh -i ~/.ssh/jenkins_agent_key -o StrictHostKeyChecking=accept-new jenkins@AGENT_INTERNAL_IP 'whoami && hostname'
```

---

## 8. Jenkins `known_hosts` (fixes “No Known Hosts file”)

Jenkins runs as OS user **`jenkins`**. Populate **`/var/lib/jenkins/.ssh/known_hosts`** using the **same hostnames/IPs** you will put in the Jenkins node **Host** field.

**[Screenshot: successful agent connection in node log]**

```bash
export AGENT1_IP="10.x.x.5"   # replace with your agent 1 IP/hostname
export AGENT2_IP="10.x.x.6"   # replace with your agent 2 IP/hostname

sudo mkdir -p /var/lib/jenkins/.ssh
sudo chown -R jenkins:jenkins /var/lib/jenkins/.ssh
sudo chmod 700 /var/lib/jenkins/.ssh

sudo -u jenkins bash -c "ssh-keyscan -H ${AGENT1_IP} ${AGENT2_IP} > /var/lib/jenkins/.ssh/known_hosts"
sudo chown jenkins:jenkins /var/lib/jenkins/.ssh/known_hosts
sudo chmod 644 /var/lib/jenkins/.ssh/known_hosts

sudo -u jenkins test -r /var/lib/jenkins/.ssh/known_hosts && echo OK
```

*Alternative for labs:* node **Host Key Verification Strategy** = **Non verifying** (no `known_hosts` file required).

---

## 9. Jenkins UI: credential + nodes

**[Screenshot: Credentials — `gcp-slave-ssh-key` (kind SSH, user `jenkins`)]**  
**[Screenshot: Nodes — `gcp-agent-1` / `gcp-agent-2` online, label `gcp-slave`]**

1. **Manage Jenkins → Credentials** → add **SSH Username with private key**  
   - **ID:** `gcp-slave-ssh-key`  
   - **Username:** `jenkins`  
   - **Private key:** contents of `jenkins_agent_key` (or “from file on controller” readable by user `jenkins`).

2. **Manage Jenkins → Nodes → New Node** (per agent):  
   - **Launch via SSH**  
   - **Host** = same IP as in `known_hosts` (prefer **internal** IP)  
   - **Remote root directory:** `/home/jenkins`  
   - **Labels:** `gcp-slave`  
   - **Credentials:** `gcp-slave-ssh-key`

3. Optional per node — **Environment variables** → `PATH`:

```text
/home/jenkins/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

---

## 10. Swap warning (optional)

**[Screenshot: Nodes table showing “Free Swap Space: 0 B”]**

No swap on small GCE VMs is common. Add a swapfile only if you hit memory pressure; otherwise you can ignore the UI warning.

---

## 11. Data pipelines (this repo)

Add pipeline secrets (`gcp-sa-key`, `gcs-bucket-name`, BQ + Cloud SQL IDs, etc.) and four **Pipeline from SCM** jobs pointing at:

- `Jenkinsfile.bq-to-gcs`  
- `Jenkinsfile.gcs-to-cloudsql`  
- `Jenkinsfile.cloudsql-to-gcs`  
- `Jenkinsfile.gcs-to-bq`  

Run order: **P1 → P2 → P3 → P4**. Details and credential IDs: **`README.md`**.

---

## Checklist (copy for your appendix)

- [ ] Controller: Ubuntu 22.04, Java 21, Jenkins APT **2026** key, service up  
- [ ] Firewall: **8080** → controller (tagged)  
- [ ] Agents: script run, **`jenkins`** user + key in `authorized_keys`  
- [ ] Firewall: **22** controller tag → agent tag  
- [ ] Controller: `known_hosts` for Jenkins **or** non-verifying host key  
- [ ] Jenkins: `gcp-slave-ssh-key`, two SSH nodes, label **`gcp-slave`**, built-in **0** executors  
- [ ] Jenkins: pipeline credentials + four jobs  

---

*End of POC doc — add screenshots in place of `[Screenshot: …]` markers.*

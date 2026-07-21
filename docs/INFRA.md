# Infrastructure — AWS setup, zero-bill strategy, and deployment

You have the **AWS Free Tier** (12-month) + **$200 credit** + a **UPI card**
attached. This guide is written so your bill stays at **₹0** through the
pilot — every service below fits inside the free tier, and the credit is a
safety net for anything that leaks past.

---

## 0. AWS account hardening (do this before creating ANYTHING)

### 0.1 — Stop using root

The email you signed up with is the **root account**. It can delete
everything, change billing, close the account. Never use it day-to-day.

1. Console → **IAM** → Users → **Create user** → name it `vishal-admin`
2. Attach policy: `AdministratorAccess`
3. Enable **Console access** → set a password
4. Enable **MFA** on both the root account AND this new user
   (Console → IAM → Users → Security credentials → MFA → Authenticator app)
5. Sign out of root. Sign in as `vishal-admin` from now on.

### 0.2 — Set up billing alerts (the zero-bill safety net)

This is the single most important step. Do it now, before anything else.

1. Console → **Billing and Cost Management** → **Budgets** → Create budget
2. **Monthly cost budget** → amount: **$1** (yes, one dollar)
3. Alert thresholds: **$0.01 actual** + **$1 forecasted** → your email
4. Create a second budget: **$10** with alerts at $5 and $10 (catches
   anything the free tier didn't cover that hits your credit)

Now go to **Billing → Billing preferences**:
- ✅ Receive Free Tier Usage Alerts → your email
- ✅ Receive PDF Invoice By Email

### 0.3 — Verify your free tier status

Console → **Billing → Free Tier** → check it says "12 months" and shows
the expiry date. Note which services show usage vs limit — this is your
ongoing dashboard for staying at ₹0.

---

## 1. What's free (12 months) and what isn't

| Service | Free tier allowance | Our usage | Safe? |
|---|---|---|---|
| EC2 `t2.micro` or `t3.micro` | 750 hrs/mo (Linux) | 1 instance 24/7 = 730 hrs | ✅ |
| EBS (gp2/gp3) | 30 GB/mo | 20 GB | ✅ |
| RDS `db.t3.micro` Postgres | 750 hrs/mo, 20 GB storage, 20 GB backup | 1 instance 24/7 | ✅ |
| S3 | 5 GB, 20K GET, 2K PUT | backups only | ✅ |
| Data transfer OUT | 100 GB/mo (recently increased) | minimal | ✅ |
| CloudWatch | 10 custom metrics, 10 alarms | 2 alarms | ✅ |
| Elastic IP | free while attached to running instance | 1 | ✅ |

**Things that are NEVER free (avoid these):**
- NAT Gateway → $32/mo just to exist → **don't create one**
- Application Load Balancer → ~$16/mo minimum → **use Caddy instead**
- RDS Multi-AZ → doubles the RDS cost → **leave it off**
- Secrets Manager → $0.40/secret/mo → **use `.env` files for now**
- CloudWatch Logs (detailed) → metered → **use Grafana instead**

### The $200 credit

Credits apply **after** Free Tier. If a service is free-tier-covered, the
credit isn't touched. The credit is your insurance for:
- Any accidental overage (an instance left running in the wrong class)
- Services not covered by free tier (S3 beyond 5 GB, etc.)
- Experimental services you want to try

**Check credit balance:** Console → Billing → Credits → see remaining amount
and expiry date.

---

## 2. Network setup (VPC + security groups, no NAT)

Use the **default VPC** in `ap-south-1` (Mumbai). No custom VPC needed.

### Create security groups

Console → EC2 → Security Groups → Create:

**`sg-app`** (for the EC2 instance):
| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | My IP (`x.x.x.x/32`) | your laptop only |
| HTTP | 80 | `0.0.0.0/0` | Caddy handles TLS upgrade |
| HTTPS | 443 | `0.0.0.0/0` | Caddy auto-TLS |

**`sg-db`** (for the RDS instance):
| Type | Port | Source | Why |
|---|---|---|---|
| PostgreSQL | 5432 | `sg-app` | only EC2 can reach the DB |

Important: in the source field for `sg-db`, type `sg-` and select `sg-app`
from the dropdown. This is a security-group reference, not a CIDR — it means
"anything running with sg-app attached." This is how EC2 talks to RDS without
a NAT Gateway.

---

## 3. Create the RDS instance

Console → RDS → Create database:

| Setting | Value | Why |
|---|---|---|
| Engine | PostgreSQL 16 | our schema needs PG 14+ |
| Template | **Free tier** | keeps it at ₹0 |
| DB instance class | `db.t3.micro` | 2 vCPU, 1 GB — free tier eligible |
| Storage | 20 GB, gp2 | free tier max |
| Storage autoscaling | **OFF** | prevents surprise bills |
| Multi-AZ | **No** | would 2x the cost |
| Public access | **No** | reached only via EC2 or SSH tunnel |
| VPC security group | `sg-db` | the one you just created |
| Initial database name | `placement` | |
| Backup retention | 7 days | free (included in 20 GB backup allowance) |

Set a strong master password → **write it down** → you need it once in step 6.

Wait for status = `Available`, then copy the **Endpoint** hostname.

---

## 4. Launch the EC2 instance

Console → EC2 → Launch instance:

| Setting | Value |
|---|---|
| AMI | Ubuntu 24.04 LTS, **64-bit (x86)** |
| Instance type | `t3.micro` (free tier eligible) |
| Key pair | Create new → download the `.pem` → keep it safe |
| Network | Default VPC, same AZ as RDS if possible |
| Security group | `sg-app` |
| Storage | 20 GB gp3 |

Once running:
1. **Allocate an Elastic IP** → Associate it with this instance
   (EC2 → Elastic IPs → Allocate → Associate). Free while attached.
2. SSH in:

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<elastic-ip>
```

3. Install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # log out and back in for group change
```

4. Install psql (for the schema script):

```bash
sudo apt-get update && sudo apt-get install -y postgresql-client
```

---

## 5. DBeaver setup (your laptop → RDS via SSH tunnel)

Install DBeaver Community (free) from **dbeaver.io**.

New PostgreSQL connection:
- **Main tab:** Host = RDS endpoint · Port = 5432 · Database = `placement` ·
  Username = your RDS master username · Password = master password
- **SSH tab:** ✅ Use SSH Tunnel · Host = your Elastic IP · Port = 22 ·
  Username = `ubuntu` · Auth = Public Key · Private key = your `.pem`

Click **Test Connection**. You now have a full GUI over the real database
without ever exposing RDS to the public internet.

---

## 6. Deploy the code

### 6.1 — Get the code onto the EC2 box

```bash
# on EC2
git clone https://github.com/vishalaadee/Cohort.git
cd Cohort
cp .env.example .env
nano .env   # fill in ALL values (see comments in the file)
```

### 6.2 — Apply schema to RDS

```bash
chmod +x scripts/apply-schema-rds.sh
./scripts/apply-schema-rds.sh seed
# prompts for RDS master password (typed, never stored)
```

### 6.3 — Start the stack

```bash
cd infra
docker compose -f docker-compose.aws.yml up -d --build
```

### 6.4 — Verify

```bash
curl localhost/api/health        # {"status":"ok","db":"up"}
curl localhost/api/auth/config   # {"google_client_id":...}
```

Open `http://<elastic-ip>` in your browser → landing page.
Open `http://<elastic-ip>/app` → sign in with `admin@demo.ac.in` / `demo1234`.

---

## 7. Point a domain at it (optional, free with Cloudflare)

1. Buy a domain (₹99–800/year on Namecheap/GoDaddy/BigRock)
2. Move DNS to **Cloudflare** (free plan) — add the domain, update nameservers
3. Add an **A record**: `@` → your Elastic IP, proxy OFF (grey cloud) initially
4. Update `.env`: `SITE_ADDRESS=yourdomain.com`
5. Restart: `cd infra && docker compose -f docker-compose.aws.yml up -d`
6. Caddy auto-issues a Let's Encrypt certificate
7. Turn Cloudflare proxy ON (orange cloud) for CDN + DDoS protection

---

## 8. Monitoring

Two layers, both free:

**CloudWatch** (zero setup): RDS Console → your instance → Monitoring tab.
CPU, connections, storage, IOPS. Set two alarms:
- RDS free storage < 2 GB → SNS → your email
- EC2 CPU > 85% for 15 min → SNS → your email

**Grafana** (detailed): already running in Docker. Access via SSH tunnel:

```bash
ssh -i your-key.pem -L 3000:localhost:3000 ubuntu@<elastic-ip>
# then open localhost:3000 in your browser
```

Login with the credentials from `.env`. Import these dashboards by ID:
- `1860` — Node Exporter (host CPU/memory/disk)
- `9628` — PostgreSQL (connections, cache hits, transaction rate)
- `14282` — cadvisor (per-container resource usage)

---

## 9. Ongoing cost management — staying at ₹0

### Weekly check (~2 minutes)

Console → **Billing → Free Tier** → scan for any service showing usage
approaching the limit. Screenshot it, compare week over week.

### Monthly check (~5 minutes)

Console → **Billing → Bills** → confirm the total is $0.00. If anything
appears, it's usually one of:
- A **stopped EC2 instance still has an Elastic IP** → either restart the
  instance or release the IP ($3.60/mo otherwise)
- An **EBS snapshot** accumulated beyond 20 GB → delete old ones
- **Data transfer** spiked → check if something is pulling large files

### Things to never do (they break the zero-bill promise)

- Don't create a second EC2 or RDS instance (750 hrs is shared across ALL
  instances of that type)
- Don't enable RDS Multi-AZ
- Don't create a NAT Gateway
- Don't enable detailed CloudWatch monitoring (basic is free, detailed isn't)
- Don't leave the EC2 instance **stopped** for weeks — the EBS volume still
  bills, and a detached Elastic IP bills too
- Don't create an ALB

### When the 12-month free tier expires

Your billing alarm at $0.01 will fire immediately. At that point either:
1. Delete everything and redeploy on a cheaper host (Hetzner CAX11 ARM,
   ~€3.79/mo; or DigitalOcean $6/mo droplet)
2. If you have paying colleges by then, the revenue covers the ~$25–30/mo
   bill (EC2 ~$8 + RDS ~$14 + bits) — and your $200 credit buys another
   7+ months of runway on top

---

## 10. Peak infra evolution — grow without redesigning

```
                PILOT (now)                      GROWTH (when needed)
Client     Cloudflare free (DNS/CDN)       ->  same (maybe paid tier)
Entry      Caddy on the EC2 box            ->  ALB (or keep Caddy)
App        1x EC2 t3.micro, Compose        ->  2+ boxes or ECS Fargate
Database   RDS db.t3.micro, Single-AZ      ->  bigger class + Multi-AZ +
                                               read replica (console change)
Files      MinIO container (S3 API)        ->  real S3 (flip one env var)
Async      FastAPI BackgroundTasks         ->  SQS/Redis + worker container
Metrics    Prometheus+Grafana on the box   ->  own box, or managed Prometheus
Auth       Google ID-token + own JWTs      ->  add Keycloak if SAML needed
```

**Triggers to act** (not before): CPU >70% sustained → second box. RDS
storage alarm → class bump. First paying SLA → Multi-AZ + ALB. Until a
trigger fires, changing nothing is correct.

---

## 11. Deploying code updates

```bash
# on EC2
cd ~/Cohort
git pull origin main
cd infra
docker compose -f docker-compose.aws.yml up -d --build backend
# only rebuilds the backend container, everything else stays running
```

For schema changes: apply the migration from `migrations/` via DBeaver or
psql, then deploy the code.

---

## 12. Backup and recovery

RDS automated backups are already enabled (7-day retention from step 3).
For a manual snapshot: RDS Console → your instance → Actions → Take snapshot.

To restore: RDS → Snapshots → select → Restore → creates a new instance.
Update `RDS_HOST` in `.env` to point at the new instance, restart the stack.

**Test a restore at least once** before you onboard real colleges.

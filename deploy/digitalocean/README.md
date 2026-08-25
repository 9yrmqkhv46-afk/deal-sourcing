# Moving deal-sourcing to a DigitalOcean Droplet in Sydney (SYD1)

**Why a Droplet, not App Platform:** App Platform doesn't support the `syd1`
region at all (as of writing it's `ams`, `fra`, `nyc`, `sfo`, `sgp`, `blr`
only) — the ~$30/mo App Platform quote you were seeing was for a non-Sydney
region. A plain Droplet in `syd1` is the only DigitalOcean compute option
that's actually in Australia.

This app is separate from credit-portal (per your call to keep them as two
separate apps/Droplets), but its database doesn't have to be a second paid
cluster: **you can add a `deal_sourcing` database to the same `syd1` Managed
Postgres cluster you create for credit-portal** and just point this app's
`DATABASE_URL` at that database instead of provisioning a second cluster.
See credit-portal's `deploy/digitalocean/README.md` step 3 for creating the
cluster if you haven't already; the extra step below is specific to this app.

## 0. Prerequisites

Same as credit-portal's runbook: a DigitalOcean account, `doctl` (optional),
and a domain/subdomain you can point at this Droplet, e.g.
`deals.transformbiz.com.au`.

## 1. Create the Droplet (syd1)

This app is lightweight — the cheapest tier is genuinely enough:

```bash
doctl compute droplet create transformbiz-deal-sourcing \
  --region syd1 \
  --image ubuntu-24-04-x64 \
  --size s-1vcpu-1gb \
  --ssh-keys <your-ssh-key-fingerprint> \
  --wait
```

(Console equivalent: **Create → Droplets → Sydney (SYD1) → Ubuntu 24.04 →
Basic, Regular, 1 GB RAM / 1 vCPU ($6/mo)**.)

## 2. Point DNS at it

A record: `deals.transformbiz.com.au` → the Droplet's public IP.

## 3. Database

If you already created the shared `syd1` Postgres cluster for credit-portal,
just add a database + user on it for this app:

```bash
doctl databases db create <cluster-id> deal_sourcing
doctl databases user create <cluster-id> deal_sourcing_app
```

Grab that database's connection string from the console (**Databases →
cluster → Connection Details**, select `deal_sourcing`) and add this
Droplet to the cluster's trusted sources. That connection string is your
`DATABASE_URL` below.

(No existing production data to migrate here — this app hasn't been
deployed anywhere live yet, so there's nothing to `pg_dump`/`pg_restore`
the way credit-portal's Neon data needs to be.)

## 4. Deploy

```bash
ssh root@DROPLET_IP
curl -fsSL https://get.docker.com | sh
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx

git clone https://github.com/9yrmqkhv46-afk/deal-sourcing.git /opt/deal-sourcing
cd /opt/deal-sourcing/deploy/digitalocean
cp .env.example .env
nano .env   # set DATABASE_URL from step 3, and DOMAIN

docker compose --env-file .env up -d --build

cp nginx.conf.template /etc/nginx/sites-available/deal-sourcing
sed -i "s/DOMAIN_PLACEHOLDER/deals.transformbiz.com.au/g" /etc/nginx/sites-available/deal-sourcing
ln -s /etc/nginx/sites-available/deal-sourcing /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d deals.transformbiz.com.au
```

## 5. Verify

- `https://deals.transformbiz.com.au/api/health` → `{"status":"ok"}`
- Upload a test PDF/PPTX through the dashboard, confirm it shows up under
  "Uploaded documents" after a page refresh (confirms the syd1 database is
  wired up correctly, not just the app running).

## Redeploying after a code change

```bash
ssh root@DROPLET_IP
cd /opt/deal-sourcing && git pull
cd deploy/digitalocean && docker compose --env-file .env up -d --build
```

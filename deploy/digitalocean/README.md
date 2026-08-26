# Moving deal-sourcing to its own DigitalOcean Droplet in Sydney (SYD1)

**Why a Droplet, not App Platform:** App Platform doesn't support the `syd1`
region at all (as of writing it's `ams`, `fra`, `nyc`, `sfo`, `sgp`, `blr`
only) — the ~$30/mo App Platform quote you were seeing was for a non-Sydney
region. A plain Droplet in `syd1` is the only DigitalOcean compute option
that's actually in Australia.

This is a **separate app on its own separate Droplet** — fully independent
of credit-portal, with its own database cluster too. Nothing is shared
between the two.

## 0. Prerequisites

A DigitalOcean account, `doctl` (optional — the console works fine too), and
a domain/subdomain, e.g. `deals.transformbiz.com.au`.

## 1. Create the Droplet (syd1)

```bash
doctl compute droplet create transformbiz-deal-sourcing \
  --region syd1 \
  --image ubuntu-24-04-x64 \
  --size s-1vcpu-1gb \
  --ssh-keys <your-ssh-key-fingerprint> \
  --wait
```

(Console: **Create → Droplets → Sydney (SYD1) → Ubuntu 24.04 → Basic,
Regular, 1 GB RAM / 1 vCPU, ~$6/mo**.) Note the Droplet's public IP —
that's `DROPLET_IP` below.

## 2. Point DNS at it

A record: `deals.transformbiz.com.au` → `DROPLET_IP`.

## 3. Create its own database (syd1)

```bash
doctl databases create deal-sourcing-pg --engine pg --region syd1 --size db-s-1vcpu-1gb --num-nodes 1
doctl databases db create <cluster-id> deal_sourcing
doctl databases user create <cluster-id> deal_sourcing_app
```

(Console: **Create → Databases → PostgreSQL → Sydney (SYD1) → smallest
plan, ~$15/mo**, then add a database + user on it.)

Grab the connection string from **Databases → your cluster → Connection
Details** (select the `deal_sourcing` database) — that's `DATABASE_URL`
below. Add this Droplet to the database's **Trusted Sources** so it's
allowed to connect.

(No existing production data to migrate — this app hasn't been deployed
live anywhere yet.)

## 4. Deploy the app onto the Droplet

```bash
ssh root@DROPLET_IP
curl -fsSL https://get.docker.com | sh
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx

git clone https://github.com/9yrmqkhv46-afk/deal-sourcing.git /opt/deal-sourcing
cd /opt/deal-sourcing/deploy/digitalocean
cp .env.example .env
nano .env   # set DATABASE_URL from step 3, and DOMAIN=deals.transformbiz.com.au

docker compose --env-file .env up -d --build

cp nginx.conf.template /etc/nginx/sites-available/deal-sourcing
sed -i "s/DOMAIN_PLACEHOLDER/deals.transformbiz.com.au/g" /etc/nginx/sites-available/deal-sourcing
ln -s /etc/nginx/sites-available/deal-sourcing /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d deals.transformbiz.com.au
```

## 5. Verify

- `https://deals.transformbiz.com.au/api/health` → `{"status":"ok"}`
- Upload a test PDF/PPTX through the dashboard, refresh, confirm it shows up
  under "Uploaded documents."

## Redeploying after a code change

```bash
ssh root@DROPLET_IP
cd /opt/deal-sourcing && git pull
cd deploy/digitalocean && docker compose --env-file .env up -d --build
```

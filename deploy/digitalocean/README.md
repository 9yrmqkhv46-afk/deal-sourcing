# Moving deal-sourcing onto the syd1 Droplet (alongside credit-portal)

**Why a Droplet, not App Platform:** App Platform doesn't support the `syd1`
region at all (as of writing it's `ams`, `fra`, `nyc`, `sfo`, `sgp`, `blr`
only) — the ~$30/mo App Platform quote you were seeing was for a non-Sydney
region. A plain Droplet in `syd1` is the only DigitalOcean compute option
that's actually in Australia, and you already have one running credit-portal.

This app runs as a **second, independent set of containers on that same
Droplet** — it doesn't touch credit-portal's containers or Nginx config,
just adds its own alongside them. Its data goes into a second database on
the **same Managed Postgres cluster** credit-portal already uses (a
`deal_sourcing` database next to `credit_portal`), not a second cluster.

Everything below assumes Docker, Nginx and Certbot are already installed on
the Droplet from setting up credit-portal (`deploy/digitalocean/README.md`
in that repo). If any of the install commands below are re-run, they're
harmless no-ops on an already-set-up box.

## 1. Point DNS at the same Droplet

A record: `deals.transformbiz.com.au` → the **same** public IP credit-portal
already uses (no new server, so no new IP).

## 2. Add the database on the existing Postgres cluster

```bash
doctl databases db create <credit-portal's cluster-id> deal_sourcing
doctl databases user create <credit-portal's cluster-id> deal_sourcing_app
```

(Console equivalent: **Databases → your existing cluster → Databases tab →
Create database** → name it `deal_sourcing`, then **Users tab → Add user**.)

Grab that database's connection string from the console (**Connection
Details**, select `deal_sourcing` from the database dropdown) — that's your
`DATABASE_URL` below. The Droplet is already a trusted source on this
cluster from the credit-portal setup, so no firewall change needed.

(No existing production data to migrate here — this app hasn't been
deployed anywhere live yet, so there's nothing to `pg_dump`/`pg_restore`.)

## 3. Deploy the app

SSH into the Droplet you already have:

```bash
ssh root@DROPLET_IP

# Skip if already present from the credit-portal setup:
curl -fsSL https://get.docker.com | sh
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx

git clone https://github.com/9yrmqkhv46-afk/deal-sourcing.git /opt/deal-sourcing
cd /opt/deal-sourcing/deploy/digitalocean
cp .env.example .env
nano .env   # set DATABASE_URL from step 2, and DOMAIN=deals.transformbiz.com.au

docker compose --env-file .env up -d --build
```

This runs in its own Docker Compose project (separate from credit-portal's),
listening only on `127.0.0.1:8000` — it won't collide with credit-portal's
`127.0.0.1:3000`/`3001`.

## 4. Add the second Nginx site + certificate

This adds a **new** Nginx server block for `deals.transformbiz.com.au`
alongside — not replacing — the existing one for credit-portal's domain:

```bash
cp nginx.conf.template /etc/nginx/sites-available/deal-sourcing
sed -i "s/DOMAIN_PLACEHOLDER/deals.transformbiz.com.au/g" /etc/nginx/sites-available/deal-sourcing
ln -s /etc/nginx/sites-available/deal-sourcing /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d deals.transformbiz.com.au
```

`nginx -t` validates config before reloading, so if something's wrong it
tells you before it can affect credit-portal's already-working site. Certbot
manages a separate certificate per domain, so this doesn't touch
credit-portal's certificate either.

## 5. Verify

- `https://deals.transformbiz.com.au/api/health` → `{"status":"ok"}`
- Upload a test PDF/PPTX through the dashboard, confirm it shows up under
  "Uploaded documents" after a page refresh (confirms the syd1 database is
  wired up correctly, not just the app running).
- Re-check `https://portal.transformbiz.com.au` still works fine — confirms
  adding this app alongside it didn't disturb anything.

## Redeploying after a code change

```bash
ssh root@DROPLET_IP
cd /opt/deal-sourcing && git pull
cd deploy/digitalocean && docker compose --env-file .env up -d --build
```

# Deploying to the DigitalOcean droplet

Target: `sca.armin2080.de` → Cloudflare Tunnel → `http://127.0.0.1:8082`
(gunicorn, running as `codex`).

The droplet also hosts **Radmin** (`radmin.armin2080.de`, port 8081). It is the
more important service and must never be disrupted. Everything here is designed
around that: a different port, a different user, and explicit OOM protection so
this app is always the first victim under memory pressure.

## Layout

```
/home/codex/sca/
├── app/            source, rsynced from the workstation
│   ├── backend/    Django project (.env lives here, mode 600)
│   └── frontend/   dist/ is the built SPA
├── venv/           Python 3.12 environment
└── data/           db.sqlite3 and media/ — OUTSIDE the source tree
```

`data/` is deliberately separate. The deploy replaces `app/` wholesale, and the
database and uploaded CVs must not be in the blast radius.

## Build on the workstation (never on the server)

The droplet has no Node and only 1 vCPU, so nothing is built there.

```bash
cd frontend
VITE_USE_MOCKS=false VITE_API_URL= npm run build

cd ../backend
DJANGO_DEBUG=false DJANGO_SECRET_KEY=build-only DJANGO_DB_PATH=/tmp/x.db \
  .venv/bin/python manage.py collectstatic --noinput
```

`VITE_USE_MOCKS=false` is not optional. With `VITE_API_URL` empty, `useMocks`
defaults to **true**, and the deployed UI would silently serve fabricated sample
jobs while looking like it works.

## Transfer

```bash
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'db.sqlite3' --exclude '.env' --exclude 'node_modules' \
  --exclude 'staticfiles' --exclude 'media' --exclude 'old version' \
  --exclude 'frontend.zip' \
  ./ codex@209.38.234.182:/home/codex/sca/app/
```

`--delete` keeps the tree honest. Excluded paths are protected from deletion by
default, which is why `.env` survives — but the database is kept out of the tree
entirely rather than relying on that.

## Post-deploy on the server

```bash
cd /home/codex/sca/app/backend
/home/codex/sca/venv/bin/python manage.py migrate
/home/codex/sca/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart sca
```

## Service

`deploy/sca.service` is the unit. Install with:

```bash
sudo cp /home/codex/sca/app/deploy/sca.service /etc/systemd/system/sca.service
sudo systemctl daemon-reload
sudo systemctl enable --now sca
```

Key settings and why:

| Setting | Reason |
| --- | --- |
| `User=codex` | Cannot read `/root`, so Radmin is unreachable even by accident |
| `OOMScoreAdjust=500` | Makes this service the preferred OOM victim instead of Radmin |
| `MemoryHigh=192M` / `MemoryMax=256M` | Contains a runaway request inside its own cgroup |
| `--workers 1` | 1 vCPU and 458 MB shared; more workers add pressure, not throughput |
| `ProtectSystem=full` | `/usr`, `/boot`, `/etc` read-only to the service |

## Verifying

```bash
# Local, bypassing Cloudflare entirely
curl -sI http://127.0.0.1:8082/            # 200
curl -sI http://127.0.0.1:8082/jobs        # 200, SPA deep link
curl -s  http://127.0.0.1:8082/api/config/ # {"registrationEnabled":false}

# Public, through Access — a 302 to cloudflareaccess.com means the gate works
curl -sI https://sca.armin2080.de/ | head -3

# Confirm Radmin is unaffected
systemctl is-active radmin
```

## Rollback

```bash
sudo systemctl stop sca
sudo systemctl disable sca
```

Radmin is untouched by all of this: different port, different user, separate
service. Removing this app cannot affect it.

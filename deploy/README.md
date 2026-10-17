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
```

## ⚠️ Restart the service — rsync alone does nothing

```bash
sudo systemctl restart sca
```

Python code is loaded into memory at process start. Copying new files changes
nothing until the process restarts, and the symptom is subtle: the site keeps
serving the **old** code with no error anywhere. This was hit for real — a fix
for the blank-page bug was deployed and appeared not to work, because gunicorn
was still running the previous `urls.py`.

`Restart=always` does **not** help here: it only restarts a process that has
exited, and the running process never exits.

To verify which code is actually live, check something that changed:

```bash
curl -s -o /dev/null -w "%{content_type}\n" \
  -H "Host: sca.armin2080.de" http://127.0.0.1:8082/assets/<hash>.js
# must be text/javascript, NOT text/html
```

## Verify asset serving, not just status codes

A blank page was once shipped because `/assets/<hash>.js` returned **200** — with
`Content-Type: text/html` and the 594-byte SPA shell as the body. Every check
looked fine because only the status code was examined.

```bash
JS=$(curl -s -H "Host: sca.armin2080.de" http://127.0.0.1:8082/ \
     | grep -oE "/assets/[a-zA-Z0-9_.-]+\.js" | head -1)
curl -s -o /dev/null -w "type=%{content_type} size=%{size_download}\n" \
     -H "Host: sca.armin2080.de" "http://127.0.0.1:8082$JS"
```

## Automatic search needs an external trigger

Django cannot schedule work for itself. `AutoSearchSettings.next_run_at` only
records when a run *should* happen; something outside the web process has to
come along and ask for it. Without that, enabling automatic search in the UI
does nothing but display a time that never arrives — and the UI is honest about
this through `schedulerActive`, which is driven by `AUTO_SEARCH_SCHEDULER_ENABLED`.

The trigger is cron, installed for `codex` (no root needed):

```bash
crontab -l 2>/dev/null | cat > /tmp/sca-cron
cat >> /tmp/sca-cron <<'CRON'
# Automatic job search. Ticks quarter-hourly; the command itself decides which
# users are due, so scheduling is not tied to this interval.
# choom makes this process the first OOM casualty on a 458MB box, so it can
# never take Radmin down with it.
0,15,30,45 * * * * cd /home/codex/sca/app/backend && nice -n 10 choom -n 900 -- /home/codex/sca/venv/bin/python manage.py run_scheduled_searches >> /home/codex/sca/data/scheduler.log 2>&1
CRON
crontab /tmp/sca-cron && rm /tmp/sca-cron
```

Then tell the UI it exists:

```bash
sed -i 's/^AUTO_SEARCH_SCHEDULER_ENABLED=.*/AUTO_SEARCH_SCHEDULER_ENABLED=true/' \
  /home/codex/sca/app/backend/.env
sudo systemctl restart sca
```

Set it back to `false` if cron is ever removed; the flag describes whether a
trigger exists, not whether users want automatic search.

Check it without waiting for the clock:

```bash
cd /home/codex/sca/app/backend
/home/codex/sca/venv/bin/python manage.py run_scheduled_searches
# "No automatic searches are due right now." is the healthy answer most of the time
tail -20 /home/codex/sca/data/scheduler.log
```

Runs execute **inline** inside that command, not in a background thread. A
daemon thread would be killed the instant the cron process exits, leaving the
run stuck at `running` forever; that failure is silent, since the exit status is
still 0.

Expect `text/javascript` and a size in the hundreds of KB. Anything else means
the SPA fallback is swallowing build output.

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

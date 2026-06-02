# Going live

Three ways to run the pipeline continuously, from simplest to most production-grade.
All of them produce the same artifacts: `data/reports/latest.json` (read by the dashboard)
and push alerts to your webhook when high-opportunity stories appear.

The live behaviour is driven by `config.yaml`:

```yaml
schedule:   { interval_minutes: 30, sources: [rss, google_trends], window_hours: 24 }
dashboard:  { host: 127.0.0.1, port: 8787, refresh_seconds: 30 }
alerts:     { enabled: true, min_opportunity: 0.50, max_per_run: 5, resuppress_hours: 12 }
```

Set `ALERT_WEBHOOK_URL` in `.env` to enable pushing (a Make.com custom webhook URL or a
Slack incoming webhook). Without it, alerts are still computed and logged, just not sent.

---

## Option A — One process, locally (quickest)

Runs the scheduler **and** the dashboard in a single command:

```powershell
$env:PYTHONUTF8 = "1"
python -m newsroom_trends.cli -v live
```

- Dashboard: http://127.0.0.1:8787 (auto-refreshes every 30s)
- Re-runs the pipeline every 30 min and pushes alerts.
- Stop with Ctrl-C. (Closing the terminal stops it — use Option B or C for always-on.)

Run the pieces separately if you prefer:
```powershell
python -m newsroom_trends.cli schedule     # just the recurring runs
python -m newsroom_trends.cli serve         # just the dashboard
```

---

## Option B — Windows Task Scheduler (always-on, no Docker)

Best if you want the machine itself to keep refreshing reports even after reboot,
without a long-running terminal.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
```

This registers a task `NewsroomTrends` that runs the pipeline (with `--alert`) every
30 min. Run the dashboard alongside it whenever you want to look:

```powershell
python -m newsroom_trends.cli serve
```

Manage it:
```powershell
Start-ScheduledTask    -TaskName NewsroomTrends     # run immediately
Get-ScheduledTaskInfo  -TaskName NewsroomTrends     # last/next run, last result
Unregister-ScheduledTask -TaskName NewsroomTrends -Confirm:$false
```

---

## Option C — Docker (24/7, server / cloud)

The portable, always-on answer — runs independent of this PC. One container runs the
scheduler + dashboard; a named volume persists the SQLite db and reports.

```powershell
# from the project root, with a .env file present (can be empty for RSS-only)
docker compose up -d --build
docker compose logs -f          # watch it run
```

- Dashboard: http://localhost:8787
- `restart: unless-stopped` brings it back after crashes/reboots.
- Edit `config.yaml` and `docker compose restart` — no rebuild needed (it's mounted).
- Reports/db survive restarts in the `trends-data` volume.

Deploy to a cloud VM the same way: install Docker, copy the folder, set `.env`, and
`docker compose up -d --build`. Put it behind a reverse proxy (Caddy/Nginx) if you want
TLS and a hostname. The dashboard is read-only and has no auth — keep it on a private
network or add proxy auth before exposing it publicly.

---

## Alert payload shape

POSTed to `ALERT_WEBHOOK_URL` as JSON:

```json
{
  "text": "🔥 2 trending stories to consider:\n• [0.64] शशि थरूर  (google_trends)\n…",
  "generated_at": "2026-06-02T10:37:02+00:00",
  "alerts": [
    {
      "label": "शशि थरूर",
      "opportunity": 0.635, "velocity": 0.787, "engagement": 1.0,
      "freshness": 0.466, "source_breadth": 0.2, "competitor_saturation": 0.0,
      "sources": ["google_trends"], "keywords": ["थरूर", "शशि", "…"],
      "angles": ["High search intent — lead with the exact query…"],
      "url": "https://trends.google.com/…", "signal_count": 1
    }
  ]
}
```

- **Slack**: the top-level `text` renders directly in an incoming webhook.
- **Make.com**: map any field in `alerts[]` to downstream modules (Sheets row, email, etc.).
- De-dup: the same story won't re-alert within `resuppress_hours` (state in `data/alert_state.json`).

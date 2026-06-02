# Publishing the live dashboard to GitHub Pages

GitHub Pages serves **static files only** — it can't run the Python scheduler or the
live server. So "live on Pages" works like this:

```
GitHub Actions (cron, every 30 min, in GitHub's cloud)
   └─ runs the pipeline  →  regenerates docs/index.html + docs/latest.json
   └─ commits data/history.json (interest-over-time accumulates here)
GitHub Pages
   └─ serves docs/  →  https://<username>.github.io/<repo>/
```

You do **not** need git installed locally — Actions does all the running in the cloud.
You just need to get the files into a repo once.

---

## Step 1 — Create the repo and upload the files (no install needed)

1. Go to <https://github.com/new>. Name it e.g. **newsroom-trends**. Choose **Public**
   (GitHub Pages is free for public repos; private Pages needs a paid plan). Create it.
2. On the new repo page, click **uploading an existing file**.
3. Drag in the whole `newsroom-trends` folder contents. **Important:** include the
   hidden `.github` folder (it holds the Actions workflow). If drag-and-drop hides it,
   see "Uploading the workflow" below.
4. Commit the upload.

> Prefer the command line? Install Git (<https://git-scm.com/download/win>), then:
> ```powershell
> cd C:\Users\Lenovo\newsroom-trends
> git init; git add .; git commit -m "init newsroom-trends"
> git branch -M main
> git remote add origin https://github.com/<username>/<repo>.git
> git push -u origin main
> ```

### Uploading the workflow
The web uploader sometimes drops dotfolders. If `.github/workflows/publish.yml` didn't
upload, create it in the web UI: **Add file → Create new file**, name it
`.github/workflows/publish.yml`, and paste the contents of that file from this project.

---

## Step 2 — Turn on Pages

Repo **Settings → Pages**:
- **Source:** Deploy from a branch
- **Branch:** `main`  •  **Folder:** `/docs`
- Save.

Your site will be at **https://<username>.github.io/<repo>/** within a minute or two.

---

## Step 3 — Let the Action run

- Repo **Settings → Actions → General →** Workflow permissions → enable
  **Read and write permissions** (so the bot can commit the refreshed site). Save.
- Go to the **Actions** tab → "Publish trends to GitHub Pages" → **Run workflow**
  to kick the first run immediately. After that it runs on the cron (every ~30 min).

Each run regenerates `docs/` and commits `data/history.json`, so the dashboard updates
itself and the **interest-over-time sparklines fill in** as history accumulates.

---

## Optional — secrets for more sources / alerts

Repo **Settings → Secrets and variables → Actions → New repository secret**. Add any of:

| Secret | Enables |
|--------|---------|
| `ALERT_WEBHOOK_URL`  | push alerts (Make.com / Slack) |
| `YOUTUBE_API_KEY`    | YouTube source |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` | Reddit source |
| `TWITTER_BEARER_TOKEN` | Twitter/X source |

The workflow already wires these env vars; missing ones just skip that source.
To enable extra sources in CI, also add them to the `--only` list in
`.github/workflows/publish.yml` (e.g. `--only rss,google_trends,youtube`).

---

## Things to know

- **Commit noise:** every run that changes data makes a commit to `main`
  (~48/day at 30-min cadence, tagged `[skip ci]`). To reduce it, widen the cron
  (e.g. hourly `5 * * * *`) in the workflow.
- **Cron timing:** GitHub's scheduled runs are best-effort and can be delayed several
  minutes under load. It is not a hard real-time guarantee.
- **Scheduled workflows pause** if a repo has no activity for 60 days — but since this
  workflow commits on every run, it keeps itself alive.
- **No auth on the page:** the dashboard is public and read-only. Don't put anything
  sensitive in config; secrets stay in Actions secrets, never in the committed files.
- **`refresh_seconds`** in `config.yaml` controls the browser auto-reload of the static
  page (default 300s for Pages). The data only actually changes when the Action runs.

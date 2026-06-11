# Naik

An agentic layer inside Monee that makes its wealth surface intelligent and its
insurance surface complete — Bahasa Indonesia first. See
[`design/architecture.md`](design/architecture.md) for the full system design
and agent sequence.

## Monorepo layout

```
naik/
├── design/      Architecture doc (Mermaid) + pricing derivation notebook
├── web/         Next.js frontend (App Router, TS) → Vercel
├── api/         Flask backend, /health + agent endpoints → Render
├── agents/      Diagnostic / wealth / insurance / compliance + pricing kernel
├── eval/        Streamlit ops/eval dashboard → Streamlit Community Cloud
└── render.yaml  Render Blueprint (web service + Postgres, auto-wired)
```

The contract between every subsystem is [`api/schemas.py`](api/schemas.py) — the
single source of truth for all eight data types.

## Local development

**Backend (Flask)** — from the repo root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt
flask --app api.wsgi run --port 5050      # or: gunicorn api.wsgi:app
curl localhost:5050/health
```

With no `DATABASE_URL`, `/health` reports `db: "not_configured"` and still
returns 200. Point `DATABASE_URL` at a local Postgres to see `db: "ok"`.

**Frontend (Next.js)** — from `web/`:

```bash
cd web
npm install
echo 'NEXT_PUBLIC_API_BASE_URL=http://localhost:5050' > .env.local
npm run dev        # http://localhost:3000
```

**Ops dashboard (Streamlit)** — from the repo root:

```bash
pip install -r eval/requirements.txt
API_BASE_URL=http://localhost:5050 streamlit run eval/streamlit_app.py
```

## Deploy runbook (the cloud path)

### 1. Backend + database → Render (one Blueprint)

1. Push this repo to GitHub.
2. Render Dashboard → **New → Blueprint** → select the repo. Render reads
   `render.yaml`, creates the `naik-api` web service **and** the `naik-db`
   Postgres instance, and injects `DATABASE_URL` into the service
   automatically — no manual connection-string paste.
3. Wait for the first deploy; the health check at `/health` must go green.
4. Note the service URL, e.g. `https://naik-api.onrender.com`.

> Free Postgres on Render has a limited lifetime — fine for the hackathon;
> upgrade the `plan` in `render.yaml` for anything longer-lived.

### 2. Frontend → Vercel

1. Vercel → **Add New → Project** → import the repo.
2. **Root Directory: `web`** (this is a monorepo — Vercel must build the
   subdirectory, not the repo root).
3. Add env var **`NEXT_PUBLIC_API_BASE_URL`** = your Render URL from step 1.4.
4. Deploy. The landing page pings `/health` on load and renders the result.

### 3. Ops dashboard → Streamlit Community Cloud

1. share.streamlit.io → **New app** → this repo.
2. **Main file path: `eval/streamlit_app.py`**.
3. Add secret/env **`API_BASE_URL`** = your Render URL.
4. Deploy; "Ping /health" should report the backend reachable.

### 4. Prove it

Open the Vercel URL. The status console fetches the Render backend's `/health`
cross-origin and shows `status: ok` with version, schema version, and DB
status. That round-trip — Vercel → Render → Postgres — is the cloud path proved.

## Conventions

- `api/schemas.py` field names are frozen; coordinate before renaming.
- Money is whole-rupiah `int` (`*_idr`); wellness scores are floats in `[0,100]`.
- Secrets live only in platform env stores, never in the repo.

## Team Members
| Name | Email | Website |
| ------------- | ------------- | ------------- |
|Allen Lu Zhao Quan|ALLE0002@e.ntu.edu.sg| [Portfolio](https://allenlu.vercel.app) |
|Gao Xinyue|GAOX0032@e.ntu.edu.sg| [Linkedin](https://www.linkedin.com/in/xinyuegaontusg) |
|Hilda Tio|HTIO001@e.ntu.edu.sg| [Linkedin](https://www.linkedin.com/in/tiohilda) |
|Tio Sher Min|STIO002@e.ntu.edu.sg| [Linkedin](https://www.linkedin.com/in/sher-min-tio-119a58327) | 

## Contributors
| Component | Name |
| ------------- | ------------- |
|AI Agents|Allen|
|Pricing & Evaluation Framework|Allen|
|System Architecture & API|Allen|
|Frontend|Allen, Hilda, Sher Min, Xinyue|
|Backend|Allen, Xinyue|
|Data & Fixtures|Allen|
|Slide Design|Xinyue|

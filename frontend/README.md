# React transition preview

FIXED328 starts a separate React/TypeScript interface. The preview supports existing Supabase accounts, recorded text analysis through `/api/v2/analyses`, and read-only keyword catalog search through `/api/v1/keywords`. The Streamlit app remains the operational UI for OCR, unmatched candidates, keyword requests, and administration.

## Local setup

1. Copy `.env.example` to `.env.local` and set `VITE_SUPABASE_PUBLISHABLE_KEY` to the project's **publishable** key. Set `VITE_API_BASE_URL` to the FastAPI origin. Never put `SUPABASE_SECRET_KEY` in a `VITE_` variable.
2. Run `npm ci` and `npm run dev` in this directory.
3. Run FastAPI with `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY` configured. The API's default CORS origins include `http://localhost:5173` and `http://127.0.0.1:5173`.

## Deploying this preview

The `render.yaml` Blueprint prepares an independent `keyword-risk-react-preview` static service with automatic deploys disabled. In Render, set its build-time `VITE_SUPABASE_PUBLISHABLE_KEY` and `VITE_API_BASE_URL` (the public HTTPS API origin), then deploy it. On the FastAPI service set `API_CORS_ORIGINS` to the **exact HTTPS origin** of the static site and redeploy the API. For an existing Blueprint, Render does not populate newly added `sync: false` variables automatically, so set these values in the Dashboard. Keep the existing Streamlit service and URL active.

Each explicit analysis click uses an anonymous UUID. The v2 API uses the current Streamlit text matching rules, records hit counts and unmatched candidate observations in one idempotent database transaction, and loads the latest common matching settings. Failed requests can be retried without duplicate counts. The existing v1 API behavior remains available to integration clients.

The connected Supabase project has the v2 RPC installed. Apply [`supabase/record_analysis_with_unmatched_setup.sql`](../supabase/record_analysis_with_unmatched_setup.sql) before deploying the v2 API against another existing project; fresh installations include it in `supabase/schema.sql`.

The preview still lacks the Streamlit detailed highlight interactions, auxiliary analysis, OCR, normalization review, keyword requests, reports, and administration. The catalog is read-only; administrators continue editing keywords in Streamlit. Deploy it separately until those screens are migrated and compared with the existing app.

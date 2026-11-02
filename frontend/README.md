# React transition preview

FIXED328 starts a separate React/TypeScript interface. This first slice supports existing Supabase accounts and read-only text analysis through the current FastAPI service. The Streamlit app remains the operational UI for OCR, unmatched candidates, keyword requests, administration, and the analysis side effects.

## Local setup

1. Copy `.env.example` to `.env.local` and set `VITE_SUPABASE_PUBLISHABLE_KEY` to the project's **publishable** key. Set `VITE_API_BASE_URL` to the FastAPI origin. Never put `SUPABASE_SECRET_KEY` in a `VITE_` variable.
2. Run `npm ci` and `npm run dev` in this directory.
3. Run FastAPI with `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY` configured. The API's default CORS origins include `http://localhost:5173` and `http://127.0.0.1:5173`.

## Deploying this preview

Build the `frontend` directory with `npm ci && npm run build`; publish `frontend/dist` as a static site. Set these build-time variables on the static host: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, and `VITE_API_BASE_URL` (the public HTTPS API origin). Set `API_CORS_ORIGINS` on the FastAPI service to the **exact HTTPS origin** of the static site; redeploy the API. Keep the existing Streamlit service and URL active. Do not route existing production users to the preview yet.

This preview calls `/api/v1/analyses` with `record: false`: it does not write analysis history, keyword hit counts, or unmatched candidate observations. Its matching rules and visible options do not yet cover every Streamlit setting. Moving those side effects and the remaining screens to authenticated API operations is the next stage.

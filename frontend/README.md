# React transition preview

FIXED328 starts a separate React/TypeScript interface. The preview supports existing Supabase accounts and password recovery, recorded text analysis through `/api/v2/analyses` with risk-colored clickable highlights and match details, read-only keyword catalog search, filters, and full CSV export through `/api/v1/keywords`, rolling-period Top N reports through `/api/v1/reports/top-keywords`, Korean OCR image extraction and keyword registration through `/api/v1/ocr`, official-source regulation lookup through `/api/v1/regulation/questions`, unmatched-candidate review, Kiwi-based normalization recommendations and per-user drafts, and registration requests through `/api/v1/unmatched-terms`, existing-keyword inquiries, history, and admin responses through `/api/v1/keyword-requests`, admin-only user role management through `/api/v1/admin/users`, keyword editing, additions, deletion, and CSV/XLSX import through `/api/v1/admin/keywords`, admin review, approval, and rejection of unmatched registration requests through `/api/v1/admin/unmatched-registration-requests`, shared normalization and approved partial-match settings through `/api/v1/admin/normalization-settings` and `/api/v1/admin/approved-partials`, and shared classification dropdown management through `/api/v1/admin/dropdown-settings`. The Streamlit app remains available for other administration.

## Local setup

1. Copy `.env.example` to `.env.local` and set `VITE_SUPABASE_PUBLISHABLE_KEY` to the project's **publishable** key. Set `VITE_API_BASE_URL` to the FastAPI origin. Never put `SUPABASE_SECRET_KEY` in a `VITE_` variable.
2. Add the frontend origin to Supabase Auth's allowed redirect URLs so password recovery emails can return to the React app.
3. Run `npm ci` and `npm run dev` in this directory.
4. Run FastAPI with `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY` configured. The API's default CORS origins include `http://localhost:5173` and `http://127.0.0.1:5173`.

Korean OCR additionally requires Python 3.9–3.13 and the dependencies in [`requirements-ocr.txt`](../requirements-ocr.txt). Install these in the same Python environment that runs FastAPI; the OCR model is initialized on the first OCR request.

## Deploying this preview

In Supabase Auth, add the deployed static-site origin to the allowed redirect URLs for password recovery. On Render, set the frontend's build-time `VITE_SUPABASE_PUBLISHABLE_KEY` and `VITE_API_BASE_URL` (the public HTTPS API origin). On the FastAPI service set `API_CORS_ORIGINS` to the **exact HTTPS origin** of the static site and deploy both services. For an existing Blueprint, Render does not populate newly added `sync: false` variables automatically, so set these values in the Dashboard. Keep the existing Streamlit service and URL active.

Each explicit analysis click uses an anonymous UUID. The v2 API uses the current Streamlit text matching rules, records hit counts and unmatched candidate observations in one idempotent database transaction, and loads the latest common matching settings. Failed requests can be retried without duplicate counts. The existing v1 API behavior remains available to integration clients.

The connected Supabase project has the v2 RPC installed. Apply [`supabase/record_analysis_with_unmatched_setup.sql`](../supabase/record_analysis_with_unmatched_setup.sql) before deploying the v2 API against another existing project; fresh installations include it in `supabase/schema.sql`.

The React preview now includes Korean OCR with selectable text over the recognized image, keyword classification and registration, detailed match highlights, CSV/XLSX keyword import templates, administrator report reset controls, and the shared administrator inquiry-email notification setting. Email provider secrets stay on the API service. The main Streamlit tabs have React counterparts. Keep Streamlit as the production UI until the final interaction parity review is complete.

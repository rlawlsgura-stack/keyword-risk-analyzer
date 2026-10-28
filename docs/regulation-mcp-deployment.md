# Law lookup chat deployment

The FIXED297 tab keeps the existing OCR and keyword analysis flow unchanged. It sends a question only after submission to the authenticated FastAPI service, which reads the current keyword database and calls the legislation MCP server. The MCP service is not called by the browser.

## Render services

The existing `keyword-risk-api` service acts as the public, authenticated gateway. Deploy the public `ChangooLee/mcp-kr-legislation` repository separately in the **same Render workspace and region** as a **Private Service**. Render private services have no public URL and accept traffic only from services on that private network.

Create the private service from `https://github.com/ChangooLee/mcp-kr-legislation` in Render. For the MCP service, use:

- Build command: `pip install uv && uv sync --frozen`
- Start command: `uv run python -m mcp_kr_legislation.server`
- `HOST=0.0.0.0`
- `PORT=10000`
- `TRANSPORT=http`
- `LEGISLATION_API_KEY=<your Law.go.kr account identifier/email>`

Set `REGULATION_MCP_URL` on `keyword-risk-api` to the MCP service's internal address, ending in `/mcp`, for example `http://<private-service-host>:10000/mcp`. Keep the MCP service private. The upstream repository's HTTP example does not document caller authentication; a public MCP endpoint could be called outside the application.

Set `REGULATION_API_URL` in Streamlit Community Cloud → App settings → Secrets to the public URL of `keyword-risk-api`, for example `https://<keyword-risk-api>.onrender.com`. The app sends the signed-in user's Supabase access token to the existing FastAPI auth dependency. No service-role or MCP key belongs in Streamlit secrets.

## Local development

Clone the MCP repository beside this project, not inside it:

```powershell
Set-Location D:\back-up\encore
git clone https://github.com/ChangooLee/mcp-kr-legislation.git
Set-Location .\mcp-kr-legislation
uv venv
uv pip install -e .
```

Run the MCP process with `HOST=127.0.0.1`, `PORT=8001`, and `TRANSPORT=http`. Set `REGULATION_MCP_URL=http://127.0.0.1:8001/mcp` for the local FastAPI process and `REGULATION_API_URL=http://127.0.0.1:8000` for the local Streamlit app. Use your own Law.go.kr identifier; the upstream repository currently contains a tracked `.env` with a maintainer default, so do not commit personal environment edits back to that repository.

In PowerShell, set these in the terminal used to start the local MCP process:

```powershell
$env:LEGISLATION_API_KEY = "your-email-or-law.go.kr-id"
$env:HOST = "127.0.0.1"
$env:PORT = "8001"
$env:TRANSPORT = "http"
uv run python -m mcp_kr_legislation.server
```

Put the two `REGULATION_*_URL` values in the keyword-risk-analyzer `.env` for local app/API use.

## Retrieval and optional explanation

- “광고 문구·키워드에서 법령 찾기” calls the law and precedent search tools using the submitted question's short terms. Selected OCR candidates and analysis text are included only when the user selects them.
- “법령·조항에서 등록 키워드 찾기” retrieves the selected law/article and compares the returned article text against the current keyword DB using exact matching. It does not label semantic similarity as a direct match.
- `REGULATION_LLM_ENABLED` defaults to `false`. To add the explanation stage later, set it to `true` on `keyword-risk-api` and set `OPENAI_API_KEY` and `REGULATION_LLM_MODEL` there. Only submitted questions, opted-in context, DB matches, and retrieved source text are sent. The LLM does not perform a separate legal search.
- The LLM must cite a source ID and a quote that appears verbatim in the retrieved material. A reported conflict, insufficient evidence, or invalid quote suppresses the generated conclusion and displays an administrator-review notice with the retrieved sources. A valid quote still does not establish that the interpretation is legally correct; the UI labels the result as informational.
- Chat history remains in the active Streamlit session and is not written to Supabase.

The Streamlit Community Cloud app cannot reach a process running on the user's PC. Cloud use requires the Render API gateway and private MCP service to be deployed and their environment settings above to be configured.

# Law lookup chat

The optional, evidence-first legal lookup chat sends submitted questions to the authenticated FastAPI service. The service reads the current keyword database and calls the Law.go.kr Open API through `legislation_source.py`. Search and explanation orchestration live in `regulation_assistant.py`; the provider module owns HTTP requests and response formatting. This keeps the data source replaceable without changing the question flow.

## Configure the API service

1. Request an Open API key (the `OC` identifier) from [Law.go.kr Open Data](https://open.law.go.kr/).
2. Set `LEGISLATION_API_KEY` in the `keyword-risk-api` service environment or local API `.env`.
3. Redeploy or restart `keyword-risk-api`.
4. Keep `REGULATION_API_URL` in Streamlit Community Cloud Secrets pointed at the public URL of `keyword-risk-api`.

The Law.go.kr key belongs only on the API service. Do not put it in Streamlit Cloud Secrets or commit it. `REGULATION_MCP_URL` is no longer used. An MCP service is not required for this application's current searches.

## Retrieved evidence and optional explanation

- Keyword-to-law questions search laws, administrative rules, and precedents using up to three short terms from the submitted question and selected context.
- Law-to-keywords questions locate the law and retrieve the requested article, or the full current law when no article number is supplied. The returned provision text is compared with the current keyword database using exact matching.
- Retrieved source text includes the official record links returned by Law.go.kr when available. Search results are evidence for review; they are not a legal verdict.
- `REGULATION_LLM_ENABLED` defaults to `false`. To enable the optional explanation stage, set it to `true` on `keyword-risk-api`, and set `OPENAI_API_KEY` and `REGULATION_LLM_MODEL` there. The LLM receives only the submitted question, opted-in context, DB matches, and retrieved source text. It does not perform a separate legal search.
- The LLM must cite a source ID and a quote that appears verbatim in retrieved material. A conflict, insufficient evidence, or invalid quote suppresses its conclusion and asks for administrator review. A valid quote still does not establish that the interpretation is legally correct; the UI labels the result as informational.
- Chat history remains in the active Streamlit session and is not written to Supabase.

## Future provider changes

If another MCP-compatible client needs the same searches later, add an MCP provider that implements the same search operations in `legislation_source.py`. The request flow, DB comparison, source handling, and optional LLM explanation can remain in `regulation_assistant.py`.

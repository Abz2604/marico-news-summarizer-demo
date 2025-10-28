# Backend Requirements (MVP Focus)

## 0. Phase 0 MVP (Thin Slice)
- Expose a single endpoint: `POST /api/agent/run` that accepts `{ "prompt": string, "seed_links": string[], "max_articles"?: number }` and returns `{ "summary_markdown": string, "bullet_points": string[], "citations": {url,label}[], "model": string }`.
- Enable CORS for the Next.js origin so the browser can call the FastAPI backend.
- Validate configuration at startup and per-request: require `OPENAI_API_KEY`. If missing, return a clear 422/500 with actionable message.
- Provide a minimal health check `GET /api/healthz` that reports service status and verifies OpenAI key presence (Snowflake check can be added in Phase 1).
- Establish Python dependency management in `api/requirements.txt` (or `pyproject.toml`). Remove Python packages from `package.json`.
- Wire the frontend form to call `POST /api/agent/run` instead of simulating saves.
- Defer persistence (Snowflake), auth/JWT, and campaigns endpoints to Phase 1+ while keeping code structure extensible.

## 1. Objectives & Scope
- Replace demo data with a minimal-but-real backend supporting the existing briefing and campaign UI flows.
- Persist core entities (users, briefings, summaries, campaigns) in Snowflake via a thin data access layer.
- Provide REST endpoints that the frontend can call today: list/create briefings, trigger a summary run, read generated summaries, and view campaign metadata.
- Implement a LangChain/LangGraph-powered agent that operates on **provided seed links** (no open web search for MVP) to fetch, extract, and summarize news content.
- Defer advanced capabilities (multi-channel delivery, RBAC, analytics) to later phases but keep the design extensible.

## 2. Architecture Overview (MVP)
- **Runtime:** FastAPI app (residing in `api/`) deployed as a single service. For local dev we can run `uvicorn` directly.
- **Data Layer:** Snowflake for all persistent data. Use a lightweight connector module that wraps Snowflake Python connector + SQL templates.
- **State & Caching:** In-memory caching optional; not required for MVP.
- **Background Work:** Use a simple task queue based on `asyncio` background tasks or `RQ` + Redis if necessary. For MVP, synchronous execution with guarded timeouts is acceptable; long-term we can move to dedicated workers.
- **LLM/Agent:** LangChain/LangGraph orchestrating OpenAI (configurable via env). Agent receives seed URLs and prompt, crawls only those domains (with limited depth) unless explicitly provided more links.
- **File Storage:** No external object storage for MVP; store extracted article text and metadata in Snowflake (VARIANT/Text). Future optimization can offload to object storage.
- **CORS:** Enable CORS for the Next.js origin(s) so browser calls to the API succeed.
- **Dependencies:** Maintain Python deps in `api/requirements.txt` (or `pyproject.toml`); do not list Python packages in `package.json`.

## 3. Snowflake Schema (MVP)
Use one database, one schema (e.g., `MARICO.PROD`). All IDs are UUID strings.

### 3.1 Identity
- `users`
  - `id`, `email`, `hashed_password`, `display_name`, `role` (enum: `admin`, `member`), `created_at`, `updated_at`.
- (Optional) `sessions` can be added later; MVP can rely on stateless JWT.

### 3.2 Briefings & Sources
- `briefings`
  - `id`, `user_id`, `name`, `description`, `status` (`draft`, `active`, `paused`), `prompt`, `primary_links` (ARRAY of STRING), `created_at`, `updated_at`, `last_run_at`.
- `briefing_links`
  - `id`, `briefing_id`, `url`, `depth_limit` (default 0), `notes`, `created_at`.
- `briefing_tags` (optional for MVP, only if UI needs filtering).

### 3.3 Agent Runs & Content
- `agent_runs`
  - `id`, `briefing_id`, `trigger_type` (`manual`, `schedule`), `status` (`queued`, `running`, `succeeded`, `failed`), `started_at`, `completed_at`, `error_message`, `model`, `token_usage_prompt`, `token_usage_completion`.
- `agent_run_steps`
  - `id`, `agent_run_id`, `step_order`, `name`, `input_payload` (VARIANT), `output_payload` (VARIANT), `error`, `created_at`.
- `articles`
  - `id`, `agent_run_id`, `source_url`, `resolved_url`, `title`, `author`, `published_at`, `raw_html`, `clean_text`, `extraction_confidence`, `created_at`.
- `summaries`
  - `id`, `agent_run_id`, `briefing_id`, `summary_markdown`, `bullet_points` (ARRAY), `key_quotes` (ARRAY), `citations` (ARRAY of STRUCT `{title, url}`), `created_at`.

### 3.4 Campaigns (Read-Only for MVP)
- `campaigns`
  - `id`, `name`, `status` (`active`, `paused`), `description`, `briefing_ids` (ARRAY), `recipient_emails` (ARRAY), `schedule_description`, `created_at`, `updated_at`.
- Delivery logs and multi-channel support are **out of scope** for MVP; campaigns exist to satisfy the dashboard view.

### 3.5 Utilities
- `audit_events` (optional future). Not required for MVP but keep table name reserved.

## 4. Snowflake Connector Strategy
- Create `lib/snowflake.py` with helper functions:
  - `get_connection()` to initialize connector using env (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`).
  - context manager for query execution returning dicts.
  - parameterized SQL queries stored as constants or in a simple repository layer per domain.
- Provide migration scripts as SQL files executed manually or via lightweight runner (no Alembic equivalent in Snowflake). For MVP maintain a `schema.sql` with table creation statements.

## 5. API Surface (MVP)
All endpoints prefixed with `/api` to mirror Next.js conventions.

### 5.0 Phase 0 API Surface
- `POST /api/agent/run`
  - **Request Body:** `{ "prompt": string, "seed_links": string[], "max_articles"?: number }`
  - **Response 200:** `{ "summary_markdown": string, "bullet_points": string[], "citations": {"url": string, "label": string}[], "model": string }`
  - **Error Responses:** `422` when `OPENAI_API_KEY` missing or body invalid; `500` on unexpected failure.

### 5.1 Auth
- `POST /auth/login` – verify credentials, issue JWT.
- `POST /auth/signup` – optional (enabled for internal testing). Otherwise seed a default admin user.

### 5.2 Briefings
- `GET /briefings` – returns list with summary metadata (status, last run).
- `POST /briefings` – create briefing with name, prompt, and initial seed links.
- `GET /briefings/{id}` – returns briefing + latest summary (if exists) + seed links.
- `PATCH /briefings/{id}` – update status, prompt, or seed links.
- `POST /briefings/{id}/run` – trigger agent run (synchronous response with run id, actual processing may be async).
- `GET /briefings/{id}/runs` – list recent runs with status/outcome.
- `GET /briefings/{id}/summaries` – list historical summaries (latest first).
#### 5.2.1 Contracts
- `GET /briefings`
  - **Query Params:** `status` (optional), `limit` (default 20), `cursor` (optional).
  - **Response 200:**
    ```json
    {
      "items": [
        {
          "id": "b1",
          "name": "Tech Headlines Digest",
          "status": "active",
          "prompt": "Summarize the top tech stories...",
          "seed_links": ["https://techcrunch.com"],
          "last_run_at": "2025-10-22T08:45:00Z"
        }
      ],
      "nextCursor": null
    }
    ```
- `POST /briefings`
  - **Request Body:** `{ "name": string, "description"?: string, "prompt": string, "seed_links": string[] }`
  - **Response 201:** `{ "id": string, "name": string, "prompt": string, "status": "draft", "seed_links": string[], "created_at": iso8601 }`
  - **Error Responses:** `400` validation error (invalid URL/prompt missing), `409` duplicate name (same user).
- `GET /briefings/{id}`
  - **Response 200:** `{ "briefing": { ...briefing fields... }, "latest_summary": { ... } }`
  - **Error Responses:** `404` not found when id unknown or unauthorized.
- `PATCH /briefings/{id}`
  - **Request Body:** Partial object with fields `name`, `description`, `status`, `prompt`, `seed_links`.
  - **Response 200:** Updated briefing payload.
- `POST /briefings/{id}/run`
  - **Request Body (optional):** `{ "max_articles"?: number, "crawl_depth"?: number }`
  - **Response 202:** `{ "run_id": string, "status": "queued" | "running" }`
  - **Error Responses:** `409` if a run is already in progress, `422` if parameters out of bounds.
- `GET /briefings/{id}/runs`
  - **Response 200:** list of `{ "id", "status", "started_at", "completed_at", "error_message" }`.
- `GET /briefings/{id}/summaries`
  - **Response 200:** `{ "items": [{ "id", "created_at", "headline"?, "summary_markdown" }], "nextCursor": null }`.

### 5.3 Summaries (optional convenience)
- `GET /summaries/{summary_id}` – fetch summary detail for deep link.

### 5.4 Campaigns (read-only for MVP)
- `GET /campaigns` – return stub data from Snowflake so UI can display cards.
- `GET /campaigns/{id}` – detail view for future expansion.
#### 5.4.1 Contracts
- `GET /campaigns`
  - **Response 200:**
    ```json
    {
      "items": [
        {
          "id": "c1",
          "name": "Daily CXO Briefing",
          "status": "active",
          "briefing_ids": ["b1", "b2"],
          "recipient_emails": ["ceo@example.com"],
          "schedule_description": "Weekdays 09:00"
        }
      ]
    }
    ```
- `GET /campaigns/{id}`
  - **Response 200:** same shape as list item plus optional `notes` and metadata.
  - **Error Responses:** `404` when campaign not present.

### 5.5 Health
- `GET /api/healthz` – during Phase 0 validates service liveness and OpenAI key presence; in Phase 1 adds Snowflake connectivity.

## 6. Agent Design (Seed-Link-Oriented)
- **Inputs:** `briefing.prompt`, user-provided `seed_links` (primary + optional additional). Optionally accept `max_articles`, `crawl_depth` (default 0 = just the provided page).
- **Flow:**
  1. **Init:** Create `agent_run` record, mark `running`.
  2. **Fetch URLs:** For each seed link, optionally expand to additional URLs via in-page links if `depth_limit > 0`.
  3. **Normalize & Deduplicate:** Ensure we only process each resolved URL once.
  4. **Fetch & Extract:** Use `httpx` to fetch HTML, apply readability-based extractor. Store structured article record.
  5. **Summarize:** Feed aggregated article chunks + prompt into LangChain summarization chain (map-reduce if multiple articles). Return bullet list + markdown narrative + citations.
  6. **Persist:** Save summary, bullet points, citations to Snowflake. Update `briefings.last_run_at` and `agent_run.status`.
- **Failure Handling:** On exception, mark run as failed with message. Provide partial data capture in `agent_run_steps` for debugging.
- **Performance Guardrails:** Limit to <=5 articles per run for MVP. Add simple rate limiting (sleep between requests) to avoid site bans.

#### 6.1 Execution Sequence (Pseudo-flow)
1. `init_run(briefing_id)`
   - Insert `agent_runs` row (`status='running'`), capture config (prompt, links, limits).
   - Append step record `{"step": "init", "briefing_id": ...}`.
2. `prepare_url_queue`
   - Normalize seed links, enforce HTTPS when possible.
   - If `crawl_depth > 0`, enqueue link discovery tasks but cap total URLs (`<= max_articles * 2`).
3. `fetch_and_extract`
   - For each URL, attempt HTTP GET with timeout (e.g., 10s) and 2 retries.
   - Record step results: status code, fetch latency, error (if any).
   - Run readability extraction; skip if `clean_text` < 200 chars.
   - Persist article rows immediately to Snowflake.
   - Stop once we have `max_articles` successful extractions.
4. `summarize`
   - Assemble prompt template with briefing instructions + article snippets (truncate to ~3k tokens overall).
   - Call LangChain `map_reduce` chain, log token usage and model name.
   - Persist summary row (markdown + bullets + citations) linked to run.
5. `finalize`
   - Update `agent_runs.status` (`succeeded` or `failed`) and `completed_at`.
   - Update `briefings.last_run_at` when successful.
   - Emit final step with summary metadata and counts (articles processed, tokens used).

#### 6.2 Error & Retry Strategy
- Network errors: retry up to 2 times with exponential backoff (0.5s, 2s) before marking URL as failed.
- Extraction failures: skip URL but continue run; include failure note in summary metadata.
- LLM errors: attempt one immediate retry; if persistent, mark run failed with error message.
- Hard stop: if zero articles extracted, mark run failed with `"reason": "no_content"`.
- Store all errors in `agent_run_steps` to enable frontend debugging view later.

## 7. Background Processing & Scheduling
- For MVP, `POST /briefings/{id}/run` can run agent synchronously (with request held open up to ~60s). If we exceed time, shift to `asyncio.create_task` and return early with run id.
- Manual scheduling (cron for daily runs) can be deferred; if needed quickly, add simple APScheduler job runner inside API process reading `briefings` with `status='active'`.
- Campaign delivery automation is out of scope; we only need stored metadata.

## 8. Observability & Logging
- Structured logging using Python `logging` with run id correlation.
- Minimal metrics: log counts of successful/failed runs. Advanced monitoring deferred.
- Capture agent decisions in `agent_run_steps` for debugging via API.

## 9. Security & Configuration
- Store Snowflake credentials and OpenAI keys in `.env.local` (never commit). Use FastAPI dependency to enforce JWT auth on all routes except `/healthz`.
- Basic rate limiting (per-user per-minute counts) can be implemented later; not critical for MVP but keep middleware hook ready.
- Ensure summaries and prompts sanitized before returning to frontend (no HTML injection).
- Enable CORS for the frontend origin.
- Prefer `pydantic` v1 for current `BaseSettings` usage or adopt `pydantic-settings` v2 across the codebase consistently.
- Manage Python dependencies via `api/requirements.txt` (or `pyproject.toml`); do not place Python packages in `package.json`.

## 9.1 Non-Functional Baselines (MVP)
- **Performance:** Target end-to-end agent run completion under 60 seconds for three-article summaries; request timeout 90 seconds.
- **Availability:** Single instance acceptable; restart within 5 minutes in case of failure.
- **Scalability:** Support at least 5 concurrent runs without manual intervention; beyond that, queue requests.
- **Security:** Hash passwords with Argon2id (or bcrypt fallback). JWT expiry 60 minutes, refresh via login. All external calls over HTTPS.
- **Data Integrity:** Wrap Snowflake writes in transactions where multiple inserts must succeed together (e.g., run + summary).
- **Reliability:** Persist intermediate data (articles, steps) immediately to avoid data loss on crash.

## 10. Phase 2+ Wishlist (Not MVP)
- Multi-tenant organizations, RBAC, API keys.
- Automated search expansion (SerpAPI, etc.) beyond provided links.
- Email/slack delivery, full campaign automation, delivery logs.
- Vector search for deduping across runs, advanced analytics dashboards.
- External storage for article snapshots, cost tracking, audit logs.

## 11. Next Steps Checklist (High Level)
Before steps 1–6, complete Phase 0 tasks:
  - Add CORS and mount routers under `/api`.
  - Implement `POST /api/agent/run` and frontend wiring.
  - Validate `OPENAI_API_KEY` in health and requests.
  - Create `api/requirements.txt` and remove Python deps from `package.json`.
1. Set up Snowflake schema (run `schema.sql`).
2. Implement Snowflake connector and repository functions for `briefings`, `agent_runs`, `summaries`, `campaigns`.
3. Build FastAPI routers (auth, briefings, campaigns, summaries, health).
4. Wire frontend to new endpoints for briefings and campaigns.
5. Implement agent runner adhering to seed link constraints and persist outputs.
6. Smoke test end-to-end: create briefing → run agent → view summary in dashboard.



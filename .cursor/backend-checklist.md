# Backend Development Checklist (MVP)

## Phase 0 (Thin Slice – Immediately Usable)
- [x] Mount all routers under `/api` prefix in `api/main.py`.
- [x] Enable CORS for the Next.js origin in FastAPI middleware.
- [x] Implement `POST /api/agent/run` (seed links + prompt → summary payload).
- [x] Validate `OPENAI_API_KEY` on startup and return a clear error if missing.
- [x] Update `/api/healthz` to verify service liveness and OpenAI key presence.
- [x] Add Python dependency management: create `api/requirements.txt` and remove Python packages from `package.json`.
- [ ] Wire the frontend create form to call `POST /api/agent/run` and render the returned summary.

## Foundation Setup
- [ ] Scaffold FastAPI app layout (`api/main.py`, `routers/`, `schemas/`, `services/`).
- [ ] Configure environment settings loader (Snowflake creds, OpenAI key, JWT secret, timeout defaults).
- [ ] Implement Snowflake connector utility (`lib/snowflake.py`) with connection pooling/retry helpers.
- [ ] Create `schema.sql` (or migration scripts) with CREATE TABLE statements and document execution steps.

## Data Modeling & Persistence
- [ ] Create Snowflake tables: `users`, `briefings`, `briefing_links`, `agent_runs`, `agent_run_steps`, `articles`, `summaries`, `campaigns`.
- [ ] Seed initial data for development (admin user, sample campaigns).
- [ ] Implement repository functions for CRUD (briefings, campaigns, runs, summaries) with typed return objects.
- [ ] Ensure transactional writes where run + summary inserts must succeed together.

## API Layer
- [ ] Define Pydantic models matching documented contracts (requests/responses + error shapes).
- [ ] Build auth endpoints (`POST /auth/login`, optional `POST /auth/signup`) with Argon2/bcrypt hashing and JWT issuance.
- [ ] Implement briefing endpoints (`GET/POST/PATCH /briefings`, `GET /briefings/{id}`, `/runs`, `/summaries`, `POST /briefings/{id}/run`).
- [ ] Implement campaign read endpoints (`GET /campaigns`, `GET /campaigns/{id}`).
- [ ] Add `/summaries/{id}` endpoint if frontend needs direct access.
- [ ] Provide `/healthz` endpoint checking Snowflake + OpenAI connectivity.
- [ ] Add error handling middleware returning consistent JSON structure.
  - [ ] Ensure all routes are mounted under `/api` and CORS is configured.

## Agent Implementation
- [ ] Implement agent runner orchestrating sequence: init → prepare queue → fetch/extract → summarize → finalize.
- [ ] Add URL normalization, deduping, and crawl depth guard rails.
- [ ] Integrate HTTP fetching with retry/backoff and extraction (readability/Goose).
- [ ] Implement LangChain summarization chain adhering to token limits; include token usage logging.
- [ ] Persist agent steps, article records, and summary payloads per run.
- [ ] Handle failure modes (network, extraction, LLM) updating run status accordingly.

## Non-Functional & Observability
- [ ] Configure logging with run id correlation and structured JSON output.
- [ ] Enforce request/agent timeouts (60s target, 90s hard stop) via settings.
- [ ] Apply basic security defaults (Argon2 hashing, JWT expiry 60m, HTTPS enforcement for outbound calls).
- [ ] Document rate-limiting strategy placeholder (even if deferred) and ensure hooks ready.

## Frontend Integration
- [ ] Replace demo data fetches on `/dashboard/briefings` with live API calls (list, status toggles, delete if supported).
- [ ] Connect create briefing form to `POST /briefings` and `POST /briefings/{id}/run` for preview.
- [ ] Update campaigns dashboard to consume `GET /campaigns` data.
- [ ] Wire frontend auth flow to backend JWT endpoints; handle token storage/refresh strategy.
- [ ] Display run history and summary content using new API responses.
  - [ ] For Phase 0: Call `POST /api/agent/run` directly and render returned summary.

## Testing & QA
- [ ] Unit tests for repositories and validation logic (briefing creation, seed link validation, password hashing).
- [ ] Integration tests for key API flows using Snowflake test schema or mocks.
- [ ] Agent runner tests with mocked HTTP/LLM responses covering success and failure paths.
- [ ] Manual QA script: create briefing → add seed links → run agent → view summary in UI → verify data in Snowflake.

## Deployment & Rollout
- [ ] Document local dev setup (Snowflake credentials, env variables, running FastAPI + Next.js concurrently).
- [ ] Define deployment plan (container image or serverless) and CI steps (tests, linting).
- [ ] Set up minimal monitoring/alerts (logging sink, error notifications).
- [ ] Create rollback/runbook notes for agent failures and Snowflake connectivity issues.



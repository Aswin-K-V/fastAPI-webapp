# Production-Readiness & Scale Roadmap

An honest assessment of whether this FastAPI blog app is production-ready and able to
scale to millions of users, plus a prioritized roadmap of what to add. Framed for a
**learning/portfolio** project — the goal is to learn the high-leverage concepts first,
not to over-build infrastructure you won't run.

> **Verdict:** Not production-ready for millions of users today. But the architecture
> choices are sound, so this is a good base to harden rather than rewrite.

---

## What's already good (keep these)

These are real strengths and the reason the app is "scalable in principle":

- **Stateless auth** — JWT means any app instance can serve any request, so you can run
  N replicas behind a load balancer with no sticky sessions. This is the single biggest
  prerequisite for horizontal scale, and it's already done.
- **Fully async stack** — async SQLAlchemy + async endpoints + `run_in_threadpool` for
  the CPU/blocking work (PIL, boto3). Correct instinct.
- **Media offloaded to S3** ([image_utils.py](image_utils.py)) — app servers stay
  stateless; no local disk to replicate.
- **Externalized config** via `pydantic-settings` ([config.py](config.py)) and secrets
  as `SecretStr`. Twelve-factor friendly.
- **Alembic migrations** present — schema changes are versioned, not ad hoc.
- **N+1 avoided** — `selectinload(Post.author)` is used on every feed/list query.
- **Sensible auth hygiene** — Argon2 hashing, generic "incorrect email or password",
  generic forgot-password response (no account enumeration), hashed reset tokens with
  expiry.

---

## Concrete bugs found (fix these regardless of scale)

These are correctness issues in the current code, independent of scale:

1. **`change_password` endpoint is never registered** —
   [routers/users.py:228](routers/users.py#L228). The line
   `router.patch("/me/password", ...)` is missing the `@` decorator *and* is separated
   from the function by a blank line, so `change_password` is registered as nothing. The
   feature is dead. Should be `@router.patch("/me/password", ...)` directly above the def.

2. **`get_user_posts` counts the wrong thing** —
   [routers/users.py:275](routers/users.py#L275). The count query is
   `select(func.count()).select_from(models.Post)` with no
   `.where(Post.user_id == user_id)`, so `total` and `has_more` reflect *all* posts in
   the system, not that user's. Pagination metadata is wrong on this endpoint.

3. **Junk/auto-import lines** — `from pyexpat import model`
   ([routers/posts.py:1](routers/posts.py#L1), [routers/users.py:2](routers/users.py#L2)),
   `from PIL.ImageChops import offset` ([routers/users.py:17](routers/users.py#L17)),
   `import token` ([auth.py:3](auth.py#L3)). Unused, almost certainly IDE auto-import
   mistakes. Remove them.

4. **User-facing typos** — "Apassword is incorrect"
   ([routers/users.py:238](routers/users.py#L238)), "password reset successfull"
   ([routers/users.py:225](routers/users.py#L225)), "password changes succesfully"
   ([routers/users.py:249](routers/users.py#L249)).

5. **`likes` is inert** — [models.py:56](models.py#L56) defines a `likes` counter (and a
   migration added it), but there is no like/unlike endpoint and no per-user tracking.
   As designed it's just a number with no integrity (no way to prevent double-likes).
   See Data Integrity below.

---

## Scalability gaps (ordered by impact at scale)

| # | Gap | Why it breaks at scale | Direction |
|---|-----|------------------------|-----------|
| 1 | **OFFSET pagination** ([posts.py:30](routers/posts.py#L30), [users.py:282](routers/users.py#L282)) | `OFFSET 100000` makes the DB scan and discard 100k rows per request. Gets linearly slower the deeper you page. | Keyset/cursor pagination on `(date_posted DESC, id DESC)` — "give me posts older than this cursor". |
| 2 | **`SELECT COUNT(*)` on every list call** ([posts.py:23](routers/posts.py#L23), [main.py:45](main.py#L45)) | Full-table count is expensive on large tables and runs on every page load. | Drop exact totals for feeds (cursor pagination doesn't need them), or cache an approximate count. |
| 3 | **`date_posted` is not indexed** ([models.py:52](models.py#L52)) | Every feed query orders by `date_posted DESC` — without an index that's a sort over the whole table. | Add index on `date_posted`, and a composite `(user_id, date_posted DESC)` for the per-user feed. |
| 4 | **No DB connection-pool tuning** ([database.py:6](database.py#L6)) | `create_async_engine(url)` uses defaults (pool size 5). Many replicas × few connections each can still exhaust Postgres's connection limit. | Set `pool_size`, `max_overflow`, `pool_pre_ping=True`, `pool_recycle`. At real scale, put **PgBouncer** in front of Postgres. |
| 5 | **No caching layer** | Every home-feed and profile read hits Postgres. The feed is the hottest, most cacheable path. | Add **Redis** for hot reads (feed page 1, user profiles) with short TTLs + invalidation on write. |
| 6 | **Email via `BackgroundTasks`** ([users.py:169](routers/users.py#L169)) | In-process tasks die with the worker, have no retries, and don't survive a deploy/crash. SMTP latency also ties up the worker. | Move to a durable task queue (**arq**/Celery/RQ) with a broker; workers handle email + retries. |
| 7 | **Image processing inline** ([users.py:407](routers/users.py#L407)) | PIL resize is CPU-bound; even in a threadpool it competes with request handling. At volume it starves the event loop's thread pool. | Offload to the same worker queue; return 202 and process async. |
| 8 | **Upload read fully into memory before size check** ([users.py:399](routers/users.py#L399)) | `await file.read()` buffers the whole upload before the size guard runs — a memory-exhaustion vector. | Enforce body limit at the proxy (nginx `client_max_body_size`) and stream/limit in app. |
| 9 | **New boto3 client per call** ([image_utils.py:11](image_utils.py#L11)) | Rebuilds the client (and connection setup) on every upload/delete. | Reuse a module-level client, or `aioboto3`. |

> Note: items 5–7 (Redis, queue, async workers) are the ones that genuinely matter only
> at high volume. For a portfolio app, understanding *why* they're needed is the goal;
> you don't have to run them.

---

## Reliability & operations gaps

This is the biggest category of "missing entirely" — none of the standard
production-operations layer exists yet:

- **No health/readiness endpoints** — load balancers and orchestrators need `/health`
  (liveness) and `/ready` (DB reachable) to route traffic safely.
- **No tests** — there are zero test files. For production confidence you'd want pytest +
  `httpx.AsyncClient` covering auth, ownership checks, and pagination.
- **No observability** — `sentry-sdk` is installed in the venv but **never wired up**.
  No error tracking, no metrics (Prometheus), no tracing. You're blind in production.
- **No structured logging** — only ad-hoc `logger.exception` in
  [email_utils.py](email_utils.py). Need JSON logs + request IDs.
- **No rate limiting** — `/token`, `/forgot-password`, and `/users` (registration) are
  wide open to brute force and abuse. (Also a security item.)
- **No containerization / CI / deploy** — no Dockerfile, no docker-compose, no GitHub
  Actions. No reproducible build or automated checks.
- **No CORS config** — fine while same-origin (server-rendered), but blocks a separate
  SPA/mobile client later.
- **No timeouts / circuit breaking** on external calls (S3, SMTP) — a slow dependency
  can pile up requests.
- **Multi-process serving not configured** — needs gunicorn + uvicorn workers (or
  multiple uvicorn replicas) to use more than one CPU core.

---

## Security gaps

- **JWT stored in `localStorage`** ([static/js/auth.js:14](static/js/auth.js#L14)) — any
  XSS on the page can steal the token. Prefer an **httpOnly, Secure, SameSite cookie**
  (+ CSRF protection for state-changing requests) for the web client.
- **No token revocation / refresh** — logout is client-side only
  ([auth.js:45](static/js/auth.js#L45)); a stolen token is valid until it expires and
  can't be killed. Real systems use short-lived access tokens + a refresh token with a
  server-side revocation list.
- **No security headers** — only `Referrer-Policy` on one page
  ([main.py:180](main.py#L180)). Missing CSP, HSTS, `X-Content-Type-Options`,
  `X-Frame-Options`. Add via middleware.
- **Case-insensitive uniqueness is enforced in app code, not the DB** —
  ([users.py:64](routers/users.py#L64)) checks `lower(email)`/`lower(username)`, but the
  DB unique constraint is on the raw column ([models.py:16](models.py#L16)). Two
  concurrent registrations of "Bob"/"bob" can both pass the check and create duplicates.
  Enforce with a **unique functional index on `lower(...)`** (or `citext`).
- **No email verification at signup** — accounts are usable immediately with any email.
- **No account lockout / backoff** on repeated failed logins.

---

## Data integrity gaps

- **FKs have no `ON DELETE` rule** ([models.py:47](models.py#L47),
  [models.py:65](models.py#L65)). The ORM `cascade="all, delete-orphan"` works by loading
  every child row into memory and deleting it one by one — deleting a user with thousands
  of posts is slow and memory-heavy. Use DB-level `ondelete="CASCADE"` + `passive_deletes`.
- **`likes` has no integrity model** — to support real likes you need a `post_likes`
  join table `(user_id, post_id)` with a unique constraint, so a user can't like twice
  and the count is derivable/consistent.
- **No `updated_at` columns** — can't tell when a post/user was last modified; complicates
  cache invalidation and auditing.

---

## Recommended roadmap (priority order for a learning project)

### Tier 0 — correctness (do first, small, high value)
Fix the 5 bugs above: register `change_password`, fix the `get_user_posts` count, remove
junk imports, fix typos. Add the DB indexes (`date_posted`, composite `(user_id,
date_posted)`) and DB-level case-insensitive uniqueness.

### Tier 1 — production baseline (the "you must have these" layer)
Health/readiness endpoints, a rate limiter (e.g. `slowapi`) on auth routes,
security-headers middleware, wire up Sentry, structured logging with request IDs, a
Dockerfile + docker-compose (app + Postgres), and a starter pytest suite for auth +
ownership + pagination. These teach the most about "production" per unit of effort.

### Tier 2 — scale primitives (build to learn the concepts)
Connection-pool tuning, keyset pagination, Redis caching on the feed, and a durable task
queue (arq) for email + image processing. This is where you actually learn what scaling
costs and why.

### Tier 3 — real-fleet concerns (mostly conceptual for a portfolio)
PgBouncer, read replicas, CDN in front of S3 media, httpOnly-cookie + refresh-token auth
with revocation, multi-replica deploy behind a load balancer, Prometheus/Grafana metrics
and tracing. Understand these; implement only if the app becomes real.

---

## How to validate (when you implement)

- **Correctness:** add pytest + `httpx.AsyncClient` tests; confirm `change_password` and
  `get_user_posts` counts behave correctly, and that ownership 403s hold.
- **Pagination/index wins:** seed ~100k posts (`populate_db.py` is a starting point),
  then compare query plans (`EXPLAIN ANALYZE`) and latency for OFFSET vs keyset at deep
  pages, before/after adding the `date_posted` index.
- **Load behavior:** run a load test (`locust` or `k6`) against the feed; watch p95
  latency and DB connection counts as concurrency rises — this makes the pool/caching
  arguments concrete.
- **Ops:** hit `/health` and `/ready`, kill Postgres and confirm `/ready` fails;
  trigger an error and confirm it lands in Sentry.

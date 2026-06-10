# FastAPI Blog Backend

This project is a FastAPI backend for  blog application. It exposes JSON APIs for users, authentication, password resets, profile images, and posts. The app also renders a few server-side HTML pages, but the core backend is the FastAPI API layer, async SQLAlchemy models, Alembic migrations, SMTP email integration, and optional S3 profile image storage.

## Tech Stack

- FastAPI with async route handlers
- SQLAlchemy 2.x async ORM
- Alembic database migrations
- Pydantic and pydantic-settings for request validation and environment config
- PyJWT bearer token authentication
- pwdlib with Argon2 password hashing
- aiosmtplib for password reset email delivery through Mailtrap SMTP
- Pillow for profile image processing
- boto3 for optional S3 profile image storage
- uv for dependency management

## Project Structure

```text
.
|-- main.py                 # FastAPI app, router registration, page routes, error handlers
|-- config.py               # Pydantic settings loaded from .env
|-- database.py             # Async SQLAlchemy engine and session dependency
|-- models.py               # SQLAlchemy ORM models
|-- schemas.py              # Pydantic request/response models
|-- auth.py                 # Password hashing, JWT creation/verification, current-user dependency
|-- email_utils.py          # SMTP email sending and password reset email composition
|-- image_utils.py          # Image resize/format conversion and S3 upload/delete helpers
|-- routers/
|   |-- users.py            # User, auth, password reset, and profile picture API routes
|   `-- posts.py            # Post API routes
|-- alembic/                # Database migration environment and revisions
|-- templates/              # Server-rendered HTML templates
|-- static/                 # Static files and default profile image
|-- populate_db.py          # Optional seed script
|-- pyproject.toml          # Project metadata and dependencies
`-- uv.lock                 # Locked dependency versions
```

## Setup

### 1. Install prerequisites

- Python 3.13 or newer
- uv
- A database supported by the configured SQLAlchemy URL

For quick local development, SQLite works with the included `aiosqlite` dependency. PostgreSQL is also supported through `psycopg`.

### 2. Install dependencies

```bash
uv sync
```

### 3. Create the environment file

Copy `.env.example` to `.env` and update the required values:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, set:

- `DATABASE_URL`
- `SECRET_KEY`

Example local SQLite URL:

```env
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

Example PostgreSQL URL:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/fastapi_blog
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
```

Alembic reads the database URL from `config.py`, which loads `.env`.

### 5. Run the development server

```bash
uv run fastapi dev main.py
```

The API will be available at:

- App: `http://127.0.0.1:8000`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Environment Variables

Required:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Async SQLAlchemy database URL. |
| `SECRET_KEY` | Secret used to sign JWT access tokens. |

Optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT lifetime. |
| `MAX_UPLOAD_SIZE_BYTES` | `5242880` | Maximum uploaded profile image size. |
| `POSTS_PER_PAGE` | `5` | Page size for server-rendered post lists. |
| `RESET_TOKEN_EXPIRE_MINUTES` | `60` | Password reset token lifetime. |
| `MAIL_SERVER` | `localhost` | SMTP host. Use the Mailtrap SMTP host for development email testing. |
| `MAIL_PORT` | `587` | SMTP port. |
| `MAIL_USERNAME` | empty | Mailtrap SMTP username. Must be paired with `MAIL_PASSWORD`. |
| `MAIL_PASSWORD` | empty | Mailtrap SMTP password. Must be paired with `MAIL_USERNAME`. |
| `MAIL_FROM` | `noreply@example.com` | Sender address for password reset emails. |
| `MAIL_USE_TLS` | `true` | Whether SMTP uses STARTTLS. |
| `FRONTEND_URL` | `http://localhost:8000` | Base URL used when generating password reset links. |
| `S3_BUCKET_NAME` | empty | Optional bucket for uploaded profile pictures. |
| `S3_REGION` | empty | Optional S3 region, such as `ap-southeast-2`. |
| `S3_ACCESS_KEY_ID` | empty | Optional S3 access key. |
| `S3_SECRET_ACCESS_KEY` | empty | Optional S3 secret key. |
| `S3_ENDPOINT_URL` | empty | Optional custom S3-compatible endpoint. |

## Backend Architecture

### High-Level System Diagram

```mermaid
flowchart TD
    Client["Browser or API client"]
    FastAPI["FastAPI backend"]
    Validation["Request validation and response schemas"]
    Auth["Authentication layer<br/>OAuth2 form login, JWT bearer tokens, Argon2 password hashing"]
    Domain["User, post, password reset, and profile image workflows"]
    DBLayer["Async SQLAlchemy data access"]
    Migrations["Alembic migrations"]
    Database["PostgreSQL in production<br/>SQLite supported for local development"]
    Email["Password reset email"]
    SMTP["Mailtrap SMTP provider"]
    Images["Profile image processing"]
    S3["AWS S3 or S3-compatible object storage"]
    Pages["Server-rendered HTML pages and static assets"]

    Client --> FastAPI
    FastAPI --> Validation
    FastAPI --> Auth
    FastAPI --> Domain
    FastAPI --> Pages

    Auth --> DBLayer
    Domain --> DBLayer
    DBLayer --> Database
    Migrations --> Database

    Domain --> Email
    Email --> SMTP

    Domain --> Images
    Images --> S3
```

### Request Flow

1. A browser or API client sends a request to the FastAPI backend.
2. FastAPI validates incoming data and routes the request to the matching backend workflow.
3. Public actions, such as registration, login, post listing, and password reset requests, can run without a JWT.
4. Login verifies the submitted password against the stored Argon2 password hash and returns a signed JWT access token.
5. Protected actions require an `Authorization: Bearer <token>` header. The backend verifies the JWT signature and expiration, then loads the current user from the database.
6. Application data is read and written through async SQLAlchemy. PostgreSQL is the production-style database target, while SQLite is available for local development.
7. Alembic manages database schema changes so the database structure stays aligned with the application models.
8. Password reset requests create a short-lived reset token and send the reset link through Mailtrap using SMTP.
9. Profile image uploads are processed by the backend before being stored in AWS S3 or another S3-compatible object store when configured.

## API Surface

### Users and Auth

Base path: `/api/users`

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/users` | No | Create a user. |
| `POST` | `/api/users/token` | No | Login with email/password and return a bearer token. |
| `GET` | `/api/users/me` | Yes | Return the authenticated user's private profile. |
| `POST` | `/api/users/forgot-password` | No | Create a password reset token and send email in the background. |
| `POST` | `/api/users/reset-password` | No | Reset password using a reset token. |
| `GET` | `/api/users/{user_id}` | No | Return a public user profile. |
| `GET` | `/api/users/{user_id}/posts` | No | Return paginated posts for one user. |
| `PATCH` | `/api/users/{user_id}` | Yes, owner only | Update username and/or email. |
| `DELETE` | `/api/users/{user_id}` | Yes, owner only | Delete the user. |
| `PATCH` | `/api/users/{user_id}/picture` | Yes, owner only | Process and upload a profile picture. |
| `DELETE` | `/api/users/{user_id}/picture` | Yes, owner only | Delete the current profile picture. |

### Posts

Base path: `/api/posts`

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/posts` | No | Return paginated posts. |
| `POST` | `/api/posts` | Yes | Create a post for the authenticated user. |
| `GET` | `/api/posts/{post_id}` | No | Return one post. |
| `PUT` | `/api/posts/{post_id}` | Yes, owner only | Replace a post. |
| `PATCH` | `/api/posts/{post_id}` | Yes, owner only | Partially update a post. |
| `DELETE` | `/api/posts/{post_id}` | Yes, owner only | Delete a post. |

## Authentication Model

1. Users register with `POST /api/users`.
2. Passwords are hashed with pwdlib's recommended Argon2 configuration before storage.
3. Users login with `POST /api/users/token`. The OAuth2 form `username` field is treated as the user's email.
4. The backend returns a JWT bearer token with the user ID in the `sub` claim.
5. Protected endpoints use the `CurrentUser` dependency from `auth.py`.
6. JWT verification checks signature, expiration, and subject before loading the user from the database.


## Database Migrations

Create a new migration after model changes:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Roll back one migration:

```bash
uv run alembic downgrade -1
```

## Development Notes

- Keep secrets in `.env`; `.env` and `.env.*` are ignored by git.
- Commit `.env.example` when configuration changes.
- API schemas live in `schemas.py`; keep response models from exposing internal fields such as `password_hash`.
- The app uses async SQLAlchemy sessions through `Depends(get_db)`.
- Protected routes should use `CurrentUser` and then enforce ownership where required.

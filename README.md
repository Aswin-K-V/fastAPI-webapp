# FastAPI Blog Backend

This project is a FastAPI backend for a small blog application. It exposes JSON APIs for users, authentication, password resets, profile images, and posts. The app also renders a few server-side HTML pages, but the core backend is the FastAPI API layer, async SQLAlchemy models, Alembic migrations, SMTP email integration, and optional S3 profile image storage.

## Tech Stack

- FastAPI with async route handlers
- SQLAlchemy 2.x async ORM
- Alembic database migrations
- Pydantic and pydantic-settings for request validation and environment config
- PyJWT bearer token authentication
- pwdlib with Argon2 password hashing
- aiosmtplib for password reset email delivery
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
| `MAIL_SERVER` | `localhost` | SMTP host. |
| `MAIL_PORT` | `587` | SMTP port. |
| `MAIL_USERNAME` | empty | SMTP username. Must be paired with `MAIL_PASSWORD`. |
| `MAIL_PASSWORD` | empty | SMTP password. Must be paired with `MAIL_USERNAME`. |
| `MAIL_FROM` | `noreply@example.com` | Sender address for password reset emails. |
| `MAIL_USE_TLS` | `true` | Whether SMTP uses STARTTLS. |
| `FRONTEND_URL` | `http://localhost:8000` | Base URL used when generating password reset links. |
| `S3_BUCKET_NAME` | empty | Optional bucket for uploaded profile pictures. |
| `S3_REGION` | empty | Optional S3 region, such as `ap-southeast-2`. |
| `S3_ACCESS_KEY_ID` | empty | Optional S3 access key. |
| `S3_SECRET_ACCESS_KEY` | empty | Optional S3 secret key. |
| `S3_ENDPOINT_URL` | empty | Optional custom S3-compatible endpoint. |

## Backend Architecture

### Runtime Flow

```mermaid
flowchart TD
    Client[Client or browser] --> App[FastAPI app in main.py]
    App --> UsersRouter[/api/users router]
    App --> PostsRouter[/api/posts router]
    App --> PageRoutes[Server-rendered page routes]

    UsersRouter --> Auth[auth.py]
    UsersRouter --> Schemas[schemas.py]
    UsersRouter --> DBSession[get_db dependency]
    UsersRouter --> Email[email_utils.py]
    UsersRouter --> Images[image_utils.py]

    PostsRouter --> CurrentUser[CurrentUser dependency]
    PostsRouter --> Schemas
    PostsRouter --> DBSession

    CurrentUser --> Auth
    Auth --> DBSession
    DBSession --> ORM[SQLAlchemy ORM models]
    ORM --> Database[(Database)]

    Email --> SMTP[(SMTP server)]
    Images --> S3[(S3 or S3-compatible storage)]
```

### Configuration and Persistence

```mermaid
flowchart LR
    EnvFile[.env] --> Settings[config.Settings]
    Settings --> App[FastAPI app]
    Settings --> Engine[Async SQLAlchemy engine]
    Settings --> JWT[JWT signing]
    Settings --> Mail[SMTP client]
    Settings --> Storage[S3 client]

    Engine --> Sessions[AsyncSessionLocal]
    Sessions --> Routes[API route dependencies]
    Routes --> Models[ORM models]
    Models --> DB[(Database)]

    Alembic[Alembic env.py] --> Settings
    Alembic --> DB
```

### Entity Relationship Diagram

```mermaid
erDiagram
    users ||--o{ posts : writes
    users ||--o{ password_reset_tokens : owns

    users {
        int id PK
        string username UK
        string email UK
        string password_hash
        string image_file
    }

    posts {
        int id PK
        string title
        text content
        int user_id FK
        datetime date_posted
        int likes
    }

    password_reset_tokens {
        int id PK
        int user_id FK
        string token_hash UK
        datetime expires_at
        datetime created_at
    }
```

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

## Password Reset Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI users router
    participant DB as Database
    participant Mail as SMTP server

    Client->>API: POST /api/users/forgot-password
    API->>DB: Find user by email
    API->>DB: Delete old reset tokens
    API->>DB: Store SHA-256 hash of new token
    API-->>Client: 202 accepted
    API->>Mail: Send reset link as background task

    Client->>API: POST /api/users/reset-password
    API->>DB: Match hashed token
    API->>DB: Update password hash
    API->>DB: Delete reset tokens for user
    API-->>Client: 200 OK
```

## Profile Image Flow

1. Authenticated user uploads an image to `/api/users/{user_id}/picture`.
2. The route enforces `MAX_UPLOAD_SIZE_BYTES`.
3. Pillow normalizes EXIF orientation, crops/resizes to `300x300`, converts to JPEG, and generates a UUID filename.
4. The processed image is uploaded to `profile_pics/{filename}` in the configured S3 bucket.
5. The user's `image_file` column stores only the filename.
6. `User.image_path` builds the public S3 URL when S3 is configured, otherwise it falls back to `/static/profile_pics/default.jpg`.

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

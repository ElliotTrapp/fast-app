# Auth Setup Guide

## Overview

Fast-App supports multi-user authentication with JWT tokens and bcrypt password hashing. Auth is **disabled by default** — the system works identically to how it does today. When you're ready to add users, set a JWT secret and create your first account.

This guide covers the fundamentals of how auth works in Fast-App, how to enable it, and how to use it with both the CLI and webapp.

---

## Auth Fundamentals

### How does password auth work?

When you create an account:

1. Your password is **hashed** using bcrypt (a slow, secure hashing algorithm)
2. Only the **hash** is stored in the database — never the plaintext password
3. When you log in, the password you enter is hashed and compared to the stored hash
4. If they match, a **JWT token** is issued

This means even if the database is compromised, your password cannot be recovered from the hash.

### What is bcrypt?

bcrypt is a password hashing algorithm designed specifically for passwords. It:

- **Is slow by design**: Takes ~400ms per hash (cost factor 12). This makes brute-force attacks expensive.
- **Embeds the salt**: Each hash contains a unique random salt, so two users with the same password get different hashes.
- **Is battle-tested**: Has been the industry standard since 1999.

### What is a JWT?

JSON Web Token (JWT) is a standard for transmitting authenticated information. After login, the server issues a JWT that the client includes with every subsequent request. A JWT contains:

- **Header**: Algorithm and token type
- **Payload**: User ID and expiration time
- **Signature**: Proves the token hasn't been tampered with

JWTs are **stateless** — the server doesn't need to store sessions. The token itself proves identity.

### Token expiry

Tokens expire after 24 hours by default. You can configure this:

```bash
# Set token expiry to 7 days
export FAST_APP_JWT_EXPIRE_MINUTES=10080
```

When a token expires, the user must log in again.

### Timing attack prevention

When checking credentials, Fast-App always hashes the password even if the email doesn't exist. This prevents attackers from determining which emails are registered by measuring response times.

---

## Enabling Auth

### Step 1: Set a JWT secret

```bash
# Generate a secure random secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Example output: aBcDeFgH1234567890abcdefghijklmnopqrstuvwxyz1234

# Set it as an environment variable
export FAST_APP_JWT_SECRET="your-generated-secret-here"
```

**Important**: Keep this secret secure. Anyone with the secret can forge valid tokens. In production, use a secrets manager, not `.env` files.

### Step 2: Create the first user

```bash
# Using the CLI
fast-app auth signup --email you@example.com --password "your-strong-password"

# Or via the API
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-strong-password"}'
```

The response will include a JWT token:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### Step 3: Use the token

**CLI — One-time flag:**

```bash
fast-app generate <url> --token "eyJhbGciOiJIUzI1NiIs..."
```

**CLI — Persistent login:**

```bash
# Login stores the token in ~/.fast-app/auth.json
fast-app auth login --email you@example.com --password "your-strong-password"

# Subsequent commands use the stored token automatically
fast-app generate <url>
```

**Webapp — Browser handles tokens:**

After signup/login, the token is stored in an httpOnly, Secure, SameSite=Strict cookie. You don't need to manage it manually.

---

## Auth-Disabled Mode (Default)

When `FAST_APP_JWT_SECRET` is not set and no users exist in the database:

- All CLI commands work without authentication
- All webapp endpoints work without authentication
- No login page appears in the webapp
- `Depends(get_current_user)` returns `None`

This means **zero config required for single-user use**. Auth only activates when you explicitly enable it.

---

## Auth API Reference

### POST /api/auth/signup

Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure-password-123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
- `400` — Email already registered
- `422` — Validation error (empty email, password too short)

### POST /api/auth/login

Authenticate an existing user.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure-password-123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
- `401` — Invalid email or password

### GET /api/auth/me

Get the current authenticated user.

**Headers:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2025-01-15T10:30:00Z"
}
```

---

## CLI Auth Commands

```bash
# Create an account
fast-app auth signup --email you@example.com --password "your-password"

# Log in (stores token in ~/.fast-app/auth.json)
fast-app auth login --email you@example.com --password "your-password"

# Show current user info
fast-app auth whoami

# Log out (removes stored token)
fast-app auth logout
```

---

## Security Considerations

1. **Secret key rotation**: If the JWT secret is compromised, change it and all existing tokens become invalid. Users must re-authenticate.
2. **HTTPS**: In production, always serve the webapp over HTTPS. JWT tokens in cookies or headers are visible on unencrypted connections.
3. **Password requirements**: Currently no minimum requirements beyond non-empty. Consider adding validation (minimum length, complexity) in production.
4. **Token storage**: CLI tokens are stored in `~/.fast-app/auth.json` with file permissions `0600` (owner read/write only). This is similar to SSH key storage.
5. **httpOnly cookies**: Webapp tokens use httpOnly, Secure, SameSite=Strict cookies. JavaScript cannot access them, preventing XSS token theft.

---

## Troubleshooting

### "FAST_APP_JWT_SECRET must be set for authentication"

You tried to use auth commands without setting the JWT secret. Either:
- Set `FAST_APP_JWT_SECRET` environment variable, or
- Continue using the system without auth (auth-disabled mode)

### Token expired

Tokens expire after 24 hours by default. Re-authenticate:

```bash
fast-app auth login --email you@example.com --password "your-password"
```

### Cannot connect to database

By default, Fast-App uses a SQLite database at `~/.fast-app/fast_app.db`. If you see connection errors:
- Check the directory exists: `mkdir -p ~/.fast-app`
- Check file permissions
- Or set a custom path: `export FAST_APP_DB_PATH="/path/to/custom.db"`

### Multiple users on the same machine

Each user authenticates with their own token. The CLI stores tokens in `~/.fast-app/auth.json`. To switch users, run `fast-app auth login` with different credentials.
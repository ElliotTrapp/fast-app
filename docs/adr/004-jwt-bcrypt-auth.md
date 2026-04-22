# ADR-004: JWT Auth with bcrypt Password Hashing

## Context

Fast-App needs user authentication for multi-user support. When users log in to the webapp or use the CLI with authentication, the system needs to:

1. **Verify identity**: Confirm the user is who they claim to be (email + password)
2. **Authorize requests**: Determine which user made each API request
3. **Protect passwords**: Store passwords in a way that survives database breaches

This is the first time fast-app will have any authentication, so this ADR covers the fundamentals thoroughly.

### Auth fundamentals

**Why not just store passwords in the database?**

Storing plaintext passwords means a database breach exposes every user's password. Since users reuse passwords across services, this endangers their accounts everywhere. **We must store only the hash.**

**What is password hashing?**

A hash function converts a password into a fixed-length string that cannot be reversed:

```
"my_password" → bcrypt → "$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdq17xZiq"
```

Key properties:
- **One-way**: You cannot derive the password from the hash
- **Deterministic**: Same password + same salt = same hash (for verification)
- **Slow by design**: bcrypt takes ~100ms per hash, making brute-force attacks expensive

**What is a salt?**

A salt is random data added to the password before hashing. It prevents:
- **Rainbow table attacks**: Pre-computed tables of common password hashes
- **Duplicate detection**: Two users with the same password get different hashes

bcrypt generates the salt automatically and embeds it in the hash string.

**What is bcrypt?**

bcrypt is a password hashing algorithm designed specifically for passwords. It:
- Uses a cost factor (work factor) that makes hashing intentionally slow
- Embeds the salt in the output hash string (no separate salt storage needed)
- Is resistant to GPU-based attacks (unlike SHA-256, which is fast on GPUs)
- Has been the standard for password hashing since 1999

Cost factor determines how many rounds of hashing to perform:
- Cost 10: ~100ms per hash (good default)
- Cost 12: ~400ms per hash (more secure, slower)
- Cost 14: ~1.5s per hash (high security, very slow)

Fast-App uses **cost 12** as a balance between security and user experience.

**What is JWT?**

JSON Web Tokens (JWT) are a standard for securely transmitting information between parties as a JSON object. After login, the server issues a JWT that the client includes with every subsequent request.

A JWT has three parts:
```
header.payload.signature
```

- **Header**: Algorithm and token type (`{"alg": "HS256", "typ": "JWT"}`)
- **Payload**: Claims — user ID, expiration, etc. (`{"sub": "42", "exp": 1700000000}`)
- **Signature**: HMAC-SHA256 of header + payload using a secret key

Key properties:
- **Stateless**: The server doesn't need to store sessions — the token contains all needed info
- **Verifiable**: The signature proves the token hasn't been tampered with
- **Expiring**: Tokens have an `exp` claim; after expiration, the client must re-authenticate

**Why JWT instead of sessions?**

| Aspect | JWT | Session cookies |
|--------|-----|----------------|
| Server state | None (stateless) | Must store session data |
| CLI support | Bearer token in header | Cookie-based (browser only) |
| Scaling | No shared session store | Requires shared session store |
| Revocation | Hard (until expiry) | Easy (delete session) |
| Mobile API | Natural | Awkward |

Fast-App needs CLI support (Bearer tokens) and webapp support (httpOnly cookies), making JWT the better fit.

**What are timing attacks?**

A timing attack exploits the time difference between "user not found" (~1ms) and "wrong password" (~100ms with bcrypt). An attacker can determine if an email exists by measuring response times.

**Mitigation**: Always hash a password even when the user doesn't exist:

```python
async def authenticate_user(email: str, password: str) -> User | None:
    user = await get_user_by_email(email)
    if user is None:
        # Hash anyway to prevent timing attack
        verify_password("dummy", hash_password(password))
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
```

## Decision

Use **JWT** for authentication tokens and **bcrypt** (via `passlib`) for password hashing.

### Token flow

```
1. Signup: POST /api/auth/signup
   → hash_password(password) → store in User table
   → create_access_token(user_id) → return {access_token, token_type}

2. Login: POST /api/auth/login
   → verify_password(password, user.hashed_password)
   → create_access_token(user_id) → return {access_token, token_type}

3. Authenticated request:
   → CLI: Authorization: Bearer <token>
   → Webapp: httpOnly cookie named "fast_app_token"
   → decode_access_token(token) → User object
```

### Implementation

```python
# services/auth.py

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt with cost factor 12."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)

# JWT tokens
SECRET_KEY = os.environ.get("FAST_APP_JWT_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    if not SECRET_KEY:
        raise ValueError("FAST_APP_JWT_SECRET must be set for authentication")
    
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise ValueError("Invalid or expired token")

# FastAPI dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    """
    FastAPI dependency that extracts and validates the current user from a JWT.
    
    Returns None if auth is disabled (no JWT secret and no users in DB).
    Returns the User object if the token is valid.
    Raises HTTPException(401) if the token is invalid.
    """
    if not SECRET_KEY:
        return None  # Auth disabled
    
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        user = session.get(User, user_id)
        if user and user.is_active:
            return user
    except (ValueError, JWTError):
        pass
    
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

### Security considerations

1. **Secret key**: `FAST_APP_JWT_SECRET` must be a cryptographically random string in production. Auto-generated on first run if not set.
2. **httpOnly cookies**: Webapp tokens stored in httpOnly, Secure, SameSite=Strict cookies — prevents XSS token theft.
3. **Bearer tokens**: CLI uses `Authorization: Bearer <token>` header — standard REST API auth.
4. **Token expiry**: 24 hours by default, configurable via `FAST_APP_JWT_EXPIRE_MINUTES`.
5. **Timing attack prevention**: Always hash password even for non-existent users.
6. **No token revocation**: JWT tokens are stateless. To revoke, change `FAST_APP_JWT_SECRET`. For more sophisticated revocation, add a token blacklist later.

### Auth-disabled mode

When `FAST_APP_JWT_SECRET` is not set and the `users` table is empty:
- `get_current_user()` returns `None`
- All endpoints work without authentication
- CLI commands work exactly as they do today
- This is the **default** — no setup required for single-user use

When `FAST_APP_JWT_SECRET` is set OR users exist in the database:
- Protected endpoints require a valid JWT
- The `--token` flag provides the JWT for CLI commands
- The webapp redirects to login/signup

### Dependencies

```toml
[project.optional-dependencies]
auth = [
    "sqlmodel>=0.0.22",
    "aiosqlite>=0.20.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "bcrypt>=4.0.0",
]
```

## Consequences

### Positive

- **Stateless auth**: No session store. Tokens contain all needed info.
- **CLI + webapp support**: Bearer tokens for CLI, httpOnly cookies for webapp.
- **Zero infra**: No Redis, no session database. Just SQLite + a secret key.
- **Backward compatible**: Auth-disabled mode means existing users see zero change.
- **Industry standard**: JWT + bcrypt is the most common auth pattern for REST APIs.

### Negative

- **No token revocation**: Changing the secret invalidates all tokens. For fine-grained revocation, a token blacklist in the DB is needed. Not included in Phase 1.
- **JWT size**: Tokens are ~200 bytes, sent with every request. Negligible for our use case.
- **bcrypt cost**: ~400ms per login at cost 12. Acceptable for a tool with low login frequency.
- **Secret key management**: The secret must be kept secure and consistent across server restarts. Environment variable is standard practice.

### Alternatives considered

| Approach | Why not |
|----------|---------|
| **Session cookies** | Requires session store, no CLI support, server state |
| **API keys** | No password verification, no signup/login flow, not per-session |
| **OAuth2 / social login** | Over-engineered for a self-hosted tool, adds external dependencies |
| **Argon2** | Better than bcrypt (memory-hard) but less widely supported in Python libraries. `passlib` doesn't include it by default. bcrypt is sufficient. |
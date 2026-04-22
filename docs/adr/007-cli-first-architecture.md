# ADR-007: CLI-First Architecture

## Context

Fast-App started as a CLI tool. The webapp was added later as a browser-based interface. Currently, the webapp calls the same Python functions that the CLI calls — but this wasn't always clean, and there's risk of the webapp becoming a separate implementation.

As we add auth, profiles, and knowledge features, there's a natural temptation to build them webapp-first (because that's where auth UI lives). This would create two problems:

1. **Feature divergence**: CLI and webapp implement the same features differently
2. **Testing burden**: Every feature needs to be tested in two places

## Decision

All new services (Auth, Profile, Knowledge, LLM) must be **CLI-accessible first**. The webapp is a thin HTTP wrapper around the same service layer.

### Architecture rule

```
CLI commands  ──→  Service layer  ←──  Webapp routes (FastAPI)
                     │
              ┌──────┼──────┐
              │      │      │
           Auth   Profile  Knowledge
           Service Service  Service
              │      │      │
              ▼      ▼      ▼
           SQLite  SQLite  ChromaDB
```

No webapp route should contain business logic. Every route should:
1. Parse the HTTP request
2. Call the service layer
3. Format the response

### CLI commands

```bash
# Authentication
fast-app auth signup --email user@example.com --password secret
fast-app auth login --email user@example.com --password secret
fast-app auth whoami                          # Show current user

# Profile management
fast-app profile list                          # List all profiles
fast-app profile show [id]                     # Show profile details
fast-app profile create --name "Work"          # Create a new profile
fast-app profile import ./profile.json          # Import from JSON file
fast-app profile export [id] --output profile.json  # Export to JSON
fast-app profile delete [id]                    # Delete a profile

# Knowledge management
fast-app knowledge list                        # List all stored facts
fast-app knowledge search "Python experience"  # Semantic search
fast-app knowledge delete [fact_id]             # Delete a fact
fast-app knowledge extract <url>               # Extract facts from a job URL

# Generate (existing, with new flags)
fast-app generate <url> --provider ollama      # LLM provider (default: ollama)
fast-app generate <url> --provider opencode-go # Use OpenCode Go
fast-app generate <url> --token <jwt>          # Auth token
fast-app generate <url> --review-facts         # Review facts before storing
fast-app generate <url> --no-knowledge          # Disable knowledge injection
```

### Service layer

Each service is a Python class that can be instantiated from either CLI or webapp:

```python
# services/auth.py — usable from both CLI and webapp
class AuthService:
    def signup(self, email: str, password: str) -> tuple[User, str]:
        """Create a user and return (user, access_token)."""
        ...
    
    def login(self, email: str, password: str) -> tuple[User, str]:
        """Authenticate and return (user, access_token)."""
        ...

# services/knowledge.py — usable from both CLI and webapp
class KnowledgeService:
    def store_facts(self, user_id: int, facts: list[ExtractedFact], ...) -> None:
        """Store extracted facts in ChromaDB."""
        ...
    
    def query_facts(self, user_id: int, query: str, n: int = 5) -> list[KnowledgeSearchResult]:
        """Semantic search for relevant facts."""
        ...
```

### Webapp routes

```python
# webapp/auth_routes.py
@router.post("/api/auth/signup")
async def signup(request: SignupRequest, session: Session = Depends(get_session)):
    auth = AuthService(session)
    user, token = auth.signup(request.email, request.password)
    return {"access_token": token, "token_type": "bearer"}

# webapp/knowledge_routes.py (future, Phase 3)
@router.get("/api/knowledge/search")
async def search_knowledge(
    query: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    knowledge = KnowledgeService(user_id=user.id, session=session)
    results = knowledge.query_facts(query=query, n=5)
    return {"results": results}
```

### Auth in CLI vs. webapp

| Aspect | CLI | Webapp |
|--------|-----|--------|
| **Token storage** | `~/.fast-app/auth.json` (file) | httpOnly cookie (`fast_app_token`) |
| **Token sending** | `--token <jwt>` flag or stored token | `Authorization: Bearer <jwt>` header by browser |
| **Auth flow** | `fast-app auth login` → stores token | Login form → browser stores httpOnly cookie |
| **Token refresh** | Re-run `fast-app auth login` | Automatic via same-site cookie |

### Backward compatibility

When auth is disabled (no `FAST_APP_JWT_SECRET`, no users in DB):
- All CLI commands work without `--token`
- All webapp endpoints work without authentication
- `Depends(get_current_user)` returns `None`
- This is the **default state** — zero config required

When auth is enabled:
- CLI commands require `--token` (or stored token from `fast-app auth login`)
- Webapp endpoints require valid JWT
- Protected operations (profile CRUD, knowledge search) require authentication

## Consequences

### Positive

- **Feature parity**: CLI and webapp always have the same capabilities. No feature exists in only one.
- **Testability**: Services can be tested independently of both CLI and HTTP layers.
- **Simplicity**: Webapp routes are thin wrappers (~5-10 lines each). No business logic in route handlers.
- **Maintainability**: Adding a new feature means: (1) add service method, (2) add CLI command, (3) add webapp route. Clear, repeatable pattern.

### Negative

- **CLI auth UX**: Passing `--token` on every command is annoying. Mitigated by `fast-app auth login` storing the token in `~/.fast-app/auth.json` and CLI commands reading it automatically.
- **File-based token storage**: Tokens stored in a file are less secure than browser cookies. Acceptable for a local CLI tool — the token file has the same threat model as SSH keys in `~/.ssh/`.
- **Double command surface**: Every feature needs both a CLI command and a webapp route. This is the price of CLI-first architecture — but it ensures completeness.

### Design principle verification

Ask yourself for every new feature:

1. **Can I run this from the CLI?** If not, it's not CLI-first.
2. **Does the webapp route contain business logic?** If yes, move it to the service layer.
3. **Can I test this without starting a web server?** If not, the service layer isn't properly separated.
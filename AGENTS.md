# AGENTS.md

## Install & Run

Package is installed via **pipx** from the local source tree. After any code change:

    pipx install . --force

Three CLI entry points (defined in `pyproject.toml` `[project.scripts]`):
- `getmyancestors` — download GEDCOM from FamilySearch (main tool)
- `mergemyancestors` — merge multiple GEDCOM files
- `fstogedcom` — Tkinter GUI (download + merge)

## Testing

**No test suite exists.** Verification is done by running a real export:

    getmyancestors -u <user> -p <pass> -i <ID> -a 2 -d 0 -m --concurrency 20 --max-attempts 3 -o /tmp/test.ged

Full 13-generation export takes ~3 minutes and exercises all code paths including retry/rate-limiting:

    getmyancestors -u <user> -p <pass> -i ID1,ID2 -a 13 -d 0 -m --concurrency 20 --max-attempts 10 -o output.ged

## Architecture

### Concurrency model (`classes/session.py`)

- 20 worker threads share a single FIFO `RequestQueue`
- All HTTP requests (initial + retries) flow through the same queue
- **Global `block_until`**: when any worker gets 429/503, it sets `session.block_until = now + delay`. All workers check this before sending — prevents cascading storms.
- 503 without `Retry-After` defaults to 10s delay
- Workers are daemon threads; `stop_workers()` drains the queue before GEDCOM output
- Stats tracked via `Stats` class: retry_count, status_codes, max_retries_reached

### Auth flow (`Session.login()`)

OAuth2 authorization code flow: XSRF token → login → auth code (may open browser for MFA) → access token. Token stored in session `Authorization` header.

### Data model (`classes/tree.py`)

`Tree` contains `Indi`, `Fam`, `Note`, `Source`, `Memorie` objects. `Tree.print()` writes GEDCOM 5.5.1 with HEAD/INDI/FAM/SOUR/NOTE/TRLR records. Thread-safe access via `Tree.lock`.

### Rate limiting

FamilySearch throttles by cumulative processing time per time window (e.g., 18s execution within 60s). Handled by the `block_until` global pause: active by default, triggered by 429/503 `Retry-After` headers.

## Key Gotchas

- **No linting or formatting config** — no black, ruff, mypy, etc. Follow existing code style.
- **No test suite** — rely on `pipx install --force` + manual run to verify changes.

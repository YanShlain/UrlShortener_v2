STATUS: READY

## What was built
Round 2 fixes for the api service. The README was added and the per-request PRAGMA cost was cut.
- Added `solutions/url-shortener/README.md` with local run steps, the Docker run, `DB_PATH` and `BASE_URL`, and the open-redirect note.
- `api/app/db.py`: `journal_mode=WAL` now runs only in `init_db`, because WAL persists in the file. The redundant `PRAGMA busy_timeout` was removed, since `sqlite3.connect(timeout=5)` already sets it.

## Where each invariant and failure mode is handled
Unchanged from round 1.
- FM-1 and FM-10 (concurrent create, restart idempotence): `api/app/db.py` `create_link` (single-statement `ON CONFLICT(url) DO NOTHING`, code PK, retry) and `init_db`.
- Input validation: `api/app/urls.py` `normalize_url`.
- 413/422/500 handling: `api/app/main.py`.

## Decisions and trade-offs
- I did not change the chunked-body size check or the 405 `no-store` behaviour. The review called both minor and not required.

## Local check results
- ruff passed.
- mypy --strict passed.
- pytest: 122 passed on the second full run.
- The first full run had one failure, `test_perf_10k_links`, on a timing assertion under load. It passed on its own in 13.5 s and in the second full run.

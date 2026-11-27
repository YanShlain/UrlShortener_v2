STATUS: READY

Files: `api/tests/conftest.py`, `api/tests/test_api.py`, `web/src/App.test.tsx` (under the solution folder).

## Assumptions about the contract (design leaves these open)
- `app.main:app` reads `DB_PATH` and `BASE_URL` at import or startup. Tests re-import `app.*` per test with a temp DB.
- The code generator uses `secrets.choice(...)` through the module attribute (`import secrets`). FM-2 and FM-13 force collisions and `healthz` by patching `secrets.choice`.
- Web: `src/App.tsx` default-exports `App`. It has one `<textarea>` or `<input>` (role textbox), a `button[type=submit]`, and a button named /copy/i that turns into "Copied". It POSTs JSON to `/api/links`.

## Scenario map
| Design item | Test(s) |
|---|---|
| Ex 1-7 | test_example_1..7 |
| Ex 8, 9 (UI) | App.test.tsx: success/copy, 422 message |
| Boundaries 10-17 | test_edge_10..17 |
| Traps 18-24, 26 | test_edge_18..24, test_edge_26 |
| Trap 25 (UI XSS) | App.test.tsx: HTML as text, no href |
| Invariants 27-32 | test_risk_fm1, test_edge_29, test_edge_30, test_risk_fm2, test_edge_32, test_edge_concurrent_distinct_urls |
| FM-1 | test_risk_fm1_concurrent_same_url |
| FM-2 | test_risk_fm2_collision_retry_then_exhausted |
| FM-3 | test_risk_fm3_dangerous_schemes |
| FM-4 | test_risk_fm4_userinfo |
| FM-5 | test_risk_fm5_missing_host |
| FM-6 | test_risk_fm6_control_chars |
| FM-7 | test_risk_fm7_normalization_duplicates |
| FM-8 | test_risk_fm8_unknown_code |
| FM-9 | test_risk_fm9_redirect_is_302_not_301 |
| FM-10 | test_risk_fm10_restart_idempotent |
| FM-11 | test_risk_fm11_malformed_requests |
| FM-12 | test_risk_fm12_invalid_port |
| FM-13 | test_risk_fm13_healthz_never_shadowed |
| FM-14 | test_risk_fm14_database_unavailable (DB file replaced by a directory) |
| FM-15 | test_risk_fm15_api_errors_are_displayable plus UI tests: 500, network failure, clipboard missing, clipboard rejected, stale URL cleared |
| FM-16 | test_risk_fm16_base_url_precedence, test_api_short_url_* |
| FM-17 | test_risk_fm17_html_in_url_is_data_only plus UI XSS tests |
| UI loading / success / error / client validation | App.test.tsx |

## Perf
- test_perf_10k_links: 10,000 rows seeded outside the timed region; 200 creates, 200 duplicates, 1,000 redirects, 1 healthz; under 15 s.
- test_perf_concurrent_creates_under_5s: 20 threads, seeded DB; under 5 s.

## Red phase
Without implementation (and without fastapi installed) `pytest api/tests` fails at conftest import. Ruff clean.

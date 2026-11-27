STATUS: READY

# Tests (v2, round 1): recent links

v2 tests are in `api/tests/test_recent_links.py` and `web/src/RecentLinks.test.tsx`. The v1 tests (`api/tests/test_api.py`) still apply. In `web/src/App.test.tsx` the `mockFetch` helper now answers `GET /api/links` with `[]`. Its create assertions look only at POST calls, because the page now also fetches the list on mount.

| Design item | Test(s) |
|---|---|
| Ex 10 newest first, 4 fields | `test_example_10_three_links_newest_first` |
| Ex 11 twelve links, newest 10 | `test_example_11_twelve_links_returns_newest_ten` |
| Ex 12 UI rows, anchor attrs, full URL text | RecentLinks.test "shows a loading state, then the rows..." |
| Ex 13 refresh after create | "reloads the list after a successful create...", "...after a 200..." |
| Boundary 22 empty | `test_edge_22_empty_db_returns_empty_array`; UI "shows an empty state..." |
| Boundary 23 exactly 10 / 11 | `test_edge_23_exactly_10_and_11_links` |
| Boundary 24 same second | `test_edge_24_same_second_orders_by_insertion`, `test_edge_created_at_dominates_rowid` |
| Trap 34 resubmit | `test_edge_34_resubmit_does_not_reorder` |
| Trap 35 routes, 405 | `test_edge_35_route_not_shadowed_and_methods` |
| Trap 36 href only from short_url | UI "renders hostile URLs as inert text..." |
| Trap 37 list failure in UI | UI "shows an inline list error on 500...", "...network failure and invalid JSON" |
| Trap 38 long URL | UI "keeps a 2048-character URL fully in the DOM" |
| Inv 45 redirects | `test_edge_45_every_listed_code_redirects_to_its_url` |
| Inv 46 read-only | `test_edge_46_list_is_read_only` |
| Inv 47 no-store | `test_edge_47_list_is_no_store` |
| Params ignored, base URL, Host, restart | `test_edge_query_params_ignored`, `test_edge_short_url_base_url_env`, `test_edge_short_url_uses_forwarded_host`, `test_api_list_survives_restart` |
| DB failure on list | `test_edge_list_failure_is_generic_500` |
| FM-18 | `test_risk_fm18_ordering_and_tiebreaks` |
| FM-19 | `test_risk_fm19_list_failure_is_isolated`; UI list-error tests |
| FM-20 | `test_risk_fm20_fresh_after_create_no_store`; UI "ignores a stale list response..." |
| FM-21 | UI "every anchor has target=_blank..." (UI-only, no api behaviour) |
| FM-22 | `test_risk_fm22_privacy_notice_in_readme` (README needs "recent links" and "visible to everyone"); UI "shows the privacy notice near the list" |
| FM-23 | `test_risk_fm23_hostile_stored_data_is_inert_json`; UI hostile and 2048-char tests |
| Perf | `test_perf_list_10k_rows` |

UI states covered: loading, success, empty, error (500, network, invalid JSON), recovery after create, stale-response ordering.

Perf: 10,000 seeded rows, 200 sequential `GET /api/links`. Budget: p95 < 50 ms, total < 15 s. The seed is built outside the timed region.

Red phase: against the v1 code, 22 of 22 new Python tests and 12 of 12 new UI tests fail. The 11 adjusted v1 UI tests pass.

## Dispute resolution (round 1, v2)
- `test_risk_fm23_hostile_stored_data_is_inert_json`: builder was right. The input contained a space, which design.md scenario 28 and FM-6 reject with 422. Changed to the space-free `<img/src=x/onerror=alert(1)>`; the intent (markup and quotes stored and returned verbatim) is unchanged.
- `test_risk_fm22_privacy_notice_in_readme`: kept. design.md FM-22 requires the documented notice, and the README at the solution root is the documented place; the README owner (builder) must add "Recent links ... visible to everyone".

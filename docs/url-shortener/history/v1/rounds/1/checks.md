GATE: PASS
ROUND: 1
SOURCE_SHA: d96cef6c69670d813e76a398a8f08919c440734c410de29c28f319c3d27b13f6
TESTS_SHA: 178a4540fbe9bd84a6f4592a94007b41633ae4f2594939cab9d63afa8185ebf7

- [x] test lock
- [x] forbidden patterns
- [x] api: uv sync
- [x] api: ruff
- [x] api: mypy --strict
- [x] api: pytest - 122 passed, 1 warning in 22.47s
- [x] web: npm install
- [x] web: typecheck
- [x] web: test
- [x] web: build
- [x] api: smoke boot

## Slowest tests
```
12.33s call     tests/test_api.py::test_perf_10k_links
0.94s call     tests/test_api.py::test_perf_concurrent_creates_under_5s
0.83s call     tests/test_api.py::test_risk_fm10_restart_idempotent
0.76s call     tests/test_api.py::test_risk_fm1_concurrent_same_url
0.46s call     tests/test_api.py::test_edge_concurrent_distinct_urls
```

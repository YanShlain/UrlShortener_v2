GATE: PASS
ROUND: 1
SOURCE_SHA: d77126fa6c5ae8fc170490d181b62f37af7fe4528bc2f2843fbfd5756e6783f3
TESTS_SHA: b2b045635b8b7d7ae99bb3356f196101a8f8e732f4e2d04d2cb668565f865870

- [x] test lock
- [x] forbidden patterns
- [x] api: uv sync
- [x] api: ruff
- [x] api: mypy --strict
- [x] api: pytest - 144 passed, 1 warning in 23.13s
- [x] web: npm install
- [x] web: typecheck
- [x] web: test
- [x] web: build
- [x] api: smoke boot

## Slowest tests
```
9.36s call     tests/test_api.py::test_perf_10k_links
1.90s call     tests/test_recent_links.py::test_perf_list_10k_rows
1.00s call     tests/test_api.py::test_risk_fm10_restart_idempotent
0.53s call     tests/test_api.py::test_perf_concurrent_creates_under_5s
0.45s call     tests/test_api.py::test_api_codes_random_not_sequential
```

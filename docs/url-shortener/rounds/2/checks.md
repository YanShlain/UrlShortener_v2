GATE: PASS
ROUND: 2
SOURCE_SHA: d3212dc56b06889abe6267a29d6d1c362650bf49b5f26ac9254405ac1ff27627
TESTS_SHA: 178a4540fbe9bd84a6f4592a94007b41633ae4f2594939cab9d63afa8185ebf7

- [x] test lock
- [x] forbidden patterns
- [x] api: uv sync
- [x] api: ruff
- [x] api: mypy --strict
- [x] api: pytest - 122 passed, 1 warning in 21.14s
- [x] web: npm install
- [x] web: typecheck
- [x] web: test
- [x] web: build
- [x] api: smoke boot

## Slowest tests
```
11.84s call     tests/test_api.py::test_perf_10k_links
1.00s call     tests/test_api.py::test_risk_fm1_concurrent_same_url
0.81s call     tests/test_api.py::test_risk_fm10_restart_idempotent
0.38s call     tests/test_api.py::test_api_codes_random_not_sequential
0.32s call     tests/test_api.py::test_perf_concurrent_creates_under_5s
```

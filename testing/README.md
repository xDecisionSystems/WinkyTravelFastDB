# Testing

Automated test scripts live in this folder.

## Scripts

- `./testing/run_unit_tests.sh`
  - Runs unit tests with `unittest`.
  - Current coverage:
    - rate-limit service behavior (allow/block and anonymous endpoints)
    - dev log reader safety (path traversal blocking and tail limits)
    - `llms.txt` manifest presence and required section checks

- `./testing/smoke_api.sh`
  - Runs smoke checks against a running API instance.
  - Default base URL: `http://127.0.0.1:8000`
  - Override with: `API_BASE_URL=http://host:port ./testing/smoke_api.sh`

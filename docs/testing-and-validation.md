# Testing and acceptance

Automated tests are necessary but not sufficient. For real use, validate the integration using actual Home Assistant entity timestamps, utility meter behavior and backed-up history.

## CI in this repository

The existing `.github/workflows/validate.yml` exercises Python tests, Ruff, Python compileall, JavaScript syntax, frontend unit tests, Playwright browser layout, hassfest and HACS validation.

Example commands (use a virtual environment and the appropriate local Python binary):

~~~bash
python -m pip install -r requirements-test.txt
python -m pytest
python -m ruff check .
python -m compileall -q custom_components
node --check custom_components/si_grid_monitor/frontend/dashboard.js
node --test frontend_tests/*.test.mjs
npm install --ignore-scripts
npm run test:layout
~~~

Rendered Playwright layout needs compatible Chromium installation (GitHub Actions installs its browser dependencies). The **Pages preview** workflow builds an artifact from `docs/` but does not deploy a public site.

## Real Home Assistant acceptance

- Create a full backup before an update; confirm an existing Mode A database and entry can be recovered.
- Test signed-power import/export polarity with known loads.
- Test Mode B independent import/export source timestamps.
- Test Mode C single import with export unknown; verify initial incomplete quarter and later recovery of sustained advice after a fully observed quarter.
- Test Mode D import-only, bidirectional net and separate counters, including zero delta, reset, counter resolution, interval boundaries and unexpected derivatives.
- Verify actual 2026/2027 dated block limits and next transitions.
- Check completion, missing/pre-monitoring counts, simulated vs confirmed exceedances and provenance across History.
- Try two independently configured meters, selector persistence, restart and sensor unavailability.
- Check both supported languages and Android/desktop layout.
- Test safe archive retention; only test deletion on disposable backed-up data.

## Documentation-only PR acceptance

A documentation PR should change only `README.md`, `docs/**`, or documentation-only validation/preview configuration. It must not change runtime code, constants, database schema, forecasts, entity values or version number.

Verify Markdown links resolve relative to their file locations. Verify there is no claim of a public GitHub Pages website unless Pages has actually been deployed. Do not include fabricated or uncited hardware screenshots.

Existing detailed scenarios: [../MANUAL_TEST_PLAN.md](../MANUAL_TEST_PLAN.md).
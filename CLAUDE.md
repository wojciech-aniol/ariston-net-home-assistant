# Ariston NET

Home Assistant custom integration, domain `ariston_net`. Fork of
fustom/ariston-remotethermo-home-assistant-v3. Code in `custom_components/ariston_net/`, tests in
`tests/`. It reaches the Ariston cloud only through the `ariston` library (PyPI, version pinned in
`manifest.json` and `requirements_test.txt`). Never patch, fork or vendor the library.

## Commands

- Set up once: `uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt`
- Tests: `.venv/bin/python -m pytest -q`
- Coverage: `.venv/bin/python -m pytest -q --cov` (settings and the floor are in `pyproject.toml`)
- Lint and format: `.venv/bin/ruff check --fix . && .venv/bin/ruff format .`
- Accept snapshot changes: add `--snapshot-update`, only when the change is the goal.

Tests and lint pass before every commit.

## Map

- `__init__.py`: entry setup, the `set_item_by_id` service. `binary_sensor.py` registers the
  `create_vacation` service.
- `coordinator.py`: polling, HTTP 429 backoff. Up to three coordinators per entry: state, bus errors
  and energy (the last two are optional).
- `entity.py`: base entity, `is_entity_supported`. `const.py`: constants and every entity
  description. Entity behaviour sits in description lambdas (`get_native_value`, `set_value`, ...).
- Library source: `.venv/lib/python3.14/site-packages/ariston/`. Devices: `galevo_device.py`,
  `bsb_device.py`, `velis_*`, `evo_*`, `lux*`, `lydos*`, `nuos_split_device.py`; HTTP and
  `ConnectionException` in `ariston_api.py`.

Save context: `const.py` has 1000+ lines, so grep it. In `README.md` only the part above "About the
upstream integration" matters. Of `translations/` read only `en.json`.

## Hard rules

- Never change the unique_id, entity_id or name of an existing entity. Most unique_ids are built
  from the entity name (`entity.py`), so a new name means a new unique_id. Climate uses
  `{gateway}_{zone}` and the water heater `{gateway}-water_heater`. `tests/test_snapshots.py`
  guards this: an unplanned snapshot change means the code change is wrong.
- Never shorten the default polling intervals or add cloud requests per poll. The cloud throttles
  accounts (HTTP 429 and 500).
- Keep config entry data and option keys. A change needs a config entry migration and a test.
- Keep the keys of `strings.json` and `translations/en.json` the same. `strings.json` may use
  `[%key:...%]` references, `en.json` holds the final English text.
- Ask the user before a tag or release, a refactor bigger than the plan says, or a new `ariston`
  version.
- Code, comments, commits and README are in English.

## Git

- `ariston-net` is the work branch, `main` holds released code. `origin` is the fork, `upstream` is
  fustom: never push there.
- Commit subject: imperative, no prefix, under 60 characters. The body says why.

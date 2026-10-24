# Ariston NET

Home Assistant custom integration, domain `ariston_net`. Fork of
fustom/ariston-remotethermo-home-assistant-v3. Code in `custom_components/ariston_net/`, tests in
`tests/`. It reaches the Ariston cloud only through the `ariston` library (PyPI, version pinned in
`manifest.json` and `requirements_test.txt`). Never patch, fork or vendor the library.
One approved exception: `menu_items.py` replaces `async_get_menu_items` on the API object, to
add menu item IDs to the library's own request, and asks the blocked IDs 342-347 once at setup
(see its docstrings).

## Commands

- Set up once: `uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt`
- Tests: `.venv/bin/python -m pytest -q`
- Coverage: `.venv/bin/python -m pytest -q --cov` (settings and the floor are in `pyproject.toml`)
- Lint and format: `.venv/bin/ruff check --fix . && .venv/bin/ruff format .`
- Accept snapshot changes: add `--snapshot-update`, only when the change is the goal.

Tests and lint pass before every commit.

## Map

- `__init__.py`: entry setup. Coordinators live in `entry.runtime_data` (`AristonData` in
  `coordinator.py`, typed as `AristonConfigEntry`); a disabled one is None.
- `coordinator.py`: polling, HTTP 429 backoff. Up to three coordinators per entry: state, bus errors
  and energy (the last two are optional).
- `services.py`: `create_vacation` and `set_item_by_id`, registered once in `async_setup`.
- `entity.py`: base entity, base description, `is_entity_supported`. `const.py`: constants only.
- Each platform file holds its description class and list. Entity behaviour sits in description
  lambdas (`get_native_value`, `set_value`, ...). List order is entity order in snapshots.
- Library source: `.venv/lib/python3.14/site-packages/ariston/`. Devices: `galevo_device.py`,
  `bsb_device.py`, `velis_*`, `evo_*`, `lux*`, `lydos*`, `nuos_split_device.py`; HTTP and
  `ConnectionException` in `ariston_api.py`.

Save context: `sensor.py` has 600+ lines of descriptions, so grep it. In `README.md` only the part
above "About the upstream integration" matters. Of `translations/` read only `en.json`.

## Hard rules

- Never change the unique_id, entity_id or name of an existing entity. Most unique_ids are built
  from the entity name (`entity.py`), so a new name means a new unique_id. Climate uses
  `{gateway}_{zone}` and the water heater `{gateway}-water_heater`. `tests/test_snapshots.py`
  guards this for a one-zone GALEVO device so far: an unplanned snapshot change means the code
  change is wrong.
- Never shorten the default polling intervals or add cloud requests per poll. The cloud throttles
  accounts (HTTP 429 and 500).
- Keep config entry data and option keys. A change needs a config entry migration and a test.
- Keep the keys of `strings.json` and `translations/en.json` the same. `strings.json` may use
  `[%key:...%]` references, `en.json` holds the final English text.
- Ask the user before a refactor bigger than the plan says or a new `ariston` version.
- Code, comments, commits and README are in English.

## Git

- `ariston-net` is the work branch, `main` holds released code. `origin` is the fork, `upstream` is
  fustom: never push there.
- Commit subject: imperative, no prefix, under 60 characters. The body says why.
- Releases are automatic (`.github/workflows/auto-release.yml`). Each PR merged into
  `ariston-net` that changes `custom_components/` bumps the `manifest.json` version, moves `main`
  and publishes a GitHub release, which HACS picks up. The bump is a patch; the PR label `minor`,
  `major` or `no-release` changes that. Never bump the version, tag or release by hand.
- PR titles become the release notes, so write them for users. To ship several PRs as one
  release, label all but the last `no-release`.

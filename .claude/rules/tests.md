---
paths:
  - "tests/**"
---

# Test rules

- Test through Home Assistant: set the entry up with the `init_integration` fixture, read
  `hass.states`, call services with `hass.services.async_call(..., blocking=True)`. Build entities by
  hand only when no service or state can reach the code.
- Fake only the cloud API (`api` fixture). Keep the real library device, so library logic runs too.
  Change what the cloud sends with the `features` and `properties` fixtures before setup.
- Check what goes to the cloud on `api` (for example `api.async_set_property`). To check only the
  mapping from a service to a library call, replace that device method with `AsyncMock` (see
  `tests/test_select.py`).
- Entity lists and states: `snapshot_platform(hass, entity_registry, snapshot, entry.entry_id)` from
  `pytest_homeassistant_custom_component.common`. Snapshots go to `tests/snapshots/`.
- Time: the `freezer` fixture with `async_fire_time_changed`. No sleeps, no real network.
- One behaviour per test, named `test_<subject>_<expected result>`, with a one-line docstring. Use
  `pytest.mark.parametrize` for tables of cases.
- Put shared device data in `tests/conftest.py` or `tests/fixtures/`, not copied between files.

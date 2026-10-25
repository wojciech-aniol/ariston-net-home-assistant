[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

# Ariston NET for Home Assistant

This is a fork of [fustom/ariston-remotethermo-home-assistant-v3](https://github.com/fustom/ariston-remotethermo-home-assistant-v3),
based on upstream v0.19.9. The integration and the [`ariston`](https://pypi.org/project/ariston/)
library ([fustom/python-ariston-api](https://github.com/fustom/python-ariston-api)) are the work of
[@fustom](https://github.com/fustom). This fork uses
[`ariston-net-api`](https://pypi.org/project/ariston-net-api/)
([wojciech-aniol/python-ariston-net-api](https://github.com/wojciech-aniol/python-ariston-net-api)),
a fork of `ariston` 0.19.9 that fixes turning on a BSB zone that is off and the Lux BOOST mode.

> [!WARNING]
> **This fork is completely vibe-coded.** An AI coding assistant
> ([Claude Code](https://claude.com/claude-code)) wrote all the changes, the tests, the commit
> messages and this README. A human chose what to change and tests it on one real device.
> Read the code before you rely on it.

The fork uses its own domain `ariston_net`, so it can be installed:

- next to another custom integration that uses the `ariston` domain, for example
  [chomupashchuk's v2](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2);
- on Home Assistant 2026.8 and newer, where the `ariston` domain is also used by a built-in
  virtual integration (Ariston air conditioners through Midea).

It is tested on an Ariston Nimbus 120 S-T NET R32 heat pump (GALEVO). Other devices keep the
upstream support, but they are not tested here.

## What is different from the original

### Breaking changes

- Domain `ariston_net` instead of `ariston`. Config entries of the `ariston` domain are not
  migrated: set up the integration again.
- Entity names are shorter and translated (English and Polish), so names and entity IDs differ
  from upstream. Entities made by an older version of this fork keep their entity IDs; new
  installs get shorter ones (see [Good to know](#good-to-know)).
- Services are `ariston_net.create_vacation` and `ariston_net.set_item_by_id`.
- Entities the device never reports are not created: the flame sensor needs a flame value, the
  CH return temperature needs its menu value.

### From upstream pull requests

Merged upstream after the v0.19.9 release:

- [#442](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/442) by @dvapelnik:
  `hvac_action` is `heating` also when only the heat pump runs (no flame).
- [#443](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/443) by @dvapelnik:
  presets map to the real plant mode value, so preset `OFF` no longer selects "Cooling only".

Ported from open or closed upstream pull requests:

- [#489](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/489) by @gatisvil (part):
  the "is heating pump on" binary sensor now appears on pure heat pump systems (`hpSys`), not only
  on hybrid systems.
- [#476](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/476) by @alxrxs:
  an error from the energy report endpoint no longer stops the setup.
- [#452](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/452) by @vinivinilos
  (rewritten): on HTTP 429 the update interval doubles, up to 8 times, and goes back after the next
  successful update.
- [#477](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/477) by @dvapelnik:
  DHW current and target temperature sensors for GALEVO and BSB.
- [#445](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/445) by @thor2002ro (part):
  HVAC mode `off` is offered when the device supports plant modes (older Nimbus zones have no
  `off` option).

The commit messages list what was skipped from each pull request and why.

### New in this fork

- Sensors "Heat pump flow temperature" and "CH flow measured temperature" (GALEVO): the
  measured flow temperatures from the cloud menu items 348 and 349, in whole degrees. The library
  does not ask for them, so the integration adds them to its menu items request (still one request
  per update). A device that never sends them gets no such sensors, and "CH flow measured
  temperature" is skipped when "CH flow temperature" has a value. The cloud gives an owner
  account no return temperature for Nimbus 120 S-T NET (menu items 1-500, all data items and the
  web user menu were checked).
- Sensors "Heat pump return temperature" and "Evaporator temperature" (GALEVO): the
  heat pump nodes T_13.8.2 and T_13.8.7. The cloud refuses them for an owner account so far, and a
  refused ID breaks the whole menu items request. So the integration asks for them once, when it
  starts (one extra request per start, none per update). If the cloud serves them one day, they
  join the polled request and the sensors appear; until then nothing changes.
- Heat produced and COP sensors (GALEVO with metering): energy produced today and this month for
  heating, hot water and cooling (cooling only when a plant mode can cool), and the COP of
  heating and hot water yesterday and this month. Ariston has these estimates only in its web
  app, so each update logs in to the web app (2 requests), as often as the energy data. Energy
  of the last hours of a day can reach the cloud after midnight, so "today" may miss it; "this
  month" still counts it, apart from the last day of a month.
- Select entity "Plant mode" (GALEVO): Summer, Winter, Heating only and so on, as listed by the
  cloud. It does the same as the climate preset, for the whole plant.
- An error from the bus errors endpoint no longer stops the setup.
- Energy and heat produced sensors are added when their data first loads after a failed start.
- Options **Poll energy data** and **Poll bus errors** turn off these cloud requests and their
  entities. **Poll energy data** also turns off heat produced and COP.
- Total energy sensors stay `unknown` until the cloud energy data changes once. Before that the
  library has no reset time, so statistics would count the same value again after each restart.
- Clear errors: a refused password starts re-authentication (password only), and cloud errors
  of an action show a message instead of a traceback. The interval options have minimums.
- Fewer cloud requests: an action that sets the value the device already has sends nothing, a
  preset change no longer reads the whole state again, and actions reach the cloud one at a time.
- Diagnostics (**Download diagnostics** on the integration page) with the raw cloud data. Login,
  gateway, serial numbers and names are removed.
- Its own icon (`custom_components/ariston_net/brand`).
- Unit tests with a fake Ariston cloud, run in GitHub Actions.

### Offered back to upstream

Draft pull requests to fustom:
[#494](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/494) (rate limit backoff),
[#495](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/495) (bus errors no
longer stop the setup) and
[#496](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/496) (plant mode select).

## Installation

Requires Home Assistant 2025.10.0 or newer.

### HACS (custom repository)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=wojciech-aniol&repository=ariston-remotethermo-home-assistant-v3&category=integration)

1. In HACS open the menu (⋮) → **Custom repositories**.
2. Repository: `https://github.com/wojciech-aniol/ariston-remotethermo-home-assistant-v3`,
   type: **Integration**. Select **Add**.
3. Open **Ariston NET** in HACS and select **Download**.
4. Restart Home Assistant.
5. **Settings → Devices & services → Add integration → Ariston NET**. Log in with your Ariston NET
   account.

### Manual

Copy `custom_components/ariston_net` to `<config>/custom_components/ariston_net` and restart
Home Assistant.

## Good to know

- Entity names come from translations (English and Polish so far; other languages show
  English), and Home Assistant puts the device name in front: "Dom Heat pump" for a device named
  "Dom". Climate and water heater entities use only the device name (`climate.dom`,
  `water_heater.dom`).
- Entity IDs never change once made, so existing entities keep theirs. New installs get shorter
  ones made from the new names, like `binary_sensor.dom_heat_pump` (on Home Assistant 2026.10 in
  its language, like `binary_sensor.dom_pompa_ciepla`).
- Energy sensors are main sensors, not diagnostic ones. New installs create the signal strength
  sensor disabled; enable it in the entity settings if you need it.
- Default polling: state every 180 s, energy and heat produced every 60 min, bus errors every 600 s
  (**Configure** in the integration options, where you can also turn off energy and bus errors
  polling). The Ariston cloud throttles accounts (HTTP 429 and 500), so do not poll more often.
  The options do not take less than 60 s for state and bus errors and 15 min for energy.
  Every other integration that uses the same account adds to the load.
- Cloud errors: when the cloud refuses the saved password, Home Assistant asks for the new one
  (under **Settings → Devices & services**; it asks only for the password). Other
  cloud errors make the entities unavailable until the next good update, and a failed start is
  tried again later. A change that the cloud does not accept shows an error message with the
  HTTP status, not a traceback in the log.
- API settings: to change the API URL or user agent, select **Reconfigure** in the entry menu
  (⋮). It logs in with the saved account to check them. Each device has its own entry, so change
  every entry of the account.
- The climate HVAC mode `off` uses the plant mode `OFF` when the device has it, which also turns
  off domestic hot water. To keep hot water and stop heating, select the plant mode `Summer`
  (select entity or climate preset).

## Credits

- [@fustom](https://github.com/fustom): the original integration and the `ariston` library.
- [@chomupashchuk](https://github.com/chomupashchuk): the v2 integration that inspired it.
- The authors of the ported pull requests listed above.
- [@mauropriori](https://github.com/mauropriori): [ariston_net](https://github.com/mauropriori/ariston_net),
  another fork with the same domain. Some changes here follow its approach.

MIT License, see [LICENSE](LICENSE).

## About the upstream integration

The rest of this page is from the upstream README.

This integration inspired by chomupashchuk fantastic work https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2
But it does not use Ariston website. It uses Ariston API what I reversed engineered.


| [This integration](https://github.com/fustom/ariston-remotethermo-home-assistant-v3)  | [Chomupashchuk's v2 integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2) |
| ------------- | ------------- |
| Uses real API  | Uses Ariston website  |
| Faster set/get data  | Sometimes needs minutes to set/get data |
| Easy to setup with UI | Not so easy to setup (only with configuration.yaml) |
| Integration & devices & entites | Only entites |
| Proper asynchronous integration, clean code | Hard to understand and maintain (ariston.py has more than 4000 lines) |
| Less sensors, switches, etc |  More sensors, switches, etc |
| New code, may contains lot of bugs | Old, tested code |

### Integration was tested on and works with:
- Ariston Alteas One 24
- Ariston Velis Evo
- Ariston Velis Lux
- Ariston Lydos Hybrid

| ![Kazam_screenshot_00003](https://user-images.githubusercontent.com/6751243/146653448-ff7b6f9d-cbf1-4555-9a75-61bf68bc9d3e.png) | ![Kazam_screenshot_00004](https://user-images.githubusercontent.com/6751243/146653484-52e39d78-7c6f-44ae-888d-acf246147290.png) | ![Kazam_screenshot_00010](https://user-images.githubusercontent.com/6751243/147890590-6c4ebf38-16d9-421f-9b81-8f43298ec62f.png) |
:-------------------------:|:-------------------------:|:-------------------------:

![Kazam_screenshot_00011](https://user-images.githubusercontent.com/6751243/147890611-54ae2d28-bf5a-45f8-ba92-e7a00a22615c.png)

![Kazam_screenshot_00012](https://user-images.githubusercontent.com/6751243/147989103-cdac510f-e6f6-461f-a88e-b8ff0204c34f.png)

| ![Kazam_screenshot_00013](https://user-images.githubusercontent.com/6751243/148247717-5211c01c-561f-4a4e-b4b5-47a680e04a68.png) | ![Kazam_screenshot_00009](https://user-images.githubusercontent.com/6751243/146657797-ed14b741-595a-48a6-9126-1acca3beb69f.png) |
:-------------------------:|:-------------------------:

<h1 align="center">Peace Love Freedom</h1>

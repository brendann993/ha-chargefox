# Chargefox for Home Assistant

Chargefox is a custom Home Assistant integration that lets you locate and monitor
Chargefox charging stations within a configurable geographic area in Australia.

Choose a centre point and radius during setup, and the integration will create
devices for the Chargefox stations found inside that boundary. You can optionally
limit the results to stations that support selected plug types.

> [!NOTE]
> This is an unofficial community integration and is not affiliated with or
> supported by Chargefox.

## Features

- Configure a station search area using a map and radius.
- Optionally filter stations by one or more plug types.
- Automatically discover stations and connectors within the configured area.
- Monitor station availability, status, maximum power, pricing and other details.
- Monitor connector status and active charging-session information when available.
- Change the search area and plug filters from the integration options.

## Requirements

- Home Assistant 2026.3.0 or newer.
- A working internet connection from Home Assistant to the Chargefox service.
- A Home Assistant location configured near the area you want to monitor is
  recommended, as it is used as the initial map position.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Select **Integrations**.
3. Open the menu in the top-right corner and select **Custom repositories**.
4. Add `https://github.com/brendann993/ha-chargefox` as an **Integration**.
5. Search for **Chargefox** and install it.
6. Restart Home Assistant when prompted.

### Manual installation

1. Download the latest release from GitHub.
2. Copy `custom_components/chargefox` into the `custom_components` directory in
   your Home Assistant configuration directory.
3. Restart Home Assistant.

The resulting path should be:

```text
<config>/custom_components/chargefox/
```

## Configuration

1. In Home Assistant, go to **Settings > Devices & services**.
2. Select **Add integration**.
3. Search for **Chargefox**.
4. Enter a friendly name for the monitored area.
5. Choose the centre point and radius on the map.
6. Optionally select the plug types to include, or leave the selection empty to
   include all plug types.

At least one matching Chargefox station must be present inside the selected area
to complete setup.

To change the area name, boundary or plug filters later, open the Chargefox
integration and select **Configure**.

## Devices and entities

Each discovered charging station is represented as a Home Assistant device. The
available entities depend on the information returned by Chargefox and include:

- **Online** - whether the station is online.
- **Status** - the station's current status.
- **Maximum power** - the station's reported maximum charging power in kW.
- **Pricing** - the applicable pricing plan, tariffs and idle-fee details.
- **Directions** - access directions for the station.
- **Firmware** - the station's reported firmware version.
- **Connector status** - the state and plug type of each connector, with active
  charging-session details when available.

Station data is refreshed every two minutes. New stations and connectors found
inside the configured area are added automatically.

## Known limitations

- The integration currently targets Chargefox stations in Australia.
- Data availability and accuracy depend on the information provided by Chargefox.
- The integration monitors station information; it does not start, stop or pay
  for charging sessions.
- Stations that leave the configured area or no longer match the selected plug
  filters may remain in Home Assistant but will be marked unavailable.

## Troubleshooting

### No stations were found

Increase the selected radius, move the centre point, or remove plug-type filters.
Setup cannot be completed unless at least one matching station is found.

### The integration cannot connect

Confirm that Home Assistant has internet access and that the Chargefox service is
available. Check **Settings > System > Logs** for messages mentioning `chargefox`.

If the problem continues, open an issue in the
[GitHub issue tracker](https://github.com/brendann993/ha-chargefox/issues) and
include the Home Assistant version, integration version and relevant log output.

Please remove access tokens, location details and other personal information from
logs before sharing them.

## Support

Bug reports and feature requests are welcome through the
[GitHub issue tracker](https://github.com/brendann993/ha-chargefox/issues).

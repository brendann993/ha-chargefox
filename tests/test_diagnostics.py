"""Tests for Chargefox diagnostics."""

from datetime import UTC, datetime
from types import SimpleNamespace

from chargefox import ChargeStation, Connector
from homeassistant.const import CONF_ACCESS_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargefox.const import CONF_LOCATION, DOMAIN
from custom_components.chargefox.diagnostics import async_get_config_entry_diagnostics


async def test_config_entry_diagnostics_redact_private_data(hass) -> None:
    """Diagnostics redact credentials and configured coordinates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "secret-token",
            CONF_LOCATION: {"latitude": -31.9, "longitude": 115.8, "radius": 5000},
        },
        options={
            CONF_LOCATION: {"latitude": -32.0, "longitude": 115.9, "radius": 10000}
        },
    )
    station = ChargeStation(
        id="station-1",
        status="AVAILABLE",
        online=True,
        enabled=True,
        connectors=[Connector(id="connector-1", status="available")],
    )
    entry.runtime_data = SimpleNamespace(
        data={station.id: station},
        last_discovery=datetime(2026, 8, 12, 6, tzinfo=UTC),
        last_update_success=True,
        station_ids={station.id},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry"]["data"][CONF_ACCESS_TOKEN] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_LOCATION] == "**REDACTED**"
    assert diagnostics["config_entry"]["options"][CONF_LOCATION] == "**REDACTED**"
    assert diagnostics["coordinator"]["stations_discovered"] == 1
    assert diagnostics["stations"] == [
        {
            "id": "station-1",
            "status": "AVAILABLE",
            "online": True,
            "enabled": True,
            "connector_count": 1,
            "connector_statuses": ["available"],
        }
    ]

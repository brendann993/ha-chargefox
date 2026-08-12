"""Tests for the Chargefox data update coordinator."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from chargefox import ChargeStation, Location, LocationSummary, StationSummary
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryDisabler
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargefox.const import (
    CONF_LOCATION,
    DOMAIN,
    REDISCOVERY_INTERVAL,
)
from custom_components.chargefox.coordinator import ChargefoxDataUpdateCoordinator

NOW = datetime(2026, 8, 12, 6, tzinfo=UTC)
LOCATION = {"latitude": -31.9, "longitude": 115.8, "radius": 5000}


def _summary(station_id: str, *, latitude: float = -31.9) -> LocationSummary:
    return LocationSummary(
        id=f"location-{station_id}",
        latitude=latitude,
        longitude=115.8,
        charge_stations=[StationSummary(station_id, "AVAILABLE", 50)],
    )


def _station(station_id: str) -> ChargeStation:
    return ChargeStation(
        id=station_id,
        status="AVAILABLE",
        online=True,
        enabled=True,
        location=Location(
            id=f"location-{station_id}",
            latitude=-31.9,
            longitude=115.8,
        ),
    )


def _coordinator(hass, client: AsyncMock) -> ChargefoxDataUpdateCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_LOCATION: LOCATION})
    entry.add_to_hass(hass)
    return ChargefoxDataUpdateCoordinator(hass, entry, client)


async def test_initial_discovery_then_targeted_refresh(hass) -> None:
    """Discover once, then refresh the cached station IDs."""
    client = AsyncMock()
    client.get_locations_by_bounds.return_value = [_summary("station-1")]
    client.get_charge_stations.return_value = [_station("station-1")]
    coordinator = _coordinator(hass, client)

    with patch(
        "custom_components.chargefox.coordinator.dt_util.utcnow", return_value=NOW
    ):
        first = await coordinator._async_update_data()
        second = await coordinator._async_update_data()

    assert list(first) == ["station-1"]
    assert list(second) == ["station-1"]
    assert coordinator.station_ids == {"station-1"}
    assert coordinator.last_discovery == NOW
    assert client.get_locations_by_bounds.await_count == 1
    assert client.get_charge_stations.await_args_list[0].args[0] == ["station-1"]
    assert client.get_charge_stations.await_args_list[1].args[0] == ["station-1"]


async def test_periodic_rediscovery_adds_new_station(hass) -> None:
    """Discover new stations once the rediscovery interval elapses."""
    client = AsyncMock()
    client.get_locations_by_bounds.side_effect = [
        [_summary("station-1")],
        [_summary("station-1"), _summary("station-2")],
    ]
    client.get_charge_stations.side_effect = [
        [_station("station-1")],
        [_station("station-1"), _station("station-2")],
    ]
    coordinator = _coordinator(hass, client)

    with patch(
        "custom_components.chargefox.coordinator.dt_util.utcnow",
        side_effect=[NOW, NOW + REDISCOVERY_INTERVAL],
    ):
        await coordinator._async_update_data()
        data = await coordinator._async_update_data()

    assert set(data) == {"station-1", "station-2"}
    assert coordinator.station_ids == {"station-1", "station-2"}
    assert client.get_locations_by_bounds.await_count == 2
    assert client.get_charge_stations.await_args_list[1].args[0] == [
        "station-1",
        "station-2",
    ]


async def test_discovery_excludes_locations_outside_circle(hass) -> None:
    """Exclude a station in the corners of the rectangular API bounds."""
    client = AsyncMock()
    client.get_locations_by_bounds.return_value = [
        _summary("inside"),
        _summary("outside", latitude=-31.8),
    ]
    client.get_charge_stations.return_value = [_station("inside")]
    coordinator = _coordinator(hass, client)

    with patch(
        "custom_components.chargefox.coordinator.dt_util.utcnow", return_value=NOW
    ):
        data = await coordinator._async_update_data()

    assert list(data) == ["inside"]
    assert coordinator.station_ids == {"inside"}
    assert client.get_charge_stations.await_args.args[0] == ["inside"]


async def test_disabled_station_is_not_refreshed(hass) -> None:
    """Do not query a station whose Home Assistant device is disabled."""
    client = AsyncMock()
    client.get_locations_by_bounds.return_value = [_summary("station-1")]
    client.get_charge_stations.side_effect = [[_station("station-1")], []]
    coordinator = _coordinator(hass, client)

    with patch(
        "custom_components.chargefox.coordinator.dt_util.utcnow", return_value=NOW
    ):
        await coordinator._async_update_data()

        registry = dr.async_get(hass)
        device = registry.async_get_or_create(
            config_entry_id=coordinator.config_entry.entry_id,
            identifiers={(DOMAIN, "station-1")},
        )
        registry.async_update_device(device.id, disabled_by=DeviceEntryDisabler.USER)
        data = await coordinator._async_update_data()

    assert data == {}
    assert coordinator.station_ids == {"station-1"}
    assert client.get_charge_stations.await_args_list[1].args[0] == []

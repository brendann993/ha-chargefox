"""Tests for Chargefox area and map entities."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from chargefox import ChargeStation, Connector, Location
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargefox.const import CONF_LOCATION, DOMAIN
from custom_components.chargefox.coordinator import ChargefoxDataUpdateCoordinator
from custom_components.chargefox.geo_location import ChargefoxStationLocation
from custom_components.chargefox.sensor import (
    ChargefoxAreaAvailableConnectorsSensor,
    ChargefoxAreaFaultedConnectorsSensor,
    ChargefoxAreaLastDiscoverySensor,
    ChargefoxAreaOnlineStationsSensor,
)

LOCATION = {"latitude": -31.9, "longitude": 115.8, "radius": 5000}
DISCOVERY_TIME = datetime(2026, 8, 12, 6, tzinfo=UTC)


def _coordinator(hass) -> ChargefoxDataUpdateCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Northern Suburbs", data={CONF_LOCATION: LOCATION}
    )
    entry.add_to_hass(hass)
    coordinator = ChargefoxDataUpdateCoordinator(hass, entry, AsyncMock())
    coordinator.data = {
        "online": ChargeStation(
            id="online",
            name="Online station",
            online=True,
            location=Location(id="online-location", latitude=-31.9, longitude=115.8),
            connectors=[
                Connector(id="available", available=True, status="AVAILABLE"),
                Connector(id="faulted", available=False, status="FAULTED"),
            ],
        ),
        "offline": ChargeStation(
            id="offline",
            online=False,
            location=Location(id="offline-location", latitude=-31.91, longitude=115.8),
        ),
    }
    coordinator._last_discovery = DISCOVERY_TIME
    return coordinator


def test_area_summary_values(hass) -> None:
    """Area sensors summarise the coordinator data."""
    coordinator = _coordinator(hass)

    online = ChargefoxAreaOnlineStationsSensor(coordinator)
    available = ChargefoxAreaAvailableConnectorsSensor(coordinator)

    assert online.native_value == 1
    assert online.name == "Online stations"
    assert online.extra_state_attributes == {
        "total_stations": 2,
        "offline_stations": 1,
    }
    assert available.native_value == 1
    assert available.name == "Available connectors"
    assert available.extra_state_attributes == {"total_connectors": 2}
    assert ChargefoxAreaFaultedConnectorsSensor(coordinator).native_value == 1
    assert ChargefoxAreaLastDiscoverySensor(coordinator).native_value == DISCOVERY_TIME


def test_station_geolocation(hass) -> None:
    """A station map marker exposes its coordinates and Chargefox source."""
    coordinator = _coordinator(hass)
    entity = ChargefoxStationLocation(coordinator, "online")

    assert entity.latitude == -31.9
    assert entity.longitude == 115.8
    assert entity.distance == 0
    assert entity.source == DOMAIN
    assert entity.device_info["identifiers"] == {(DOMAIN, "online")}

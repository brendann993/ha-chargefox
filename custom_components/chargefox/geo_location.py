"""Geolocation entities for Chargefox stations."""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.location import distance

from . import ChargefoxConfigEntry
from .const import CONF_LOCATION, DOMAIN
from .coordinator import ChargefoxDataUpdateCoordinator
from .entity import _station_device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargefoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Chargefox station map markers."""
    coordinator = entry.runtime_data
    known_stations: set[str] = set()

    @callback
    def async_discover_entities() -> None:
        entities = [
            ChargefoxStationLocation(coordinator, station_id)
            for station_id in coordinator.data
            if station_id not in known_stations
        ]
        known_stations.update(entity.station_id for entity in entities)
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(async_discover_entities))
    async_discover_entities()


class ChargefoxStationLocation(
    CoordinatorEntity[ChargefoxDataUpdateCoordinator], GeolocationEvent
):
    """Map marker for a Chargefox station."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:ev-station"
    _attr_name = None
    _attr_source = DOMAIN

    def __init__(
        self, coordinator: ChargefoxDataUpdateCoordinator, station_id: str
    ) -> None:
        """Initialize a station map marker."""
        super().__init__(coordinator)
        self.station_id = station_id
        self._attr_unique_id = f"{station_id}_location"

    @property
    def available(self) -> bool:
        """Return whether the station remains available from the API."""
        return super().available and self.station_id in self.coordinator.data

    @property
    def latitude(self) -> float | None:
        """Return station latitude."""
        station = self.coordinator.data.get(self.station_id)
        return station.location.latitude if station and station.location else None

    @property
    def longitude(self) -> float | None:
        """Return station longitude."""
        station = self.coordinator.data.get(self.station_id)
        return station.location.longitude if station and station.location else None

    @property
    def distance(self) -> float | None:
        """Return distance from the configured area centre in kilometres."""
        if self.latitude is None or self.longitude is None:
            return None
        location = self.coordinator.config_entry.options.get(
            CONF_LOCATION, self.coordinator.config_entry.data[CONF_LOCATION]
        )
        distance_m = distance(
            location[CONF_LATITUDE],
            location[CONF_LONGITUDE],
            self.latitude,
            self.longitude,
        )
        return distance_m / 1000 if distance_m is not None else None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the parent station device information."""
        return _station_device_info(
            self.station_id, self.coordinator.data.get(self.station_id)
        )

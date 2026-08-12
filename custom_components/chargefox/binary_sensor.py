"""Binary sensors for the Chargefox integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ChargefoxConfigEntry
from .entity import ChargefoxStationEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargefoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Chargefox binary sensors."""
    coordinator = entry.runtime_data
    known_stations: set[str] = set()

    @callback
    def async_discover_entities() -> None:
        entities: list[BinarySensorEntity] = []
        for station_id in coordinator.data:
            if station_id not in known_stations:
                known_stations.add(station_id)
                entities.append(ChargefoxStationOnlineSensor(coordinator, station_id))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(async_discover_entities))
    async_discover_entities()


class ChargefoxStationOnlineSensor(ChargefoxStationEntity, BinarySensorEntity):
    """Whether a Chargefox station is online."""

    _attr_translation_key = "station_online"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_online"

    @property
    def is_on(self) -> bool | None:
        """Return whether the station is online."""
        return self.station.online if self.station else None

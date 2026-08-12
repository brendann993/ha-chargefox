"""Sensors for the Chargefox integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChargefoxConfigEntry
from .const import DOMAIN
from .coordinator import ChargefoxDataUpdateCoordinator
from .entity import ChargefoxConnectorEntity, ChargefoxStationEntity

PARALLEL_UPDATES = 0

_PLUG_ICONS = {
    "ccs 1": "mdi:ev-plug-ccs1",
    "ccs 2": "mdi:ev-plug-ccs2",
    "chademo": "mdi:ev-plug-chademo",
    "type 1": "mdi:ev-plug-type1",
    "type 1 (sae j1772)": "mdi:ev-plug-type1",
    "type 2": "mdi:ev-plug-type2",
    "type 2 (mennekes)": "mdi:ev-plug-type2",
}
_DEFAULT_PLUG_ICON = "mdi:ev-station"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargefoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Chargefox sensors."""
    coordinator = entry.runtime_data
    known_stations: set[str] = set()
    known_connectors: set[tuple[str, str]] = set()

    async_add_entities(
        (
            ChargefoxAreaOnlineStationsSensor(coordinator),
            ChargefoxAreaAvailableConnectorsSensor(coordinator),
            ChargefoxAreaFaultedConnectorsSensor(coordinator),
            ChargefoxAreaLastDiscoverySensor(coordinator),
        )
    )

    @callback
    def async_discover_entities() -> None:
        entities: list[SensorEntity] = []
        for station_id, station in coordinator.data.items():
            if station_id not in known_stations:
                known_stations.add(station_id)
                entities.extend(
                    (
                        ChargefoxStationStatusSensor(coordinator, station_id),
                        ChargefoxStationPowerSensor(coordinator, station_id),
                        ChargefoxStationPricingSensor(coordinator, station_id),
                        ChargefoxStationDirectionsSensor(coordinator, station_id),
                        ChargefoxStationFirmwareSensor(coordinator, station_id),
                    )
                )
            for connector in station.connectors:
                key = (station_id, connector.id)
                if key not in known_connectors:
                    known_connectors.add(key)
                    entities.append(
                        ChargefoxConnectorStatusSensor(
                            coordinator, station_id, connector.id
                        )
                    )
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(async_discover_entities))
    async_discover_entities()


class ChargefoxAreaEntity(
    CoordinatorEntity[ChargefoxDataUpdateCoordinator], SensorEntity
):
    """Base entity summarising a configured Chargefox area."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChargefoxDataUpdateCoordinator) -> None:
        """Initialize an area summary entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"area_{coordinator.config_entry.entry_id}")},
            name=coordinator.config_entry.title,
            manufacturer="Chargefox",
            model="Station search area",
        )


class ChargefoxAreaOnlineStationsSensor(ChargefoxAreaEntity):
    """Number of online stations in the configured area."""

    _attr_name = "Online stations"
    _attr_translation_key = "area_online_stations"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: ChargefoxDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_online_stations"

    @property
    def native_value(self) -> int:
        """Return the number of online stations."""
        return sum(station.online is True for station in self.coordinator.data.values())

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Return station totals for context."""
        stations = self.coordinator.data.values()
        return {
            "total_stations": len(self.coordinator.data),
            "offline_stations": sum(station.online is False for station in stations),
        }


class ChargefoxAreaAvailableConnectorsSensor(ChargefoxAreaEntity):
    """Number of available connectors in the configured area."""

    _attr_name = "Available connectors"
    _attr_translation_key = "area_available_connectors"
    _attr_icon = "mdi:ev-plug-type2"

    def __init__(self, coordinator: ChargefoxDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_available_connectors"
        )

    @property
    def native_value(self) -> int:
        """Return the number of available connectors."""
        return sum(
            connector.available is True
            for station in self.coordinator.data.values()
            for connector in station.connectors
        )

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Return the total connector count for context."""
        return {
            "total_connectors": sum(
                len(station.connectors) for station in self.coordinator.data.values()
            )
        }


class ChargefoxAreaFaultedConnectorsSensor(ChargefoxAreaEntity):
    """Number of faulted connectors in the configured area."""

    _attr_name = "Faulted connectors"
    _attr_translation_key = "area_faulted_connectors"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: ChargefoxDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_faulted_connectors"

    @property
    def native_value(self) -> int:
        """Return the number of faulted connectors."""
        return sum(
            bool(connector.status and "fault" in connector.status.casefold())
            for station in self.coordinator.data.values()
            for connector in station.connectors
        )


class ChargefoxAreaLastDiscoverySensor(ChargefoxAreaEntity):
    """Time when the configured area was last searched for stations."""

    _attr_name = "Last station discovery"
    _attr_translation_key = "area_last_discovery"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ChargefoxDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_last_discovery"

    @property
    def native_value(self) -> datetime | None:
        """Return the last successful rediscovery time."""
        return self.coordinator.last_discovery


class ChargefoxStationStatusSensor(ChargefoxStationEntity, SensorEntity):
    """Chargefox station status."""

    _attr_translation_key = "station_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_status"

    @property
    def native_value(self) -> str | None:
        """Return station status."""
        return self.station.status if self.station else None


class ChargefoxStationPowerSensor(ChargefoxStationEntity, SensorEntity):
    """Chargefox station maximum power."""

    _attr_translation_key = "station_power"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_power"

    @property
    def native_value(self) -> float | None:
        """Return station maximum power."""
        return self.station.power_kw if self.station else None


class ChargefoxStationPricingSensor(ChargefoxStationEntity, SensorEntity):
    """Chargefox station pricing plan."""

    _attr_translation_key = "station_pricing"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_pricing"

    @property
    def native_value(self) -> str | None:
        """Return the pricing plan name."""
        if not self.station or not self.station.pricing_plan:
            return None
        return self.station.pricing_plan.name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return tariff and idle-fee details."""
        if not self.station:
            return {}

        attributes: dict[str, Any] = {}
        if plan := self.station.pricing_plan:
            attributes["tariffs"] = [
                strategy.description
                for strategy in plan.pricing_strategies
                if strategy.description
            ]
        if idle_fee := self.station.idle_fee:
            if price := idle_fee.price_per_minute:
                attributes["idle_fee_per_minute"] = price.formatted
                attributes["idle_fee_amount"] = price.amount
                attributes["idle_fee_currency"] = price.currency
            if grace_period := idle_fee.grace_period_duration:
                attributes["idle_fee_grace_period"] = grace_period.formatted
        return attributes


class ChargefoxStationDirectionsSensor(ChargefoxStationEntity, SensorEntity):
    """Chargefox station access directions."""

    _attr_translation_key = "station_directions"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:directions"

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_directions"

    @property
    def native_value(self) -> str | None:
        """Return directions for accessing the station."""
        if not self.station or not self.station.location:
            return None
        return self.station.location.directions


class ChargefoxStationFirmwareSensor(ChargefoxStationEntity, SensorEntity):
    """Chargefox station firmware version."""

    _attr_translation_key = "station_firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, station_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id)
        self._attr_unique_id = f"{station_id}_firmware"

    @property
    def native_value(self) -> str | None:
        """Return the station firmware version."""
        return self.station.firmware_version if self.station else None


class ChargefoxConnectorStatusSensor(ChargefoxConnectorEntity, SensorEntity):
    """Chargefox connector status."""

    _attr_translation_key = "connector_status"

    def __init__(self, coordinator, station_id: str, connector_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, station_id, connector_id)
        self._attr_unique_id = f"{station_id}_{connector_id}_status"
        connector = self.connector
        self._attr_translation_placeholders = {
            "connector": connector.plug.short_name
            if connector and connector.plug
            else connector_id
        }

    @property
    def native_value(self) -> str | None:
        """Return connector status."""
        return self.connector.status if self.connector else None

    @property
    def icon(self) -> str:
        """Return the icon for the connector's plug type."""
        if not (connector := self.connector) or not connector.plug:
            return _DEFAULT_PLUG_ICON
        return _PLUG_ICONS.get(connector.plug.short_name.casefold(), _DEFAULT_PLUG_ICON)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return connector, plug, and active-session details."""
        if not (connector := self.connector):
            return {}

        attributes: dict[str, Any] = {
            "available": connector.available,
            "preparing": connector.preparing,
            "active_session": connector.active_charge_session is not None,
        }
        if plug := connector.plug:
            attributes["plug_type"] = plug.short_name
            attributes["plug_id"] = plug.id

        if session := connector.active_charge_session:
            attributes["session_id"] = session.id
            attributes["session_state"] = session.current_state
            attributes["session_start_time"] = (
                session.start_time.isoformat() if session.start_time else None
            )
            attributes["state_of_charge"] = session.state_of_charge
            attributes["start_meter_value"] = session.start_meter_value
            attributes["total_consumption_wh"] = session.total_consumption
            attributes["charge_rate_kw"] = (
                session.charge_rate.value_kw if session.charge_rate else None
            )

        return attributes

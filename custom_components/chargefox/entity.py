"""Base entities for the Chargefox integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from chargefox import ChargeStation, Connector

from .const import DOMAIN
from .coordinator import ChargefoxDataUpdateCoordinator


def _station_device_name(station: ChargeStation | None) -> str:
    """Return a friendly device name containing its Chargefox location."""
    if station is None:
        return "Chargefox station"

    station_name = station.name or "Chargefox station"
    location_name = station.location.name if station.location else None
    if not location_name or location_name == station_name:
        return station_name
    return f"{location_name} ({station_name})"


class ChargefoxStationEntity(CoordinatorEntity[ChargefoxDataUpdateCoordinator]):
    """Base class for a Chargefox station entity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ChargefoxDataUpdateCoordinator, station_id: str
    ) -> None:
        """Initialize a station entity."""
        super().__init__(coordinator)
        self.station_id = station_id

    @property
    def station(self) -> ChargeStation | None:
        """Return the current station data."""
        return self.coordinator.data.get(self.station_id)

    @property
    def available(self) -> bool:
        """Return whether this station remains in the configured area."""
        return super().available and self.station is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return station device information."""
        station = self.station
        return DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            name=_station_device_name(station),
            manufacturer=(station.vendor if station else None) or "Chargefox",
            model=station.model if station else None,
            serial_number=station.charge_box_identity if station else None,
        )


class ChargefoxConnectorEntity(ChargefoxStationEntity):
    """Base class for a Chargefox connector entity."""

    def __init__(
        self,
        coordinator: ChargefoxDataUpdateCoordinator,
        station_id: str,
        connector_id: str,
    ) -> None:
        """Initialize a connector entity."""
        super().__init__(coordinator, station_id)
        self.connector_id = connector_id

    @property
    def connector(self) -> Connector | None:
        """Return the current connector data."""
        if (station := self.station) is None:
            return None
        return next(
            (
                connector
                for connector in station.connectors
                if connector.id == self.connector_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return whether the connector remains available from the API."""
        return super().available and self.connector is not None

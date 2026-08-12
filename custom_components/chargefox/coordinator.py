"""Data coordinator for the Chargefox integration."""

from __future__ import annotations

import base64
import binascii
import math
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from chargefox import (
    Bounds,
    ChargefoxClient,
    ChargefoxError,
    ChargefoxHTTPError,
    ChargeStation,
    LocationFilter,
)

from .const import (
    CONF_LOCATION,
    CONF_PLUG_IDS,
    DOMAIN,
    LOGGER,
    REDISCOVERY_INTERVAL,
    UPDATE_INTERVAL,
)

_METERS_PER_DEGREE = 111_320


def _canonical_global_id(value: str) -> str:
    """Return the stable record suffix from a Chargefox global ID."""
    try:
        decoded = base64.b64decode(value, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return value

    record_type, separator, record_id = decoded.rpartition("-")
    if separator and record_type and record_id:
        return record_id
    return value


def bounds_from_circle(latitude: float, longitude: float, radius: float) -> Bounds:
    """Return API bounds enclosing a circle measured in meters."""
    latitude_delta = radius / _METERS_PER_DEGREE
    longitude_delta = radius / (
        _METERS_PER_DEGREE * max(math.cos(math.radians(latitude)), 0.01)
    )
    return Bounds(
        south=max(-90, latitude - latitude_delta),
        west=max(-180, longitude - longitude_delta),
        north=min(90, latitude + latitude_delta),
        east=min(180, longitude + longitude_delta),
    )


class ChargefoxDataUpdateCoordinator(DataUpdateCoordinator[dict[str, ChargeStation]]):
    """Fetch and maintain Chargefox stations within the configured area."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: ChargefoxClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._station_ids: set[str] | None = None
        self._last_discovery: datetime | None = None

    @property
    def station_ids(self) -> set[str]:
        """Return all station IDs found during the latest discovery."""
        return self._station_ids or set()

    @property
    def last_discovery(self) -> datetime | None:
        """Return the time of the latest successful discovery."""
        return self._last_discovery

    def _enabled_station_ids(self, station_ids: set[str]) -> list[str]:
        """Return known station IDs whose Home Assistant devices are enabled."""
        device_registry = dr.async_get(self.hass)
        return sorted(
            station_id
            for station_id in station_ids
            if (device := device_registry.async_get_device({(DOMAIN, station_id)}))
            is None
            or device.disabled_by is None
        )

    def _rediscovery_due(self, now: datetime) -> bool:
        """Return whether station discovery should run."""
        return (
            self._last_discovery is None
            or now - self._last_discovery >= REDISCOVERY_INTERVAL
        )

    async def _async_update_data(self) -> dict[str, ChargeStation]:
        """Fetch station and connector states."""
        location = self.config_entry.options.get(
            CONF_LOCATION, self.config_entry.data[CONF_LOCATION]
        )
        latitude = location[CONF_LATITUDE]
        longitude = location[CONF_LONGITUDE]
        radius = location[CONF_RADIUS]
        plug_ids = self.config_entry.options.get(
            CONF_PLUG_IDS, self.config_entry.data.get(CONF_PLUG_IDS, [])
        )
        now = dt_util.utcnow()
        rediscovery_due = self._rediscovery_due(now)

        try:
            station_ids = self._station_ids or set()
            if rediscovery_due:
                summaries = await self.client.get_locations_by_bounds(
                    bounds_from_circle(latitude, longitude, radius),
                    LocationFilter(plug_ids=plug_ids or None),
                )
                station_ids = {
                    station.id
                    for summary in summaries
                    if distance(
                        latitude, longitude, summary.latitude, summary.longitude
                    )
                    <= radius
                    for station in summary.charge_stations
                }
            stations = await self.client.get_charge_stations(
                self._enabled_station_ids(station_ids)
            )
        except ChargefoxHTTPError as err:
            if err.status_code in (401, 403):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Chargefox: {err}") from err
        except ChargefoxError as err:
            raise UpdateFailed(f"Error communicating with Chargefox: {err}") from err

        canonical_plug_ids = {_canonical_global_id(plug_id) for plug_id in plug_ids}
        filtered_stations = {
            station.id: station
            for station in stations
            if station.location is not None
            and station.location.latitude is not None
            and station.location.longitude is not None
            and distance(
                latitude,
                longitude,
                station.location.latitude,
                station.location.longitude,
            )
            <= radius
            and (
                not plug_ids
                or any(
                    connector.plug is not None
                    and _canonical_global_id(connector.plug.id) in canonical_plug_ids
                    for connector in station.connectors
                )
            )
        }
        if rediscovery_due:
            self._station_ids = station_ids
            self._last_discovery = now
        return filtered_stations

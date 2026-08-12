"""Data coordinator for the Chargefox integration."""

from __future__ import annotations

import asyncio
import base64
import binascii
import math

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.location import distance

from chargefox import (
    Bounds,
    ChargefoxClient,
    ChargefoxError,
    ChargefoxHTTPError,
    ChargeStation,
    LocationFilter,
)

from .const import CONF_LOCATION, CONF_PLUG_IDS, DOMAIN, LOGGER, UPDATE_INTERVAL

_METERS_PER_DEGREE = 111_320
_MAX_CONCURRENT_REQUESTS = 5


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

        try:
            bounds = bounds_from_circle(latitude, longitude, radius)
            location_filter = LocationFilter(plug_ids=plug_ids or None)
            summaries = await self.client.get_locations_by_bounds(
                bounds,
                location_filter,
            )
            location_ids = [
                summary.id
                for summary in summaries
                if distance(latitude, longitude, summary.latitude, summary.longitude)
                <= radius
            ]
            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

            async def async_get_location(location_id: str):
                async with semaphore:
                    return await self.client.get_location(location_id)

            results = await asyncio.gather(
                *(async_get_location(location_id) for location_id in location_ids),
                return_exceptions=True,
            )
        except ChargefoxHTTPError as err:
            if err.status_code in (401, 403):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Chargefox: {err}") from err
        except ChargefoxError as err:
            raise UpdateFailed(f"Error communicating with Chargefox: {err}") from err

        stations: dict[str, ChargeStation] = {}
        failures: list[ChargefoxError] = []
        canonical_plug_ids = {_canonical_global_id(plug_id) for plug_id in plug_ids}
        for result in results:
            if isinstance(result, ChargefoxHTTPError) and result.status_code in (
                401,
                403,
            ):
                raise ConfigEntryAuthFailed from result
            if isinstance(result, ChargefoxError):
                failures.append(result)
                continue
            if isinstance(result, BaseException):
                raise result

            for station in result.charge_stations:
                if plug_ids and not any(
                    connector.plug is not None
                    and _canonical_global_id(connector.plug.id) in canonical_plug_ids
                    for connector in station.connectors
                ):
                    continue
                station.location = result
                stations[station.id] = station

        if failures and not stations:
            raise UpdateFailed(
                f"Error communicating with Chargefox: {failures[0]}"
            ) from failures[0]
        if failures:
            LOGGER.warning(
                "Unable to update %s of %s Chargefox locations",
                len(failures),
                len(results),
            )

        return stations

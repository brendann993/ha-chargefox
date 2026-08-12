"""Diagnostics support for the Chargefox integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from . import ChargefoxConfigEntry
from .const import CONF_LOCATION

TO_REDACT = {CONF_ACCESS_TOKEN, CONF_LOCATION}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChargefoxConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a Chargefox config entry."""
    coordinator = entry.runtime_data
    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_discovery": coordinator.last_discovery,
            "last_update_success": coordinator.last_update_success,
            "stations_discovered": len(coordinator.station_ids),
            "stations_returned": len(coordinator.data),
        },
        "stations": [
            {
                "id": station.id,
                "status": station.status,
                "online": station.online,
                "enabled": station.enabled,
                "connector_count": len(station.connectors),
                "connector_statuses": [
                    connector.status for connector in station.connectors
                ],
            }
            for station in coordinator.data.values()
        ],
    }

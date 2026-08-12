"""The Chargefox integration."""

from chargefox import ChargefoxClient
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import ChargefoxDataUpdateCoordinator

PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR)

type ChargefoxConfigEntry = ConfigEntry[ChargefoxDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ChargefoxConfigEntry) -> bool:
    """Set up Chargefox from a config entry."""
    client = ChargefoxClient(
        entry.data.get(CONF_ACCESS_TOKEN), session=async_get_clientsession(hass)
    )
    coordinator = ChargefoxDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    device_registry = dr.async_get(hass)
    for station_id in coordinator.data:
        if (
            device := device_registry.async_get_device({(DOMAIN, station_id)})
        ) is not None and device.sw_version is not None:
            device_registry.async_update_device(device.id, sw_version=None)

    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.platform == DOMAIN and entity_entry.unique_id.endswith(
            "_available"
        ):
            entity_registry.async_remove(entity_entry.entity_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargefoxConfigEntry) -> bool:
    """Unload a Chargefox config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

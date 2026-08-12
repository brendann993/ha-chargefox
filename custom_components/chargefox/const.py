"""Constants for the Chargefox integration."""

from datetime import timedelta
import logging

DOMAIN = "chargefox"
LOGGER = logging.getLogger(__package__)

CONF_LOCATION = "location"
CONF_PLUG_IDS = "plug_ids"
DEFAULT_RADIUS = 5000
UPDATE_INTERVAL = timedelta(minutes=2)

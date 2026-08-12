"""Constants for the Chargefox integration."""

import logging
from datetime import timedelta

DOMAIN = "chargefox"
LOGGER = logging.getLogger(__package__)

CONF_LOCATION = "location"
CONF_PLUG_IDS = "plug_ids"
DEFAULT_RADIUS = 5000
REDISCOVERY_INTERVAL = timedelta(hours=6)
UPDATE_INTERVAL = timedelta(minutes=2)

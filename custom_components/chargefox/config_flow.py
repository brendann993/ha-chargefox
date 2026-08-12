"""Config flow for the Chargefox integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.location import distance

from chargefox import (
    ChargefoxClient,
    ChargefoxError,
    ChargefoxGraphQLError,
    ChargefoxHTTPError,
    LocationFilter,
    Plug,
)

from .const import CONF_LOCATION, CONF_PLUG_IDS, DEFAULT_RADIUS, DOMAIN, LOGGER
from .coordinator import bounds_from_circle


def _is_auth_error(err: ChargefoxGraphQLError) -> bool:
    """Return whether a GraphQL error indicates failed authentication."""
    return any(
        marker in str(err).lower()
        for marker in ("auth", "token", "log in", "unauthorized")
    )


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    fetch_plugs: bool = False,
) -> list[Plug]:
    """Validate connectivity and confirm the circle contains a matching station."""
    location = data[CONF_LOCATION]
    client = ChargefoxClient(
        data.get(CONF_ACCESS_TOKEN), session=async_get_clientsession(hass)
    )
    plug_ids = data.get(CONF_PLUG_IDS, [])
    try:
        locations = await client.get_locations_by_bounds(
            bounds_from_circle(
                location[CONF_LATITUDE],
                location[CONF_LONGITUDE],
                location[CONF_RADIUS],
            ),
            LocationFilter(plug_ids=plug_ids or None),
        )
        plugs = await client.get_plugs() if fetch_plugs else []
    except ChargefoxHTTPError as err:
        if err.status_code in (401, 403):
            raise InvalidAuth from err
        raise CannotConnect from err
    except ChargefoxGraphQLError as err:
        if _is_auth_error(err):
            raise InvalidAuth from err
        raise CannotConnect from err
    except ChargefoxError as err:
        raise CannotConnect from err

    if not any(
        summary.charge_stations
        and distance(
            location[CONF_LATITUDE],
            location[CONF_LONGITUDE],
            summary.latitude,
            summary.longitude,
        )
        <= location[CONF_RADIUS]
        for summary in locations
    ):
        raise NoStations

    return plugs


def _user_schema(default_location: dict[str, float]) -> vol.Schema:
    """Return the first setup-step schema."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required(CONF_LOCATION, default=default_location): LocationSelector(
                LocationSelectorConfig(radius=True)
            ),
        }
    )


def _plug_schema(plugs: list[Plug], selected: list[str] | None = None) -> vol.Schema:
    """Return a plug-type multi-select schema."""
    options = [
        SelectOptionDict(value=plug.id, label=plug.short_name or plug.id)
        for plug in plugs
    ]
    return vol.Schema(
        {
            vol.Optional(CONF_PLUG_IDS, default=selected or []): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, sort=True)
            )
        }
    )


class ChargefoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chargefox."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}
        self._plugs: list[Plug] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the area and friendly name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                plugs = await validate_input(self.hass, user_input, fetch_plugs=True)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except NoStations:
                errors["base"] = "no_stations"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception during Chargefox setup")
                errors["base"] = "unknown"
            else:
                location = user_input[CONF_LOCATION]
                await self.async_set_unique_id(
                    f"{location[CONF_LATITUDE]:.5f},{location[CONF_LONGITUDE]:.5f}"
                )
                self._abort_if_unique_id_configured()
                self._data = user_input
                self._plugs = plugs
                return await self.async_step_plugs()

        default_location = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_RADIUS: DEFAULT_RADIUS,
        }
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(default_location), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_plugs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select optional plug-type filters."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._data, **user_input}
            try:
                await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except NoStations:
                errors["base"] = "no_matching_stations"
            else:
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="plugs",
            data_schema=_plug_schema(
                self._plugs,
                user_input.get(CONF_PLUG_IDS) if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and save a replacement bearer token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            updated_data = {**entry.data, **user_input}
            try:
                await validate_input(self.hass, updated_data)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except NoStations:
                errors["base"] = "no_stations"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ChargefoxOptionsFlow:
        """Return the options flow."""
        return ChargefoxOptionsFlow()


class ChargefoxOptionsFlow(OptionsFlowWithReload):
    """Handle Chargefox area and plug-filter options."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._plugs: list[Plug] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the station search area and plug filters."""
        errors: dict[str, str] = {}
        if not self._plugs:
            try:
                client = ChargefoxClient(
                    self.config_entry.data.get(CONF_ACCESS_TOKEN),
                    session=async_get_clientsession(self.hass),
                )
                self._plugs = await client.get_plugs()
            except ChargefoxError:
                errors["base"] = "cannot_connect"

        current_options = self.config_entry.options
        location = current_options.get(
            CONF_LOCATION, self.config_entry.data[CONF_LOCATION]
        )
        plug_ids = current_options.get(
            CONF_PLUG_IDS, self.config_entry.data.get(CONF_PLUG_IDS, [])
        )

        if user_input is not None:
            validation_data = {**self.config_entry.data, **user_input}
            try:
                await validate_input(self.hass, validation_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except NoStations:
                errors["base"] = "no_matching_stations"
            else:
                options = dict(user_input)
                name = options.pop(CONF_NAME)
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=name
                )
                return self.async_create_entry(data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=self.config_entry.title
                ): TextSelector(),
                vol.Required(CONF_LOCATION, default=location): LocationSelector(
                    LocationSelectorConfig(radius=True)
                ),
                **_plug_schema(self._plugs, plug_ids).schema,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


class CannotConnect(HomeAssistantError):
    """The Chargefox API could not be reached."""


class InvalidAuth(HomeAssistantError):
    """The bearer token is invalid."""


class NoStations(HomeAssistantError):
    """No Chargefox stations were found in the selected circle."""

"""Alexa.Discovery handler — returns all configured devices as Alexa endpoints."""

from __future__ import annotations

import logging

from tiberio.commands.discover_devices import DiscoverDevicesCommand, DiscoveredDevice
from tiberio.interfaces.alexa.models import AlexaDirectiveRequest
from tiberio.interfaces.alexa.response_builder import build_discovery_response

log = logging.getLogger(__name__)

_ALEXA_BASE = {"type": "AlexaInterface", "interface": "Alexa", "version": "3"}


def _power_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.PowerController",
        "version": "3",
        "properties": {
            "supported": [{"name": "powerState"}],
            "proactivelyReported": False,
            "retrievable": False,
        },
    }


def _speaker_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.Speaker",
        "version": "3",
        "properties": {
            # Mute only. Volume is intentionally omitted so Alexa never sends
            # SetVolume/AdjustVolume — the skill must not change the volume.
            "supported": [{"name": "muted"}],
            "proactivelyReported": False,
            "retrievable": False,
        },
    }


def _thermostat_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.ThermostatController",
        "version": "3",
        "properties": {
            "supported": [{"name": "targetSetpoint"}, {"name": "thermostatMode"}],
            "proactivelyReported": False,
            "retrievable": True,
        },
        "configuration": {
            "supportedModes": ["HEAT"],
            "supportsScheduling": False,
        },
    }


def _temperature_sensor_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.TemperatureSensor",
        "version": "3",
        "properties": {
            "supported": [{"name": "temperature"}],
            "proactivelyReported": False,
            "retrievable": True,
        },
    }


def _endpoint_health_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.EndpointHealth",
        "version": "3",
        "properties": {
            "supported": [{"name": "connectivity"}],
            "proactivelyReported": False,
            "retrievable": True,
        },
    }


def _range_capability() -> dict:
    return {
        "type": "AlexaInterface",
        "interface": "Alexa.RangeController",
        "instance": "Blind.Position",
        "version": "3",
        "properties": {
            "supported": [{"name": "rangeValue"}],
            "proactivelyReported": False,
            "retrievable": True,
        },
        "capabilityResources": {
            "friendlyNames": [
                {"@type": "asset", "value": {"assetId": "Alexa.Setting.Opening"}}
            ]
        },
        "configuration": {
            "supportedRange": {"minimumValue": 0, "maximumValue": 100, "precision": 1},
            "unitOfMeasure": "Alexa.Unit.Percent",
        },
        "semantics": {
            "actionMappings": [
                {
                    "@type": "ActionsToDirective",
                    "actions": ["Alexa.Actions.Close"],
                    "directive": {
                        "name": "SetRangeValue",
                        "payload": {"rangeValue": 0},
                    },
                },
                {
                    "@type": "ActionsToDirective",
                    "actions": ["Alexa.Actions.Open"],
                    "directive": {
                        "name": "SetRangeValue",
                        "payload": {"rangeValue": 100},
                    },
                },
                {
                    "@type": "ActionsToDirective",
                    "actions": ["Alexa.Actions.Lower"],
                    "directive": {
                        "name": "AdjustRangeValue",
                        "payload": {
                            "rangeValueDelta": -10,
                            "rangeValueDeltaDefault": False,
                        },
                    },
                },
                {
                    "@type": "ActionsToDirective",
                    "actions": ["Alexa.Actions.Raise"],
                    "directive": {
                        "name": "AdjustRangeValue",
                        "payload": {
                            "rangeValueDelta": 10,
                            "rangeValueDeltaDefault": False,
                        },
                    },
                },
            ],
            "stateMappings": [
                {
                    "@type": "StatesToValue",
                    "states": ["Alexa.States.Closed"],
                    "value": 0,
                },
                {
                    "@type": "StatesToRange",
                    "states": ["Alexa.States.Open"],
                    "range": {"minimumValue": 1, "maximumValue": 100},
                },
            ],
        },
    }


_CAPABILITY_BY_KIND = {
    "power": (_power_capability, "SWITCH", "TV-Kanal"),
    "speaker": (_speaker_capability, "SPEAKER", "TV-Lautsprecher"),
    "thermostat": (_thermostat_capability, "THERMOSTAT", "Heizungsthermostat"),
    "range": (_range_capability, "INTERIOR_BLIND", "Rollo / Jalousie"),
}

# Secondary interfaces a capability kind always exposes alongside its primary.
# A thermostat pairs ThermostatController with TemperatureSensor so the Alexa
# app renders the current room temperature and an interactive control.
_EXTRA_CAPABILITIES_BY_KIND = {
    "thermostat": (_temperature_sensor_capability, _endpoint_health_capability),
}


def _build_endpoint(device: DiscoveredDevice) -> dict | None:
    primary = _CAPABILITY_BY_KIND.get(device.capabilities[0])
    if primary is None:
        log.warning(
            "DiscoveryHandler: unknown capability %r for device %s — skipped",
            device.capabilities[0],
            device.id,
        )
        return None
    _, category, description = primary

    capabilities = []
    for kind in device.capabilities:
        entry = _CAPABILITY_BY_KIND.get(kind)
        if entry is None:
            log.warning(
                "DiscoveryHandler: unknown capability %r for device %s — skipped",
                kind,
                device.id,
            )
            continue
        capabilities.append(entry[0]())
        capabilities.extend(
            extra() for extra in _EXTRA_CAPABILITIES_BY_KIND.get(kind, ())
        )
    capabilities.append(_ALEXA_BASE)

    return {
        "endpointId": device.id,
        "friendlyName": device.name,
        "description": description,
        "manufacturerName": "tiberio",
        "displayCategories": [category],
        "cookie": {},
        "capabilities": capabilities,
    }


class DiscoveryHandler:
    def __init__(self, discover_devices: DiscoverDevicesCommand) -> None:
        self._discover_devices = discover_devices

    async def handle(self, _req: AlexaDirectiveRequest) -> dict:
        devices = await self._discover_devices.execute()
        endpoints = [e for d in devices if (e := _build_endpoint(d)) is not None]
        log.info("DiscoveryHandler: returning %d endpoints", len(endpoints))
        return build_discovery_response(endpoints)

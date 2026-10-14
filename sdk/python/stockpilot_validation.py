"""Plugin API 1 contract. Server-parity tests guard this standalone copy."""
import hashlib
import json
import re

ValidationError = ValueError

CORE_VERSION = "0.14.0"


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", value):
        raise ValidationError("Use a stable version such as 1.2.0")
    return tuple(map(int, value.split(".")))


def checksum(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def validate(manifest):
    fields = {
        "id",
        "name",
        "version",
        "api",
        "core_min",
        "core_max",
        "hook",
        "requires",
        "settings",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValidationError("Manifest fields do not match plugin API 1")
    if not isinstance(manifest["id"], str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,63}", manifest["id"]
    ):
        raise ValidationError("Invalid plugin ID")
    if not isinstance(manifest["name"], str) or not 1 <= len(manifest["name"]) <= 80:
        raise ValidationError("Invalid plugin name")
    version(manifest["version"])
    if type(manifest["api"]) is not int or manifest["api"] != 1 or not isinstance(manifest["hook"], str) or manifest["hook"] not in {"inventory.low_stock", "dashboard.notice"}:
        raise ValidationError("Unsupported plugin API or hook")
    if not version(manifest["core_min"]) <= version(CORE_VERSION) < version(manifest["core_max"]):
        raise ValidationError("Release is not compatible with this ERP version")
    required_settings = {"threshold"} if manifest["hook"] == "inventory.low_stock" else {"message"}
    if not isinstance(manifest["settings"], dict) or set(manifest["settings"]) != required_settings:
        raise ValidationError("Settings do not match the hook contract")
    if not isinstance(manifest["requires"], dict) or len(manifest["requires"]) > 10:
        raise ValidationError("Invalid dependencies")
    for slug, minimum in manifest["requires"].items():
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", slug) or slug == manifest["id"]:
            raise ValidationError("Invalid dependency ID")
        version(minimum)
    configuration(manifest, manifest["settings"])
    return manifest


def configuration(manifest, values):
    if not isinstance(values, dict) or set(values) != set(manifest["settings"]):
        raise ValidationError("Configuration must contain exactly the declared settings")
    if manifest["hook"] == "inventory.low_stock":
        if type(values["threshold"]) is not int or not 0 <= values["threshold"] <= 100000:
            raise ValidationError("Threshold must be an integer from 0 to 100000")
    elif not isinstance(values["message"], str) or not 1 <= len(values["message"]) <= 200:
        raise ValidationError("Message must have 1 to 200 characters")
    return values.copy()


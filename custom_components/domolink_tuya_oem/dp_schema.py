"""DP Schema parser and validator based on official Tuya OEM product definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Literal

_LOGGER = logging.getLogger(__name__)

DPType = Literal["bool", "value", "enum", "string", "raw", "bitmap", "fault", "json"]


@dataclass
class DPSpec:
    """Specification of a single Tuya DataPoint from official product schema."""

    dp_id: str
    code: str
    name: str
    mode: str = "rw"  # "rw", "ro", "wr"
    dp_type: DPType = "string"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    scale: int = 0
    unit: str | None = None
    range_options: list[str] = field(default_factory=list)
    raw_property: dict[str, Any] = field(default_factory=dict)

    @property
    def writable(self) -> bool:
        """Return True if DP can be controlled from Home Assistant."""
        return "w" in self.mode.lower()

    @property
    def readable(self) -> bool:
        """Return True if DP can be read from Home Assistant."""
        return "r" in self.mode.lower()

    def format_value(self, raw_val: Any) -> Any:
        """Format raw DP value applying scale factor if numeric."""
        if raw_val is None:
            return None
        if self.dp_type == "value" and isinstance(raw_val, (int, float)):
            if self.scale > 0:
                scaled = raw_val / (10**self.scale)
                return round(scaled, self.scale)
            return raw_val
        return raw_val

    def coerce_to_raw(self, user_val: Any) -> Any:
        """Coerce user input to valid Tuya raw payload value according to schema constraints."""
        if self.dp_type == "bool":
            return bool(user_val)

        if self.dp_type == "value" and isinstance(user_val, (int, float)):
            # If user passed a scaled float, scale back to integer raw
            raw_val = user_val * (10**self.scale) if self.scale > 0 else user_val
            raw_val = float(raw_val)

            # Clamp between min and max
            if self.min is not None:
                raw_val = max(raw_val, float(self.min))
            if self.max is not None:
                raw_val = min(raw_val, float(self.max))

            # Step alignment if specified
            if self.step and self.step > 0:
                base = float(self.min or 0)
                steps = round((raw_val - base) / float(self.step))
                raw_val = base + steps * float(self.step)

            return int(round(raw_val))

        if self.dp_type == "enum":
            str_val = str(user_val)
            if self.range_options and str_val not in self.range_options:
                # Find closest case-insensitive match or keep original
                for opt in self.range_options:
                    if opt.lower() == str_val.lower():
                        return opt
            return str_val

        return user_val


def parse_dp_schema(schema_raw: Any, dp_names: dict[str, Any] | None = None) -> dict[str, DPSpec]:
    """Parse raw schema data returned by Tuya Mobile API into structured DPSpec dictionary."""
    specs: dict[str, DPSpec] = {}
    if not schema_raw:
        return specs

    dp_list: list[dict[str, Any]] = []

    # Handle stringified JSON or dict wrappers
    if isinstance(schema_raw, str):
        try:
            parsed = json.loads(schema_raw)
            if isinstance(parsed, list):
                dp_list = parsed
            elif isinstance(parsed, dict) and "schema" in parsed:
                return parse_dp_schema(parsed["schema"], dp_names)
        except Exception as e:
            _LOGGER.debug("Could not parse schema JSON string: %s", e)
            return specs
    elif isinstance(schema_raw, list):
        dp_list = schema_raw
    elif isinstance(schema_raw, dict):
        if "schema" in schema_raw:
            return parse_dp_schema(schema_raw["schema"], dp_names)
        elif "schemaInfo" in schema_raw:
            return parse_dp_schema(schema_raw["schemaInfo"], dp_names)
        else:
            # Maybe a dict of DP objects keyed by id
            dp_list = list(schema_raw.values())

    names_map = dp_names or {}

    for item in dp_list:
        if not isinstance(item, dict):
            continue

        dp_id = str(item.get("id") or item.get("dpId") or item.get("dp_id") or "")
        code = str(item.get("code") or dp_id)
        if not dp_id and not code:
            continue
        if not dp_id:
            dp_id = code

        # Human name: user dpName override -> schema name -> standard code
        name = names_map.get(dp_id) or item.get("name") or code

        mode = str(item.get("mode") or "rw").lower()
        raw_type = str(item.get("type") or "string").lower()
        if raw_type not in ("bool", "value", "enum", "string", "raw", "bitmap", "fault", "json"):
            raw_type = "string"

        # Properties (min, max, step, scale, unit, range)
        prop_data = item.get("property") or {}
        if isinstance(prop_data, str):
            try:
                prop_data = json.loads(prop_data)
            except Exception:
                prop_data = {}

        min_val = prop_data.get("min")
        max_val = prop_data.get("max")
        step_val = prop_data.get("step")
        scale_val = int(prop_data.get("scale") or 0)
        unit_val = prop_data.get("unit") or None

        range_opts: list[str] = []
        raw_range = prop_data.get("range")
        if isinstance(raw_range, list):
            range_opts = [str(x) for x in raw_range]
        elif isinstance(raw_range, str):
            try:
                range_opts = [str(x) for x in json.loads(raw_range)]
            except Exception:
                range_opts = [s.strip() for s in raw_range.split(",") if s.strip()]

        spec = DPSpec(
            dp_id=dp_id,
            code=code,
            name=name,
            mode=mode,
            dp_type=raw_type,  # type: ignore[arg-type]
            min=float(min_val) if min_val is not None else None,
            max=float(max_val) if max_val is not None else None,
            step=float(step_val) if step_val is not None else None,
            scale=scale_val,
            unit=unit_val,
            range_options=range_opts,
            raw_property=prop_data,
        )

        specs[dp_id] = spec
        if code and code != dp_id:
            specs[code] = spec

    return specs

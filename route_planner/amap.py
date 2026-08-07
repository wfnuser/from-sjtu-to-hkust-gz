"""Secret-safe, cached client for the AMap routing and geocoding APIs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import ssl
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from route_planner.models import CandidateRoute, Coordinate, GeocodeCandidate, RouteStep
from route_planner.roads import classify_risks, classify_road


_BASE_URL = "https://restapi.amap.com"
_KEY_NAMES = ("AMAP_WEB_SERVICE_KEY", "AMAP_KEY")
_FALLBACK_CA_FILES = (Path("/etc/ssl/cert.pem"),)


class AmapError(RuntimeError):
    """An AMap request or response could not be used safely."""


def load_amap_key(path: Path) -> str:
    """Load the AMap web-service key from a local dotenv-style file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Unable to read AMap key file: {path}") from error

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").lstrip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() not in _KEY_NAMES:
            continue
        key = value.strip().strip("\"'")
        if key:
            return key
        break

    raise ValueError(f"one of {', '.join(_KEY_NAMES)} must be set in {path}")


class AmapClient:
    """Fetch AMap responses without putting credentials in cache material or errors."""

    def __init__(self, key: str, cache_dir: Path, min_interval_s: float = 1.05):
        if not isinstance(key, str) or not key:
            raise ValueError("AMap key must be a non-empty string")
        if min_interval_s < 0:
            raise ValueError("min_interval_s must not be negative")

        self._key = key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self._last_start_monotonic: float | None = None
        self._ssl_context = _verified_ssl_context()
        self._urlopen = urlopen

    def cache_key(self, endpoint: str, params: dict[str, str]) -> str:
        """Return a stable cache key based only on public request data."""
        public_params = {name: value for name, value in params.items() if name != "key"}
        material = endpoint + "?" + urlencode(sorted(public_params.items()))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def electrobike(
        self,
        origin: Coordinate,
        destination: Coordinate,
        alternatives: int = 3,
    ) -> tuple[CandidateRoute, ...]:
        """Return all AMap electric-bike alternatives and their classified steps."""
        if not isinstance(alternatives, int) or isinstance(alternatives, bool) or alternatives < 1:
            raise ValueError("alternatives must be a positive integer")
        payload = self._fetch(
            "/v5/direction/electrobike",
            {
                "origin": _coordinate_text(origin),
                "destination": _coordinate_text(destination),
                "show_fields": "polyline",
                "alternative_route": str(alternatives),
            },
        )
        paths = _expect_list(_expect_object(payload.get("route"), "route").get("paths"), "route.paths")
        return tuple(_parse_route(index, path) for index, path in enumerate(paths))

    def geocode(self, query: str, city: str) -> tuple[GeocodeCandidate, ...]:
        """Resolve a Chinese place query to the candidates returned by AMap."""
        if not isinstance(query, str) or not query:
            raise ValueError("query must be a non-empty string")
        if not isinstance(city, str) or not city:
            raise ValueError("city must be a non-empty string")
        try:
            payload = self._fetch("/v3/geocode/geo", {"address": query, "city": city})
        except AmapError as error:
            if "30001 ENGINE_RESPONSE_DATA_ERROR" not in str(error):
                raise
            return self.search_pois(query, city)
        geocodes = _expect_list(payload.get("geocodes"), "geocodes")
        return tuple(_parse_geocode(item, query) for item in geocodes)

    def search_pois(self, query: str, city: str) -> tuple[GeocodeCandidate, ...]:
        """Search named POIs and retain the official name, address, and AMap POI ID."""
        if not isinstance(query, str) or not query:
            raise ValueError("query must be a non-empty string")
        if not isinstance(city, str) or not city:
            raise ValueError("city must be a non-empty string")
        payload = self._fetch(
            "/v3/place/text",
            {
                "keywords": query,
                "city": city,
                "citylimit": "true",
                "offset": "20",
                "page": "1",
                "extensions": "all",
            },
        )
        pois = _expect_list(payload.get("pois"), "pois")
        return tuple(_parse_place(item) for item in pois)

    def _fetch(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        cache_path = self.cache_dir / f"{self.cache_key(endpoint, params)}.json"
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cache_path.unlink(missing_ok=True)
            else:
                return self._validate_status(payload, endpoint)

        self._throttle()
        transport_failed = False
        try:
            # Key injection occurs only while constructing the request handed to urlopen.
            with self._urlopen(
                Request(f"{_BASE_URL}{endpoint}?{urlencode({**params, 'key': self._key})}"),
                timeout=30,
                context=self._ssl_context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            transport_failed = True

        if transport_failed:
            # Raise outside the handler so no URL-bearing exception remains chained.
            raise AmapError(f"AMap transport request failed at {endpoint}")

        payload = self._validate_status(payload, endpoint)
        try:
            cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError as error:
            raise AmapError(f"Unable to cache AMap response for {endpoint}") from error
        return payload

    def _throttle(self) -> None:
        if self._last_start_monotonic is not None:
            remaining = self.min_interval_s - (time.monotonic() - self._last_start_monotonic)
            if remaining > 0:
                time.sleep(remaining)
        self._last_start_monotonic = time.monotonic()

    def _validate_status(self, payload: Any, endpoint: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AmapError(f"Invalid AMap response at {endpoint}")
        if payload.get("status") != "1":
            infocode = self._redact(str(payload.get("infocode", "unknown")))
            info = self._redact(str(payload.get("info", "unknown")))
            raise AmapError(f"AMap request failed at {endpoint}: {infocode} {info}")
        return payload

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "[redacted]")


def _coordinate_text(coordinate: Coordinate) -> str:
    return f"{coordinate.lon},{coordinate.lat}"


def _verified_ssl_context() -> ssl.SSLContext:
    """Create a certificate-verifying context with a usable local CA fallback."""
    configured = os.environ.get("SSL_CERT_FILE")
    candidates = ((Path(configured),) if configured else ()) + _FALLBACK_CA_FILES
    for candidate in candidates:
        if candidate.is_file():
            return ssl.create_default_context(cafile=str(candidate))
    return ssl.create_default_context()


def _parse_route(index: int, value: Any) -> CandidateRoute:
    path = _expect_object(value, "route path")
    steps = _expect_list(path.get("steps"), "route path steps")
    return CandidateRoute(
        source_index=index,
        distance_m=_parse_int(path.get("distance"), "route path distance"),
        duration_s=_parse_int(path.get("duration"), "route path duration"),
        steps=tuple(_parse_step(step) for step in steps),
    )


def _parse_step(value: Any) -> RouteStep:
    step = _expect_object(value, "route step")
    instruction = _expect_string(step.get("instruction"), "route step instruction")
    road_name = _expect_string(step.get("road_name"), "route step road_name")
    return RouteStep(
        instruction=instruction,
        road_name=road_name,
        distance_m=_parse_int(step.get("step_distance"), "route step step_distance"),
        polyline_gcj=_parse_polyline(step.get("polyline")),
        road_class=classify_road(road_name, instruction),
        risk_tags=classify_risks(road_name, instruction),
    )


def _parse_geocode(value: Any, query: str) -> GeocodeCandidate:
    geocode = _expect_object(value, "geocode")
    district = _optional_text(geocode.get("district"))
    formatted_address = "".join(
        _optional_text(geocode.get(field))
        for field in ("province", "city", "district", "street", "number")
    )
    return GeocodeCandidate(
        name=query,
        formatted_address=formatted_address or query,
        district=district,
        location_gcj=_parse_location(geocode.get("location")),
    )


def _parse_place(value: Any) -> GeocodeCandidate:
    place = _expect_object(value, "place")
    name = _expect_string(place.get("name"), "place name")
    poi_id = _expect_string(place.get("id"), "place id")
    district = _optional_text(place.get("adname"))
    formatted_address = "".join(
        _optional_text(place.get(field))
        for field in ("pname", "cityname", "adname", "address")
    )
    return GeocodeCandidate(
        name=name,
        formatted_address=formatted_address or name,
        district=district,
        location_gcj=_parse_location(place.get("location")),
        poi_id=poi_id,
    )


def _parse_polyline(value: Any) -> tuple[Coordinate, ...]:
    if not isinstance(value, str) or not value:
        raise AmapError("Invalid route step polyline")
    return tuple(_parse_location(point) for point in value.split(";") if point)


def _parse_location(value: Any) -> Coordinate:
    if not isinstance(value, str):
        raise AmapError("Invalid AMap coordinate")
    parts = value.split(",")
    if len(parts) != 2:
        raise AmapError("Invalid AMap coordinate")
    try:
        return Coordinate(lon=float(parts[0]), lat=float(parts[1]))
    except ValueError as error:
        raise AmapError("Invalid AMap coordinate") from error


def _expect_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AmapError(f"Invalid AMap {context}")
    return value


def _expect_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise AmapError(f"Invalid AMap {context}")
    return value


def _expect_string(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise AmapError(f"Invalid AMap {context}")
    return value


def _optional_text(value: Any) -> str:
    """Normalize AMap's documented string-or-array optional response fields."""
    return value.strip() if isinstance(value, str) else ""


def _parse_int(value: Any, context: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise AmapError(f"Invalid AMap {context}") from error
    if result < 0:
        raise AmapError(f"Invalid AMap {context}")
    return result

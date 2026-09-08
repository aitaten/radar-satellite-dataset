"""E-SOH OGC API - EDR client for station observations."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import DirectoryConfig
from .covjson import coveragejson_to_records
from .http import build_session
from .models import StationObservations


class ESoHClient:
    """Client for the public E-SOH observation EDR service.

    The client is intentionally endpoint-oriented: locations/metadata retrieval
    is separate from observation retrieval so callers can build their own
    workflows rather than being tied to one plotting use case.
    """

    def __init__(
        self,
        base_url: str = "https://observations.meteogate.eu",
        cache_dir: Path | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_dir = Path(cache_dir or DirectoryConfig().esoh_cache)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = build_session(retries=5, backoff_factor=0.5)

    def _get_json(self, path: str, params: dict[str, Any] | None = None, cache_name: str | None = None):
        if cache_name:
            cache_file = self.cache_dir / cache_name
            if cache_file.exists() and cache_file.stat().st_size > 0:
                return json.loads(cache_file.read_text(encoding="utf-8"))

        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        print("\n--- E-SOH request ---")
        print("URL:", response.url)
        print("Status:", response.status_code)

        if not response.ok:
            print("Response:", response.text)

        response.raise_for_status()
        data = response.json()
        if cache_name:
            (self.cache_dir / cache_name).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def metadata(self) -> dict[str, Any]:
        return self._get_json("/collections/observations", cache_name="collection_observations.json")

    def locations(self) -> dict[str, Any]:
        return self._get_json("/collections/observations/locations", cache_name="locations.json")

    def location(self, location_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        encoded = quote(location_id, safe="")
        return self._get_json(f"/collections/observations/locations/{encoded}", params=params)

    def area(self, bbox: tuple[float, float, float, float], params: dict[str, Any]) -> dict[str, Any]:
        query = dict(params)
        query["coords"] = (
            f"POLYGON(({bbox[0]} {bbox[1]},"
            f"{bbox[2]} {bbox[1]},"
            f"{bbox[2]} {bbox[3]},"
            f"{bbox[0]} {bbox[3]},"
            f"{bbox[0]} {bbox[1]}))"
        )
        return self._get_json("/collections/observations/area", params=query)

    def position(self, lon: float, lat: float, params: dict[str, Any]) -> dict[str, Any]:
        query = dict(params)
        query["coords"] = f"POINT({lon} {lat})"
        return self._get_json("/collections/observations/position", params=query)

    #def observation_records(
        #self,
        #*,
        #start: dt.datetime,
        #end: dt.datetime,
        #parameters: list[str],
        #bbox: tuple[float, float, float, float] | None = None,
        #location_id: str | None = None,
        #level: str | None = None,
    #) -> StationObservations:
        #params: dict[str, Any] = {
            #"datetime": f"{start.astimezone(dt.timezone.utc).isoformat()}/{end.astimezone(dt.timezone.utc).isoformat()}",
            #"parameter-name": ",".join(f"{parameter}:*:*:*" for parameter in parameters),
            #"f": "CoverageJSON",
        #}
        #if level:
            #params["level"] = level

        #if location_id:
            #payload = self.location(location_id, params=params)
        #elif bbox:
            #payload = self.area(bbox, params=params)
        #else:
            #raise ValueError("Provide bbox or location_id for an E-SOH query.")

        #records = coveragejson_to_records(payload)
        #self._attach_location_metadata(records, payload)
        #return StationObservations(records)

    def observation_records(
        self,
        *,
        start: dt.datetime,
        end: dt.datetime,
        parameters: list[str],
        bbox: tuple[float, float, float, float] | None = None,
        location_id: str | None = None,
        level: str | None = None,
        height: float | None = None,
        statistic: str | None = None,
        period: str | None = None,
    ) -> StationObservations:

        selectors = []

        for parameter in parameters:
            height_selector = "*" if height is None else str(height)
            statistic_selector = "*" if statistic is None else statistic
            period_selector = "*" if period is None else period

            selectors.append(
                f"{parameter}:"
                f"{height_selector}:"
                f"{statistic_selector}:"
                f"{period_selector}"
            )

        params: dict[str, Any] = {
            "datetime": (
                f"{start.astimezone(dt.timezone.utc).isoformat()}/"
                f"{end.astimezone(dt.timezone.utc).isoformat()}"
            ),
            "parameter-name": ",".join(selectors),
            "f": "CoverageJSON",
        }

        if level:
            params["level"] = level

        if location_id:
            payload = self.location(location_id, params=params)
        elif bbox:
            payload = self.area(bbox, params=params)
        else:
            raise ValueError("Provide bbox or location_id for an E-SOH query.")

        records = coveragejson_to_records(payload)

        self._normalise_records(records)
        self._attach_location_metadata(records, payload)

        return StationObservations(records)
    

    @staticmethod
    def _normalise_records(records: list[dict[str, Any]]) -> None:
        """Normalise E-SOH-specific missing values and parameter metadata."""

        missing_values = {-32767.0, -32766.0}

        for record in records:
            value = record.get("value")

            if isinstance(value, (int, float)):
                value = float(value)

                if value in missing_values or not math.isfinite(value):
                    record["value"] = None

            parameter = record.get("parameter")

            if isinstance(parameter, str):
                parts = parameter.split(":")

                if len(parts) == 4:
                    variable, height, statistic, period = parts

                    record["variable"] = variable

                    try:
                        record["height_m"] = float(height)
                    except ValueError:
                        record["height_m"] = None

                    record["statistic"] = statistic
                    record["period"] = period
       

    @staticmethod
    def _attach_location_metadata(
        records: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> None:
        """Attach common station metadata when present in EDR output."""

        properties = payload.get("properties", {})

        if isinstance(properties, dict):
            for record in records:
                for key in (
                    "station_name",
                    "location_id",
                    "wigos_id",
                    "name",
                ):
                    if key in properties and key not in record:
                        record[key] = properties[key]

        refs = payload.get("domain", {}).get("referencing", [])

        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue

                system = ref.get("system", {})

                if (
                    system.get("type") == "GeographicCRS"
                    and ref.get("coordinates")
                ):
                    coordinates = ref["coordinates"]

                    if len(coordinates) >= 2:
                        for record in records:
                            record.setdefault(
                                "longitude",
                                coordinates[0],
                            )
                            record.setdefault(
                                "latitude",
                                coordinates[1],
                            )
    #@staticmethod
    #def _attach_location_metadata(records: list[dict[str, Any]], payload: dict[str, Any]) -> None:
     #   """Attach common station metadata when present in EDR output."""

      #  properties = payload.get("properties", {})
       # if isinstance(properties, dict):
        #    for record in records:
         #       for key in ("station_name", "location_id", "wigos_id", "name"):
          #          if key in properties and key not in record:
           #             record[key] = properties[key]

        ## CoverageJSON may provide location metadata through the domain
        ## referencing object rather than top-level properties. Preserve the
        ## metadata where it is easily identifiable without imposing one schema.
        #refs = payload.get("domain", {}).get("referencing", [])
        #if isinstance(refs, list):
         #   for ref in refs:
          #      if not isinstance(ref, dict):
           #         continue
            #    system = ref.get("system", {})
             #   if system.get("type") == "GeographicCRS" and ref.get("coordinates"):
              #      coordinates = ref.get("coordinates")
               #     if len(coordinates) >= 2:
                #        for record in records:
                 #           record.setdefault("longitude", coordinates[0])
                  #          record.setdefault("latitude", coordinates[1])

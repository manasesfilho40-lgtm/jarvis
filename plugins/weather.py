import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_weather")


class WeatherPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="weather",
                version="1.0.0",
                description="Weather information - current, forecast via free APIs",
            )
        super().__init__(manifest)
        self._default_city: str = ""
        self._api_key: str = ""
        self._cache: dict = {}
        self._cache_ttl: int = 600

    async def on_load(self):
        self._default_city = self.config.get("default_city", "São Paulo")
        self._api_key = self.config.get("openweather_key", "")
        self._cache_ttl = int(self.config.get("cache_ttl", 600))
        logger.info(f"Weather plugin loaded (default city: {self._default_city})")

    async def on_unload(self):
        logger.info("Weather plugin unloaded")

    def _get_cached(self, key: str) -> Optional[dict]:
        if key in self._cache:
            entry = self._cache[key]
            if (datetime.now() - entry["time"]).total_seconds() < self._cache_ttl:
                return entry["data"]
        return None

    def _set_cache(self, key: str, data: dict):
        self._cache[key] = {"data": data, "time": datetime.now()}

    async def get_coordinates(self, city: str) -> Optional[tuple]:
        try:
            import requests
            url = "https://geocoding-api.open-meteo.com/v1/search"
            params = {"name": city, "count": 1, "language": "pt", "format": "json"}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                return (r["latitude"], r["longitude"], r.get("name", city), r.get("country", ""))
            return None
        except Exception as e:
            logger.error(f"Geocoding failed for {city}: {e}")
            return None

    async def get_current_weather(self, city: str = "") -> Optional[dict]:
        city = city or self._default_city
        cache_key = f"current_{city}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        coords = await self.get_coordinates(city)
        if not coords:
            return {"error": f"City '{city}' not found"}
        lat, lon, name, country = coords
        try:
            import requests
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,pressure_msl",
                "timezone": "auto",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})
            weather_code = current.get("weather_code", 0)
            result = {
                "city": name,
                "country": country,
                "temperature_c": current.get("temperature_2m"),
                "feels_like_c": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "pressure_hpa": current.get("pressure_msl"),
                "precipitation_mm": current.get("precipitation"),
                "condition": self._code_to_condition(weather_code),
                "condition_code": weather_code,
                "updated": current.get("time", ""),
            }
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return {"error": str(e)}

    async def get_forecast(self, city: str = "", days: int = 7) -> Optional[dict]:
        city = city or self._default_city
        cache_key = f"forecast_{city}_{days}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        coords = await self.get_coordinates(city)
        if not coords:
            return {"error": f"City '{city}' not found"}
        lat, lon, name, country = coords
        try:
            import requests
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max",
                "timezone": "auto",
                "forecast_days": days,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            daily = data.get("daily", {})
            days_data = []
            dates = daily.get("time", [])
            t_max = daily.get("temperature_2m_max", [])
            t_min = daily.get("temperature_2m_min", [])
            codes = daily.get("weather_code", [])
            precip = daily.get("precipitation_sum", [])
            wind = daily.get("wind_speed_10m_max", [])
            for i in range(len(dates)):
                days_data.append({
                    "date": dates[i] if i < len(dates) else "",
                    "temp_max": t_max[i] if i < len(t_max) else None,
                    "temp_min": t_min[i] if i < len(t_min) else None,
                    "condition": self._code_to_condition(codes[i]) if i < len(codes) else "",
                    "precipitation_mm": precip[i] if i < len(precip) else 0,
                    "wind_max_kmh": wind[i] if i < len(wind) else 0,
                })
            result = {"city": name, "country": country, "days": days_data}
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Forecast fetch failed: {e}")
            return {"error": str(e)}

    def _code_to_condition(self, code: int) -> str:
        conditions = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            56: "Light freezing drizzle", 57: "Dense freezing drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            66: "Light freezing rain", 67: "Heavy freezing rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            85: "Slight snow showers", 86: "Heavy snow showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        return conditions.get(code, f"Unknown ({code})")


manifest = PluginManifest(
    name="weather",
    version="1.0.0",
    description="Weather information - current, forecast via free Open-Meteo API",
)

"""P10 — Garmin health data sync for Sunny.

Reads sleep, heart rate, steps, and other health metrics
from Garmin Connect.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class HealthMetric:
    """A single health metric data point."""
    metric: str  # sleep_duration, steps, heart_rate, etc.
    value: float
    unit: str
    timestamp: datetime
    source: str = "garmin"


@dataclass
class HealthInsight:
    """A derived insight from health data."""
    type: str  # sleep_debt, high_heart_rate, low_activity, etc.
    severity: str  # low | medium | high
    message: str
    value: Optional[float] = None
    recommendation: str = ""


class GarminSync:
    """Syncs health data from Garmin Connect."""

    def __init__(
        self,
        vault: Path,
        garmin_email: str = "",
        garmin_password: str = "",
    ) -> None:
        self.vault = vault
        self.garmin_email = garmin_email
        self.garmin_password = garmin_password
        self._cache_path = vault / "data" / "garmin_cache.json"

    def is_configured(self) -> bool:
        return bool(self.garmin_email and self.garmin_password)

    def fetch_sleep_data(
        self,
        days: int = 7,
        start_date: Optional[datetime] = None,
    ) -> list[dict]:
        """Fetch sleep data from Garmin. Returns cached if offline."""
        if not self.is_configured():
            log.warning("Garmin not configured, returning cached sleep data")
            return self._load_cache("sleep", days)

        try:
            return self._fetch_from_garmin("sleep", days, start_date)
        except Exception as e:
            log.warning("Garmin fetch failed, using cache: %s", e)
            return self._load_cache("sleep", days)

    def fetch_steps_data(
        self,
        days: int = 30,
    ) -> list[dict]:
        """Fetch step count data."""
        if not self.is_configured():
            return self._load_cache("steps", days)

        try:
            return self._fetch_from_garmin("steps", days, None)
        except Exception as e:
            log.warning("Garmin steps fetch failed, using cache: %s", e)
            return self._load_cache("steps", days)

    def fetch_heart_rate_data(
        self,
        days: int = 7,
    ) -> list[dict]:
        """Fetch heart rate data (resting avg, zones)."""
        if not self.is_configured():
            return self._load_cache("heart_rate", days)

        try:
            return self._fetch_from_garmin("heart_rate", days, None)
        except Exception as e:
            log.warning("Garmin HR fetch failed, using cache: %s", e)
            return self._load_cache("heart_rate", days)

    def _fetch_from_garmin(
        self,
        metric: str,
        days: int,
        start_date: Optional[datetime],
    ) -> list[dict]:
        """Fetch data from Garmin Connect API."""
        try:
            from garminconnect import Garmin
        except ImportError:
            log.warning("garminconnect package not installed")
            return []

        client = Garmin(
            self.garmin_email,
            self.garmin_password,
            is_upload_session=False,
        )

        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
        end_date = datetime.now(timezone.utc)

        results = []

        if metric == "sleep":
            try:
                sleep_data = client.get_sleep_stats(start_date, end_date)
                for entry in sleep_data:
                    results.append({
                        "date": entry.get("dateOfSleep", ""),
                        "sleep_minutes": entry.get("minutesAsleep", 0),
                        "sleep_score": entry.get("sleepScore", 0),
                        "resting_heart_rate": entry.get("restingHeartRate", 0),
                        "rem_sleep_minutes": entry.get("remMinutes", 0),
                        "deep_sleep_minutes": entry.get("deepSleepMinutes", 0),
                    })
            except Exception as e:
                log.error("Failed to fetch sleep stats: %s", e)

        elif metric == "steps":
            try:
                steps_data = client.get_steps_summary(
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                )
                for entry in steps_data:
                    results.append({
                        "date": entry.get("calendarDate", ""),
                        "steps": entry.get("stepTotal", 0),
                        "active_calories": entry.get("activeCalories", 0),
                    })
            except Exception as e:
                log.error("Failed to fetch steps: %s", e)

        elif metric == "heart_rate":
            try:
                hr_data = client.get_heart_rate_timeseries(
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                )
                for entry in hr_data:
                    results.append({
                        "timestamp": entry.get("startTimeEpoch", ""),
                        "bpm": entry.get("bpm", 0),
                    })
            except Exception as e:
                log.error("Failed to fetch HR: %s", e)

        self._save_cache(metric, results)
        return results

    def _load_cache(self, metric: str, days: int) -> list[dict]:
        """Load cached health data."""
        if not self._cache_path.exists():
            return []
        try:
            import json
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return data.get(metric, [])
        except Exception as e:
            log.error("Failed to load Garmin cache: %s", e)
            return []

    def _save_cache(self, metric: str, data: list[dict]) -> None:
        """Save health data to cache."""
        data_dir = self._cache_path.parent
        data_dir.mkdir(parents=True, exist_ok=True)

        import json
        cache = {}
        if self._cache_path.exists():
            try:
                cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        cache[metric] = data
        self._cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    def clear_cache(self) -> None:
        if self._cache_path.exists():
            self._cache_path.unlink()

"""P10 — Health insights engine.

Analyzes health data from Garmin to detect anomalies
and generate actionable recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class HealthInsight:
    """A derived health insight."""
    type: str
    severity: str  # low | medium | high
    message: str
    value: Optional[float] = None
    recommendation: str = ""


class HealthInsights:
    """Analyzes health metrics and generates insights."""

    # Default thresholds
    SLEEP_MINUTES_LOW = 360  # 6 hours
    SLEEP_MINUTES_HIGH = 540  # 9 hours
    STEPS_DAILY_MIN = 3000
    STEPS_DAILY_HIGH = 10000
    HEART_RATE_RESTING_LOW = 50
    HEART_RATE_RESTING_HIGH = 100

    def __init__(self, vault: Path) -> None:
        self.vault = vault
        self._history: list[HealthInsight] = []

    @property
    def history(self) -> list[HealthInsight]:
        return self._history

    def analyze_sleep(self, sleep_data: list[dict]) -> list[HealthInsight]:
        """Analyze sleep data and return insights."""
        insights: list[HealthInsight] = []

        if not sleep_data:
            return insights

        total_sleep = 0
        count = 0
        recent_nights = sleep_data[-7:] if len(sleep_data) > 7 else sleep_data

        for entry in recent_nights:
            minutes = entry.get("sleep_minutes", entry.get("sleepMinutes", 0))
            score = entry.get("sleep_score", 0)
            total_sleep += minutes
            count += 1

            if minutes < self.SLEEP_MINUTES_LOW:
                insights.append(HealthInsight(
                    type="sleep_debt",
                    severity="high",
                    message=f"Poor sleep: {minutes} minutes ({minutes//60}h{minutes%60}m)",
                    value=float(minutes),
                    recommendation="Aim for 7-9 hours of sleep. Consider reducing screen time before bed.",
                ))
            elif score < 50:
                insights.append(HealthInsight(
                    type="poor_sleep_quality",
                    severity="medium",
                    message=f"Low sleep quality score: {score}",
                    value=float(score),
                    recommendation="Try maintaining a consistent sleep schedule.",
                ))

        if count > 0:
            avg_sleep = total_sleep / count
            if avg_sleep < self.SLEEP_MINUTES_LOW:
                insights.append(HealthInsight(
                    type="chronic_sleep_debt",
                    severity="high",
                    message=f"Average sleep over 7 days: {avg_sleep:.0f} minutes ({avg_sleep//60:.0f}h{(avg_sleep%60):.0f}m)",
                    value=avg_sleep,
                    recommendation="Consistently low sleep. Review your evening routine.",
                ))

        self._history.extend(insights)
        return insights

    def analyze_steps(self, steps_data: list[dict]) -> list[HealthInsight]:
        """Analyze step data and return insights."""
        insights: list[HealthInsight] = []

        if not steps_data:
            return insights

        recent = steps_data[-7:] if len(steps_data) > 7 else steps_data
        total_steps = 0

        for entry in recent:
            steps = entry.get("steps", entry.get("stepTotal", 0))
            total_steps += steps

            if steps < self.STEPS_DAILY_MIN:
                insights.append(HealthInsight(
                    type="low_activity",
                    severity="medium",
                    message=f"Low activity day: {steps} steps",
                    value=float(steps),
                    recommendation="Try to walk at least 3000 steps per day.",
                ))
            elif steps < 5000:
                insights.append(HealthInsight(
                    type="below_average_activity",
                    severity="low",
                    message=f"Below average: {steps} steps",
                    value=float(steps),
                    recommendation="Consider adding short walks to your routine.",
                ))

        return insights

    def analyze_heart_rate(self, hr_data: list[dict]) -> list[HealthInsight]:
        """Analyze heart rate data and return insights."""
        insights: list[HealthInsight] = []

        if not hr_data:
            return insights

        resting_heart_rates = [
            d.get("restingHeartRate", d.get("resting_heart_rate", 0))
            for d in hr_data
            if d.get("restingHeartRate", d.get("resting_heart_rate", 0)) > 0
        ]

        if resting_heart_rates:
            avg_hr = sum(resting_heart_rates) / len(resting_heart_rates)

            if avg_hr > self.HEART_RATE_RESTING_HIGH:
                insights.append(HealthInsight(
                    type="high_resting_hr",
                    severity="high",
                    message=f"Elevated resting heart rate: {avg_hr:.0f} bpm",
                    value=avg_hr,
                    recommendation="High resting HR can indicate stress, illness, or overtraining. Consider resting.",
                ))
            elif avg_hr < self.HEART_RATE_RESTING_LOW:
                insights.append(HealthInsight(
                    type="low_resting_hr",
                    severity="low",
                    message=f"Low resting heart rate: {avg_hr:.0f} bpm",
                    value=avg_hr,
                    recommendation="Low resting HR is typically a sign of good fitness.",
                ))

        # Check for recent spikes
        recent = hr_data[-3:] if len(hr_data) > 3 else hr_data
        for entry in recent:
            bpm = entry.get("bpm", 0)
            if bpm > 100 and bpm < 200:
                insights.append(HealthInsight(
                    type="high_heart_rate",
                    severity="medium",
                    message=f"Elevated heart rate: {bpm} bpm",
                    value=float(bpm),
                    recommendation="Check if this was during exercise or stress.",
                ))

        return insights

    def get_health_summary(self) -> str:
        """Generate a health summary from all insights."""
        if not self._history:
            return "No health data analyzed yet."

        by_severity = {"high": [], "medium": [], "low": []}
        for insight in self._history:
            by_severity.setdefault(insight.severity, []).append(insight.message)

        lines = ["# Health Summary", ""]

        if by_severity["high"]:
            lines.append("## High Priority", "")
            for msg in by_severity["high"]:
                lines.append(f"⚠️ {msg}")

        if by_severity["medium"]:
            lines.append("## Medium Priority", "")
            for msg in by_severity["medium"]:
                lines.append(f"⚡ {msg}")

        if by_severity["low"]:
            lines.append("## Low Priority", "")
            for msg in by_severity["low"]:
                lines.append(f"ℹ️ {msg}")

        return "\n".join(lines)

    def clear_history(self) -> None:
        self._history.clear()

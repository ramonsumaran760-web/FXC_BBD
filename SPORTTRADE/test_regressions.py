import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from api.v1.routes.predictions import mundial_en_vivo
from live import LatencyTracker
from main import health


class RouteRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_mundial_returns_configured_odds_data(self):
        match = {
            "id": "USA-AUS",
            "date": datetime.now(timezone.utc).isoformat(),
            "live": False,
            "done": False,
            "l": "USA",
            "v": "Australia",
            "bl": 1.6,
            "be": 4.3,
            "bv": 5.4,
        }

        with patch("services.odds_api._get_key", return_value="configured"), patch(
            "services.odds_api.fetch_full_world_cup_data",
            new=AsyncMock(return_value=[match]),
        ):
            result = await mundial_en_vivo()

        self.assertEqual(result["source"], "the_odds_api")
        self.assertEqual(result["matches"][0]["id"], "USA-AUS")

    async def test_health_uses_live_component_contracts(self):
        result = await health()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["circuit_breaker"], "OPERATIONAL")
        self.assertIn("latencia_p95_ms", result)


class LatencyTrackerRegressionTests(unittest.TestCase):
    def test_statistics_and_spanish_alias(self):
        tracker = LatencyTracker()
        with patch("live.time.time", return_value=1000.0):
            tracker.registrar("test", 999.9)
            tracker.registrar("test", 999.0)

        stats = tracker.estadisticas()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["p95_ms"], 1000)
        self.assertEqual(stats["p99_ms"], 1000)
        self.assertEqual(stats["cumplimiento_pct"], 50.0)
        self.assertEqual(tracker.sla_cumplimiento_pct(), 50.0)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import main


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.places = [
            {"title": "출발", "lat": 37.0, "lng": 127.0},
            {"title": "먼 곳", "lat": 37.2, "lng": 127.2},
            {"title": "가까운 곳", "lat": 37.01, "lng": 127.01},
        ]

    async def test_schedule_keeps_first_stop_and_optimizes_the_rest(self):
        result = await main.schedule(main.ScheduleReq(cards=self.places))

        self.assertEqual([item["title"] for item in result["items"]], ["출발", "가까운 곳", "먼 곳"])
        self.assertGreater(result["total_distance_m"], 0)
        self.assertIsNone(result["items"][0]["leg_distance_m"])

    async def test_weather_and_crowding_are_handled_together(self):
        indoor = [{
            "title": "실내 미술관", "addr": "서울", "dist": 300,
            "lat": 37.57, "lng": 126.98, "contentid": "1",
            "contenttypeid": "14", "img": "",
        }]
        request = main.ChatReq(message="너무 붐비고 비도 와", region="서울 종로구")

        with patch.object(main, "nearby_raw", AsyncMock(return_value=indoor)), patch.object(
            main, "weather", AsyncMock(return_value={"label": "맑음"})
        ):
            result = await main.chat(request)

        self.assertEqual(result["type"], "weather_detour")
        self.assertIn("현장 상황을 우선", result["text"])
        self.assertEqual(result["cards"][0]["title"], "실내 미술관")

    def test_unknown_region_is_rejected_instead_of_using_wrong_coordinates(self):
        with self.assertRaises(HTTPException) as raised:
            main.resolve_location("없는 지역", 37.5, 127.0)

        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()

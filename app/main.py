"""RePlan API: a context-aware travel replanning demo for Vercel."""

from __future__ import annotations

import datetime as dt
import logging
import math
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

TOUR_KEY = unquote(os.getenv("TOUR_API_KEY", "").strip())
TOUR_BASE = "https://apis.data.go.kr/B551011/KorService2"
METEO_BASE = "https://api.open-meteo.com/v1/forecast"
KST = ZoneInfo("Asia/Seoul")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
logger = logging.getLogger("replan")

app = FastAPI(title="RePlan", version="2.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

REGION_CENTERS: tuple[tuple[str, float, float], ...] = (
    ("서울 종로구", 37.5735, 126.9790),
    ("서울 중구", 37.5641, 126.9979),
    ("서울 강남구", 37.5172, 127.0473),
    ("부산 해운대", 35.1631, 129.1635),
    ("제주 서귀포", 33.2541, 126.5601),
    ("강릉", 37.7519, 128.8761),
    ("경주", 35.8562, 129.2247),
    ("전주", 35.8242, 127.1480),
    ("여수", 34.7604, 127.6622),
    ("속초", 38.2070, 128.5918),
    ("춘천", 37.8813, 127.7298),
    ("서울", 37.5665, 126.9780),
    ("부산", 35.1796, 129.0756),
    ("대구", 35.8714, 128.6014),
    ("인천", 37.4563, 126.7052),
    ("광주", 35.1595, 126.8526),
    ("대전", 36.3504, 127.3845),
    ("울산", 35.5384, 129.3114),
    ("세종", 36.4800, 127.2890),
    ("제주", 33.4996, 126.5312),
)

STYLE_CONTENT_TYPES = {
    "문화·역사": (14, 12),
    "카페·휴식": (39, 12),
    "자연·산책": (12, 28),
    "맛집": (39,),
}


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    lat: float = Field(default=37.5665, ge=-90, le=90)
    lng: float = Field(default=126.9780, ge=-180, le=180)
    region: str = Field(default="", max_length=80)
    travel_date: Optional[dt.date] = None
    style: str = Field(default="문화·역사", max_length=30)
    exclude_ids: list[str] = Field(default_factory=list)


class ScheduleReq(BaseModel):
    cards: list[dict[str, Any]] = Field(default_factory=list)
    start_hour: int = Field(default=10, ge=0, le=23)


async def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("External API timeout: %s", url)
        raise HTTPException(504, "관광정보 서버의 응답이 늦어지고 있습니다.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("External API failure for %s: %s", url, type(exc).__name__)
        raise HTTPException(502, "외부 관광정보를 불러오지 못했습니다.") from exc
    if not isinstance(data, dict):
        raise HTTPException(502, "외부 관광정보의 응답 형식이 올바르지 않습니다.")
    return data


def rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        header = data["response"]["header"]
        if str(header.get("resultCode", "0000")) != "0000":
            raise HTTPException(502, header.get("resultMsg", "TourAPI 요청에 실패했습니다."))
        raw = data["response"]["body"]["items"]
        if not raw:
            return []
        item = raw.get("item", [])
        return item if isinstance(item, list) else [item]
    except HTTPException:
        raise
    except (KeyError, TypeError) as exc:
        raise HTTPException(502, "TourAPI 응답을 해석하지 못했습니다.") from exc


async def tour(path: str, **params: Any) -> list[dict[str, Any]]:
    if not TOUR_KEY:
        raise HTTPException(503, "TOUR_API_KEY가 설정되지 않았습니다.")
    base = {
        "serviceKey": TOUR_KEY,
        "MobileOS": "ETC",
        "MobileApp": "RePlan",
        "_type": "json",
    }
    return rows(await get_json(f"{TOUR_BASE}/{path}", {**base, **params}))


def convert(item: dict[str, Any]) -> dict[str, Any]:
    try:
        distance = round(float(item.get("dist", 0)))
    except (TypeError, ValueError):
        distance = 0
    image = item.get("firstimage") or item.get("firstimage2") or ""
    if image.startswith("http://"):
        image = "https://" + image.removeprefix("http://")
    return {
        "title": item.get("title") or "관광지",
        "addr": item.get("addr1") or "",
        "img": image,
        "dist": distance,
        "lat": item.get("mapy"),
        "lng": item.get("mapx"),
        "contentid": str(item.get("contentid") or ""),
        "contenttypeid": str(item.get("contenttypeid") or ""),
    }


def resolve_location(region: str, lat: float, lng: float) -> tuple[float, float, str]:
    normalized = " ".join(region.strip().split())
    for name, center_lat, center_lng in REGION_CENTERS:
        if normalized and (name in normalized or normalized in name):
            return center_lat, center_lng, name
    if normalized:
        supported = ", ".join(name for name, _, _ in REGION_CENTERS[:11])
        raise HTTPException(422, f"아직 지원하지 않는 지역입니다. 지원 지역: {supported}")
    return lat, lng, "기본 위치"


def estimate_time(travel_date: Optional[dt.date]) -> dt.datetime:
    now = dt.datetime.now(KST)
    if travel_date and travel_date != now.date():
        return dt.datetime.combine(travel_date, dt.time(13, 0), tzinfo=KST)
    return now


def estimated_crowding(distance: int, when: dt.datetime) -> float:
    value = 28.0 + (20 if when.weekday() >= 5 else 0) + (18 if 11 <= when.hour <= 16 else 0)
    value += min(12, max(0, (2500 - distance) / 250))
    return round(min(95, value), 1)


def enrich(items: list[dict[str, Any]], travel_date: Optional[dt.date] = None) -> list[dict[str, Any]]:
    when = estimate_time(travel_date)
    for place in items:
        place["congestion"] = estimated_crowding(place.get("dist", 0), when)
        place["congestion_basis"] = "요일·시간대·거리 기반 예상치"
    return items


def unique(items: list[dict[str, Any]], excluded: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen = set(excluded)
    for place in items:
        content_id = place.get("contentid")
        if content_id and content_id not in seen:
            seen.add(content_id)
            result.append(place)
    return result


def coordinates(place: dict[str, Any]) -> Optional[tuple[float, float]]:
    try:
        return float(place["lat"]), float(place["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def distance_m(left: dict[str, Any], right: dict[str, Any]) -> Optional[int]:
    start = coordinates(left)
    end = coordinates(right)
    if not start or not end:
        return None
    lat1, lng1 = map(math.radians, start)
    lat2, lng2 = map(math.radians, end)
    dlat, dlng = lat2 - lat1, lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return round(6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))


def optimize_route(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first selected stop, then visit the nearest remaining stop."""
    if len(places) < 3:
        return places
    route = [places[0]]
    remaining = places[1:]
    while remaining:
        current = route[-1]
        next_index = min(
            range(len(remaining)),
            key=lambda index: distance_m(current, remaining[index]) or 10**12,
        )
        route.append(remaining.pop(next_index))
    return route


def weather_name(code: int) -> str:
    if code in (0, 1): return "맑음"
    if code in (2, 3): return "구름 많음"
    if code in (45, 48): return "안개"
    if code in (51, 53, 55, 56, 57): return "이슬비"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "비"
    if code in (71, 73, 75, 77, 85, 86): return "눈"
    if code in (95, 96, 99): return "천둥·번개"
    return "날씨 정보 없음"


async def nearby_raw(lat: float, lng: float, radius: int, content_type: int, count: int = 20) -> list[dict[str, Any]]:
    items = await tour(
        "locationBasedList2", mapX=lng, mapY=lat,
        radius=max(500, min(radius, 20_000)), contentTypeId=content_type,
        arrange="E", numOfRows=count, pageNo=1,
    )
    return [convert(item) for item in items]


async def recommendations(lat: float, lng: float, style: str, travel_date: Optional[dt.date], excluded: set[str], radius: int = 6000) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for content_type in STYLE_CONTENT_TYPES.get(style, (12, 14)):
        candidates.extend(await nearby_raw(lat, lng, radius, content_type, 16))
    return enrich(unique(candidates, excluded), travel_date)[:8]


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "tour_api_configured": bool(TOUR_KEY), "weather_api": "Open-Meteo", "version": app.version}


@app.get("/api/weather")
async def weather(lat: float = 37.5665, lng: float = 126.9780) -> dict[str, Any]:
    current = (await get_json(METEO_BASE, {
        "latitude": lat, "longitude": lng,
        "current": "temperature_2m,precipitation,rain,weather_code,wind_speed_10m",
        "timezone": "Asia/Seoul",
    })).get("current", {})
    code = int(current.get("weather_code", -1))
    return {
        "temperature": current.get("temperature_2m"), "precipitation": current.get("precipitation"),
        "rain": current.get("rain"), "weather_code": code, "label": weather_name(code),
        "wind_speed": current.get("wind_speed_10m"),
    }


@app.get("/api/nearby")
async def nearby(lat: float = 37.5665, lng: float = 126.9780, radius: int = 3000, content_type: int = 12) -> list[dict[str, Any]]:
    return enrich((await nearby_raw(lat, lng, radius, content_type))[:10])


@app.get("/api/detail/{content_id}")
async def detail(content_id: str) -> dict[str, Any]:
    items = await tour("detailCommon2", contentId=content_id, defaultYN="Y", firstImageYN="Y", overviewYN="Y", addrinfoYN="Y", mapinfoYN="Y", numOfRows=1, pageNo=1)
    return items[0] if items else {}


@app.post("/api/schedule")
async def schedule(req: ScheduleReq) -> dict[str, Any]:
    selected = [item for item in req.cards if item.get("title")][:6]
    if not selected:
        raise HTTPException(422, "일정에 담긴 장소가 없습니다.")
    selected = optimize_route(selected)
    plan = []
    total_distance = 0
    for index, place in enumerate(selected):
        total_minutes = req.start_hour * 60 + index * 120
        hour, minute = divmod(total_minutes, 60)
        leg_distance = distance_m(selected[index - 1], place) if index else None
        total_distance += leg_distance or 0
        plan.append({
            "time": f"{hour % 24:02d}:{minute:02d}",
            "title": place.get("title"),
            "addr": place.get("addr"),
            "contentid": place.get("contentid"),
            "leg_distance_m": leg_distance,
        })
    return {
        "title": "이동 거리를 줄인 재설계 일정",
        "text": "첫 장소는 유지하고 이후 장소를 가까운 순서로 재배치했습니다.",
        "total_distance_m": total_distance,
        "items": plan,
    }


@app.post("/api/chat")
async def chat(req: ChatReq) -> dict[str, Any]:
    message = req.message.lower()
    excluded = {str(item) for item in req.exclude_ids}
    lat, lng, applied_region = resolve_location(req.region, req.lat, req.lng)
    is_crowded = any(word in message for word in ("혼잡", "붐비", "사람 많", "복잡", "줄이 길"))
    is_weather = any(word in message for word in ("비", "우천", "눈", "날씨", "더워", "추워", "폭염", "한파"))
    is_schedule = any(word in message for word in ("일정", "동선", "코스", "다시 짜", "재설계"))

    if is_crowded and is_weather:
        current_weather = None
        try:
            current_weather = await weather(lat, lng)
        except HTTPException:
            pass
        indoor = unique(await nearby_raw(lat, lng, 9000, 14, 30), excluded)
        alternatives = sorted(
            enrich(indoor, req.travel_date),
            key=lambda item: (item["congestion"], item["dist"]),
        )[:6]
        observed = f" 참고 관측 날씨는 {current_weather['label']}입니다." if current_weather else ""
        return {
            "type": "weather_detour",
            "title": "우천·혼잡 동시 대응 추천",
            "text": f"말씀해주신 현장 상황을 우선 반영해 {applied_region}의 실내 장소 중 예상 혼잡 점수가 낮은 대안을 찾았어요.{observed}",
            "weather": current_weather,
            "cards": alternatives,
            "applied_region": applied_region,
        }

    if is_crowded:
        candidates: list[dict[str, Any]] = []
        for content_type in (12, 14, 15, 28):
            candidates.extend(await nearby_raw(lat, lng, 9000, content_type, 20))
        alternatives = unique(candidates, excluded)
        alternatives = sorted(enrich(alternatives, req.travel_date), key=lambda item: (item["congestion"], item["dist"]))[:6]
        return {"type": "detour", "title": "혼잡 우회 추천", "text": f"{applied_region}에서 기존 장소를 제외하고 예상 혼잡 점수가 낮은 대안을 찾았어요.", "cards": alternatives, "applied_region": applied_region}

    if is_weather:
        current_weather = None
        try:
            current_weather = await weather(lat, lng)
        except HTTPException:
            pass
        indoor = unique(await nearby_raw(lat, lng, 8000, 14, 20), excluded)[:6]
        observed = f" 참고 관측 날씨는 {current_weather['label']}입니다." if current_weather else ""
        return {"type": "weather", "title": "날씨 대응 추천", "text": f"말씀해주신 현장 날씨를 우선 반영해 {applied_region}의 실내 문화시설을 찾았어요.{observed}", "weather": current_weather, "cards": enrich(indoor, req.travel_date), "applied_region": applied_region}

    cards = await recommendations(lat, lng, req.style, req.travel_date, excluded)
    text = f"{applied_region}의 선택 장소를 바탕으로 일정을 다시 구성할 수 있어요. 먼저 원하는 장소를 담아주세요." if is_schedule else f"{applied_region}에서 ‘{req.style}’ 취향에 맞는 장소를 찾았어요."
    return {"type": "schedule_candidates" if is_schedule else "nearby", "title": "일정 후보" if is_schedule else "주변 관광지 추천", "text": text, "cards": cards[:6], "applied_region": applied_region}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

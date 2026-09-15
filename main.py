"""RePlan: reliable contest demo backend.
Uses Korea Tourism Organization TourAPI + Open-Meteo. No LLM key is required.
"""
import os, datetime
from urllib.parse import unquote
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

TOUR_KEY = unquote(os.getenv("TOUR_API_KEY", "").strip())
TOUR_BASE = "https://apis.data.go.kr/B551011/KorService2"
METEO = "https://api.open-meteo.com/v1/forecast"
app = FastAPI(title="RePlan", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    lat: float = 37.5665
    lng: float = 126.9780
    exclude_ids: list[str] = []

class ScheduleReq(BaseModel):
    cards: list[dict[str, Any]] = []
    start_hour: int = Field(default=10, ge=0, le=23)

async def get_json(url: str, params: dict):
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"외부 API 호출 실패: {type(e).__name__}")

def rows(data: dict) -> list[dict]:
    try:
        raw = data["response"]["body"]["items"]
        if not raw: return []
        item = raw.get("item", [])
        return item if isinstance(item, list) else [item]
    except (KeyError, TypeError):
        return []

async def tour(path: str, **params):
    if not TOUR_KEY:
        raise HTTPException(503, "TOUR_API_KEY가 설정되지 않았습니다.")
    base = {"serviceKey": TOUR_KEY, "MobileOS": "ETC", "MobileApp": "RePlan", "_type": "json"}
    return rows(await get_json(f"{TOUR_BASE}/{path}", {**base, **params}))

def convert(item: dict) -> dict:
    try: distance = round(float(item.get("dist", 0)))
    except (TypeError, ValueError): distance = 0
    return {"title": item.get("title", "관광지"), "addr": item.get("addr1", ""),
            "img": item.get("firstimage", ""), "dist": distance,
            "lat": item.get("mapy"), "lng": item.get("mapx"),
            "contentid": str(item.get("contentid", "")),
            "contenttypeid": str(item.get("contenttypeid", ""))}

def estimated_crowding(distance: int, now=None) -> float:
    now = now or datetime.datetime.now()
    value = 28.0 + (20 if now.weekday() >= 5 else 0) + (18 if 11 <= now.hour <= 16 else 0)
    value += min(12, max(0, (2500 - distance) / 250))
    return round(min(95, value), 1)

def enrich(items: list[dict]) -> list[dict]:
    for p in items: p["congestion"] = estimated_crowding(p.get("dist", 0))
    return items

def unique(items: list[dict], excluded: set[str]) -> list[dict]:
    result, seen = [], set(excluded)
    for p in items:
        cid = p.get("contentid")
        if cid and cid not in seen:
            seen.add(cid); result.append(p)
    return result

def weather_name(code: int) -> str:
    if code in (0, 1): return "맑음"
    if code in (2, 3): return "구름 많음"
    if code in (45, 48): return "안개"
    if code in (51, 53, 55, 56, 57): return "이슬비"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "비"
    if code in (71, 73, 75, 77, 85, 86): return "눈"
    if code in (95, 96, 99): return "천둥·번개"
    return "날씨 정보"

@app.get("/health")
def health():
    return {"ok": True, "tour_api_configured": bool(TOUR_KEY), "weather_api": "Open-Meteo", "version": "2.0.0"}

@app.get("/api/weather")
async def weather(lat: float = 37.5665, lng: float = 126.9780):
    c = (await get_json(METEO, {"latitude": lat, "longitude": lng,
        "current": "temperature_2m,precipitation,rain,weather_code,wind_speed_10m", "timezone": "Asia/Seoul"})).get("current", {})
    code = int(c.get("weather_code", -1))
    return {"temperature": c.get("temperature_2m"), "precipitation": c.get("precipitation"),
            "rain": c.get("rain"), "weather_code": code, "label": weather_name(code), "wind_speed": c.get("wind_speed_10m")}

async def nearby_raw(lat: float, lng: float, radius: int, content_type: int, count: int = 20):
    return [convert(x) for x in await tour("locationBasedList2", mapX=lng, mapY=lat,
        radius=max(500, min(radius, 20000)), contentTypeId=content_type, arrange="E", numOfRows=count)]

@app.get("/api/nearby")
async def nearby(lat: float = 37.5665, lng: float = 126.9780, radius: int = 3000, content_type: int = 12):
    return enrich((await nearby_raw(lat, lng, radius, content_type))[:10])

@app.get("/api/detour")
async def detour(lat: float = 37.5665, lng: float = 126.9780, exclude: str = ""):
    excluded = {x for x in exclude.split(",") if x}
    candidates = []
    for content_type in (12, 14, 15):
        candidates += await nearby_raw(lat, lng, 8000, content_type, 20)
    alternatives = unique(candidates, excluded)
    alternatives = sorted(enrich(alternatives), key=lambda x: (x["congestion"], x["dist"]))[:6]
    return {"quiet_alternatives": alternatives}

@app.get("/api/detail/{content_id}")
async def detail(content_id: str):
    items = await tour("detailCommon2", contentId=content_id, defaultYN="Y", firstImageYN="Y", overviewYN="Y", addrinfoYN="Y", mapinfoYN="Y", numOfRows=1)
    return items[0] if items else {}

@app.post("/api/schedule")
async def schedule(req: ScheduleReq):
    selected = [x for x in req.cards if x.get("title")][:4]
    plan = []
    for i, p in enumerate(selected):
        hour = req.start_hour + i * 2
        plan.append({"time": f"{hour:02d}:00", "title": p.get("title"), "addr": p.get("addr"), "contentid": p.get("contentid")})
    return {"title": "현재 상황 기준 추천 일정", "items": plan}

@app.post("/api/chat")
async def chat(req: ChatReq):
    m = req.message.lower()
    excluded = {str(x) for x in req.exclude_ids}
    is_crowded = any(k in m for k in ["혼잡", "붐비", "사람 많", "복잡", "줄이 길"])
    is_weather = any(k in m for k in ["비", "우천", "눈", "날씨"])
    if is_crowded:
        data = await detour(req.lat, req.lng, ",".join(excluded))
        return {"type": "detour", "title": "혼잡 우회 추천", "text": "입력하신 혼잡 상황을 고려해 기존 추천 장소를 제외하고 새로운 대체 장소를 추천해드릴게요.", "cards": data["quiet_alternatives"]}
    if is_weather:
        w = await weather(req.lat, req.lng)
        indoor = enrich(await nearby_raw(req.lat, req.lng, 8000, 14, 20))
        indoor = unique(indoor, excluded)[:6]
        return {"type": "weather", "title": "날씨 대응 추천", "text": "입력하신 우천·악천후 상황을 고려해 실내 문화시설을 중심으로 대안을 추천해드릴게요.", "weather": w, "cards": indoor}
    normal = enrich(await nearby_raw(req.lat, req.lng, 5000, 12, 12))
    return {"type": "nearby", "title": "주변 관광지 추천", "text": "현재 위치 주변 관광지를 찾아드렸어요. 마음에 드는 장소를 일정에 담아보세요.", "cards": normal[:6]}

app.mount("/static", StaticFiles(directory="app/static"), name="static")
@app.get("/", include_in_schema=False)
def index(): return FileResponse("app/static/index.html")

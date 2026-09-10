"""RePlan production-ready single-service app.
Required key: TOUR_API_KEY (data.go.kr Korean Tourism Organization TourAPI).
Weather: Open-Meteo public forecast API, no key required.
"""
import os, datetime, math
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

TOUR_KEY=os.getenv("TOUR_API_KEY","").strip()
TOUR_BASE="https://apis.data.go.kr/B551011/KorService2"
OPEN_METEO="https://api.open-meteo.com/v1/forecast"
app=FastAPI(title="RePlan", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatReq(BaseModel):
    message:str=Field(min_length=1,max_length=500)
    lat:float=37.5665
    lng:float=126.9780
    history:list[dict[str,Any]]=[]

async def json_get(url:str, params:dict):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r=await client.get(url,params=params); r.raise_for_status(); return r.json()
    except Exception as e:
        raise HTTPException(502,f"외부 API 호출 실패: {type(e).__name__}")

def items_from(data:dict)->list[dict]:
    try:
        items=data["response"]["body"]["items"]
        if not items:return []
        item=items.get("item",[])
        return item if isinstance(item,list) else [item]
    except (KeyError,TypeError):return []

async def tour_get(path:str, **params):
    if not TOUR_KEY: raise HTTPException(503,"TOUR_API_KEY가 설정되지 않았습니다.")
    base={"serviceKey":TOUR_KEY,"MobileOS":"ETC","MobileApp":"RePlan","_type":"json"}
    data=await json_get(f"{TOUR_BASE}/{path}",{**base,**params})
    return items_from(data)

def place(i:dict)->dict:
    try: dist=round(float(i.get("dist",0)))
    except: dist=0
    return {"title":i.get("title","관광지"),"addr":i.get("addr1", ""),"img":i.get("firstimage", ""),"dist":dist,"lat":i.get("mapy"),"lng":i.get("mapx"),"contentid":i.get("contentid"),"contenttypeid":i.get("contenttypeid")}

def score(p:dict, now=None)->float:
    now=now or datetime.datetime.now(); x=40.0
    if now.weekday()>=5:x+=25
    if 11<=now.hour<=16:x+=18
    if p.get("dist",9999)<1000:x+=5
    return min(round(x,1),100)

def weather_label(code:int)->str:
    if code in [0,1]: return "맑음"
    if code in [2,3]: return "구름 많음"
    if code in [45,48]: return "안개"
    if code in [51,53,55,56,57]: return "이슬비"
    if code in [61,63,65,66,67,80,81,82]: return "비"
    if code in [71,73,75,77,85,86]: return "눈"
    if code in [95,96,99]: return "천둥·번개"
    return "날씨 정보"

@app.get("/health")
def health():
    return {"ok":True,"tour_api_configured":bool(TOUR_KEY),"weather_api":"Open-Meteo","version":"1.0.0"}

@app.get("/api/weather")
async def weather(lat:float=Query(37.5665),lng:float=Query(126.9780)):
    data=await json_get(OPEN_METEO,{"latitude":lat,"longitude":lng,"current":"temperature_2m,precipitation,rain,weather_code,wind_speed_10m","timezone":"Asia/Seoul"})
    c=data.get("current",{})
    return {"temperature":c.get("temperature_2m"),"precipitation":c.get("precipitation"),"rain":c.get("rain"),"weather_code":c.get("weather_code"),"label":weather_label(int(c.get("weather_code",-1))),"wind_speed":c.get("wind_speed_10m")}

@app.get("/api/nearby")
async def nearby(lat:float=37.5665,lng:float=126.9780,radius:int=3000,content_type:int=12):
    rows=await tour_get("locationBasedList2",mapX=lng,mapY=lat,radius=max(500,min(radius,20000)),contentTypeId=content_type,arrange="E",numOfRows=10)
    return [{**place(i),"congestion":score(place(i))} for i in rows]

@app.get("/api/detour")
async def detour(lat:float=37.5665,lng:float=126.9780):
    rows=await nearby(lat,lng,8000,12)
    return {"quiet_alternatives":sorted(rows,key=lambda p:(p["congestion"],p["dist"]))[:5]}

@app.get("/api/detail/{content_id}")
async def detail(content_id:str):
    common=await tour_get("detailCommon2",contentId=content_id,defaultYN="Y",firstImageYN="Y",overviewYN="Y",addrinfoYN="Y",mapinfoYN="Y",numOfRows=1)
    return place(common[0]) if common else {}

@app.post("/api/chat")
async def chat(req:ChatReq):
    m=req.message
    if any(k in m for k in ["혼잡","붐비","사람 많","복잡","줄이 길"]):
        return {"type":"cards","title":"혼잡 우회 추천","text":"현재 주변이 혼잡하군요. 상대적으로 여유로운 대안 관광지를 추천해드릴게요.","cards":(await detour(req.lat,req.lng))["quiet_alternatives"]}
    if any(k in m for k in ["비","날씨","우천","눈"]):
        w=await weather(req.lat,req.lng)
        indoor=[place(i) for i in await tour_get("locationBasedList2",mapX=req.lng,mapY=req.lat,radius=5000,contentTypeId=14,arrange="E",numOfRows=10)]
        indoor=[{**p,"congestion":score(p)} for p in indoor]
        return {"type":"cards","title":"날씨 대응 추천","text":f"현재 날씨는 {w['label']}입니다. 실내 문화시설을 중심으로 대안을 추천해드릴게요.","weather":w,"cards":indoor[:5]}
    rows=[place(i) for i in await tour_get("locationBasedList2",mapX=req.lng,mapY=req.lat,radius=3000,contentTypeId=12,arrange="E",numOfRows=10)]
    return {"type":"cards","title":"주변 관광지 추천","text":"현재 위치 주변 관광지를 찾아드렸어요.","cards":[{**p,"congestion":score(p)} for p in rows[:5]]}

app.mount("/static",StaticFiles(directory="app/static"),name="static")
@app.get("/",include_in_schema=False)
def index():return FileResponse("app/static/index.html")

# RePlan — 실시간 여행 재설계 AI 가이드

2026 관광데이터 활용 공모전 웹·앱 구현 부문 지정과제 1용 배포-ready 프로토타입입니다.

## 핵심 가치
여행 중 혼잡·날씨·동선 문제가 생겼을 때 사용자가 상황을 말하면, 현재 위치 주변의 대체 관광지를 다시 찾아 여행 계획을 바꿀 수 있습니다.

## 구성
- FastAPI 단일 웹서비스: `app/main.py`
- 정적 프론트엔드: `app/static/index.html`
- 필수 인증키 1개: 한국관광공사 TourAPI `TOUR_API_KEY`
- 키 불필요 외부 API: Open-Meteo 날씨 API
- 로그인 없음

## 로컬 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export TOUR_API_KEY='공공데이터포털 서비스키'
uvicorn app.main:app --reload --port 8000
```
브라우저에서 `http://localhost:8000`을 엽니다.

자세한 배포 방법은 `DEPLOY.md`를 확인하세요.

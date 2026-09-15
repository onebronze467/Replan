# RePlan v2.1 — 실시간 여행 재설계 가이드

## 주요 기능
- 한국관광공사 TourAPI 실제 관광지 조회
- 입력한 지역·날짜·여행 스타일을 추천 조건에 반영
- 주변 추천 결과를 기억하고 혼잡 우회 시 기존 장소 제외
- 관광지·문화시설·행사 후보를 섞어 대체 장소 검색
- `예상 혼잡도`로 표현을 정정하여 실제 측정값과 혼동 방지
- 우천 상황 문구와 추천 결과 일치
- 추천 카드에서 장소를 누적한 뒤 간단한 시간표 생성
- API 실패 시 가짜 샘플을 보여주지 않고 오류를 명확히 표시
- `/health`를 사용한 실제 API 설정 상태 표시
- 로그인 없이 사용

## 사용 API
- 필수: 한국관광공사 국문 관광정보 서비스_GW (`locationBasedList2`, `detailCommon2`)
- 무료·키 없음: Open-Meteo Forecast API

## 배포
Vercel Python 배포 구조입니다. Vercel 환경변수에 다음을 등록합니다.

```text
TOUR_API_KEY=공공데이터포털 일반 인증키(Decoding)
```

환경변수 저장 후 Redeploy하고 `/health`에서 `tour_api_configured: true`를 확인합니다.

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`.env.example`을 참고해 `TOUR_API_KEY`를 셸 환경변수로 설정해야 실제 관광지 조회가 동작합니다.

# Vercel 배포 체크리스트
1. GitHub에 `api`, `app`, `requirements.txt`, `vercel.json`을 저장합니다.
2. Vercel에서 저장소를 Import합니다.
3. Environment Variables에 `TOUR_API_KEY`를 Production으로 추가합니다.
4. 값에는 공공데이터포털 일반 인증키(Decoding)만 입력합니다. 따옴표와 `TOUR_API_KEY=`는 넣지 않습니다.
5. 저장 후 Redeploy합니다.
6. `https://내주소.vercel.app/health`에서 `tour_api_configured: true` 확인
7. 주변 추천 → 혼잡해요 → 비가 와요 → 일정에 담기 순서로 시연합니다.

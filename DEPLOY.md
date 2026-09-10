# RePlan 배포·API 설정 안내

## 사용하는 API

### 1) 필수: 한국관광공사 국문 관광정보 서비스_GW / TourAPI 4.0
- 제공처: 공공데이터포털(data.go.kr)
- 기본 URL: `https://apis.data.go.kr/B551011/KorService2`
- 인증키 환경변수: `TOUR_API_KEY`
- 호출 오퍼레이션:
  - `locationBasedList2`: 현재 위치 주변 관광지 검색
  - `detailCommon2`: 관광지 상세정보(확장 기능)
- 호출 파라미터: `serviceKey`, `MobileOS=ETC`, `MobileApp=RePlan`, `_type=json`

### 2) 무료·키 불필요: Open-Meteo Forecast API
- URL: `https://api.open-meteo.com/v1/forecast`
- 용도: 현재 기온, 강수량, 날씨 코드, 풍속 조회
- 별도 가입이나 키가 필요하지 않음

## 배포 순서

1. 이 폴더를 GitHub 저장소에 업로드합니다.
2. Render에서 New → Web Service를 선택합니다.
3. 저장소를 연결하고 Docker 배포를 선택합니다.
4. 환경변수에 `TOUR_API_KEY`를 추가합니다.
5. 공공데이터포털에서 받은 서비스키를 값으로 붙여 넣습니다.
6. 배포 후 `https://발급된주소/health`를 엽니다.
7. `tour_api_configured: true`이면 키 설정이 완료된 것입니다.
8. 첫 화면에서 주변 추천·혼잡·비 상황을 차례로 테스트합니다.

## 키를 채팅에 보내지 마세요
서비스키는 이 대화에 붙여넣지 말고 배포 서비스의 환경변수에 직접 입력하세요.

## 최종 심사 전 확인
- 외부 URL에서 첫 화면이 열리는가
- `/health`가 정상인가
- 주변 추천 카드가 실제 관광공사 데이터로 나오는가
- 혼잡 버튼이 대안 관광지를 보여주는가
- 비 버튼이 실내 문화시설을 보여주는가
- 모바일과 PC에서 모두 열리는가

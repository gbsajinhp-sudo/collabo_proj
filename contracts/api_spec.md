# API Contract

## 책임자

human3

## 원칙

- FastAPI는 MotherDuck 읽기 전용 토큰만 사용한다.
- 브라우저는 MotherDuck에 직접 연결하지 않는다.
- API는 DATA_out을 조회하며 요청마다 전체 집계 엔진을 실행하지 않는다.
- 산업분류 다중선택, 조사연도, 시군, 행정동, 지표, H3 해상도를 지원한다.
- 응답 크기 제한과 확대 수준별 표현 규칙을 적용한다.

최종 endpoint와 응답 예시는 `dashbord_vercel`의 검증된 API를 이관할 때 확정한다.

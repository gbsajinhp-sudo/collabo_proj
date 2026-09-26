# MotherDuck Infrastructure

MotherDuck 원격 DB의 논리 구성, 적재 순서, 권한과 검증 명령을 문서화한다.

운영 연결 대상은 기존 `gyeonggi_industry_dashboard_v20260915`이며 현재 물리 스키마와 테이블명을 그대로 유지한다.

```text
기존 MotherDuck DB main 스키마
├─ DATA_in 논리 영역   # fact와 dimension, human1 책임
└─ DATA_out 논리 영역  # 집계 mart, human2 책임, human3 읽기
```

- human1과 human2의 적재 자격증명은 로컬 또는 보호된 CI에서만 사용한다.
- Vercel Runtime에는 `MOTHERDUCK_READONLY_TOKEN`만 등록한다.
- 토큰 값과 전체 DB 파일은 Git에 저장하지 않는다.
- 공유 운영 DB에는 쓰기 작업을 수행하지 않는다.
- 변경이 필요하면 새 버전 DB를 만들고 검증 후 human1이 전환을 승인한다.

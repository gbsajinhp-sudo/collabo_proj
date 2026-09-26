# Agent Collaboration Rules

이 저장소에서 각 human은 자신의 에이전트를 사용한다. 에이전트는 담당 경로와 데이터 계약을 우선 준수한다.

## 소유 경로

| 담당 | 기본 수정 경로 |
|---|---|
| human1 | `pipeline/data_in/`, `contracts/data_in_schema.md`, `docs/human1_data_lead.md`, 릴리스 문서 |
| human2 | `pipeline/engine/`, `pipeline/data_out/`, `contracts/metric_definition.md`, `contracts/data_out_schema.md` |
| human3 | `backend/`, `frontend/`, `contracts/api_spec.md`, `infra/vercel/` |

## 공통 규칙

- 다른 human의 소유 경로를 수정해야 하면 Pull Request 설명에 이유와 영향을 기록한다.
- `contracts/` 변경 후 관련 테스트와 샘플을 함께 갱신한다.
- 전체 데이터 대신 `samples/`의 비식별 소량 데이터를 사용한다.
- `.env`, 토큰, 개인 경로, DB 파일을 코드나 문서에 기록하지 않는다.
- 분석 API에서 지표를 즉석 계산하지 않고 검증된 DATA_out을 조회한다.
- 공유 MotherDuck DB `gyeonggi_industry_dashboard_v20260915`에 DDL이나 DML을 실행하지 않는다.
- 데이터 변경 실험은 소량 샘플이나 별도 버전 DB에서만 수행한다.
- Production 배포는 human1의 최종 확인 후 human1이 수행한다.

## 브랜치 이름

```text
feature/human1-data-<topic>
feature/human2-engine-<topic>
feature/human3-output-<topic>
fix/<topic>
docs/<topic>
```

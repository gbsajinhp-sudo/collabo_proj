# Gyeonggi Industry Atlas Hackathon

복잡한 실험 이력을 제외하고 검증된 경기도 산업집적 대시보드를 세 명이 재현하기 위한 독립 협업 저장소다.

## 목표

```text
DATA_in -> Engine -> DATA_out -> FastAPI -> Frontend -> Vercel
```

- human1: DATA_in, 프로젝트 리드, 통합 검수, 최종 Production 배포
- human2: 집적도, LQ, 증감률 엔진과 DATA_out
- human3: FastAPI, 지도 UI, 필터, Preview 배포 후보

MotherDuck의 815만 건 상세 데이터와 집계 데이터는 원격 DB에 저장한다. GitHub에는 코드, 계약, 소량 샘플, 검증 기준만 저장한다.

## 현재 단계

검증된 Vercel 배포본의 FastAPI, 프론트엔드, 경계 파일과 조회 검증 도구를 이관했다. 운영 데이터는 파일로 복사하지 않고 기존 MotherDuck DB `gyeonggi_industry_dashboard_v20260915`를 읽기 전용으로 공유한다.

| 기존 위치 | 이관 대상 |
|---|---|
| `../KSIC_10_11` | DATA_in 스키마, KSIC 연도별 매핑 규칙, 검증 기준 |
| `../dashboad_industry` | 최종 마트 생성 로직과 데이터 검증 기준 |
| `../dashbord_vercel` | 이관 완료한 FastAPI, 프론트엔드, Vercel 설정의 기준 원본 |

DB, Parquet, 중간 CSV, 실패한 실험 노트북과 임시 산출물은 이관하지 않는다.

## 공유 DB 안전 원칙

- 기존 MotherDuck DB의 테이블과 `main` 스키마를 변경하지 않는다.
- DATA_in과 DATA_out은 현재 팀 책임을 나누는 논리적 구분이며 물리 스키마명이 아니다.
- FastAPI와 팀원 기본 접속은 `MOTHERDUCK_READONLY_TOKEN`만 사용한다.
- 새 데이터 적재가 필요하면 기존 DB를 수정하지 않고 별도 버전 DB를 만든 뒤 human1 승인을 받는다.

## 협업 원칙

1. `main`은 항상 재현 및 배포 가능한 상태로 유지한다.
2. 모든 변경은 역할별 feature branch와 Pull Request를 사용한다.
3. `contracts/` 변경은 세 역할 모두의 영향 검토가 필요하다.
4. human1이 통합 검수 후 `main` 병합과 Production 배포를 승인한다.
5. 토큰, 대용량 DB, 원본 주소 데이터는 Git에 커밋하지 않는다.

상세 절차는 `docs/workflow.md`와 각 human 역할 문서를 따른다.


권장 구조
hackathon/
├─ .git/
├─ .github/
│  ├─ workflows/
│  └─ CODEOWNERS
├─ README.md
├─ AGENTS.md
├─ .gitignore
├─ .env.example
├─ vercel.json
│
├─ contracts/                 # 세 팀원이 공유하는 고정 규격
│  ├─ data_in_schema.md
│  ├─ data_out_schema.md
│  ├─ metric_definition.md
│  └─ api_spec.md
│
├─ pipeline/
│  ├─ data_in/                # 주소·좌표·KSIC·행정구역 결합
│  ├─ engine/                 # 집적도·LQ·증감률 계산
│  └─ data_out/               # H3·행정구역 사전집계 생성
│
├─ backend/                   # FastAPI 조회 전용 API
├─ frontend/                  # 지도·필터·히트맵 UI
├─ infra/
│  ├─ motherduck/
│  └─ vercel/
├─ samples/                   # 테스트용 소량 데이터
├─ tests/
└─ docs/
   ├─ workflow.md
   ├─ role_1_data_in.md
   ├─ role_2_engine.md
   ├─ role_3_output.md
   └─ deployment.md

   MotherDuck 구성
   
   MotherDuck 원격 DB
├─ data_in
│  ├─ fact_industry_location
│  ├─ dim_year
│  ├─ dim_industry
│  ├─ dim_admin
│  └─ dim_h3_cell
│
└─ data_out
   ├─ agg_h3_counts
   ├─ agg_h3_year_industry
   ├─ agg_heatmap_scale
   ├─ agg_admin_counts
   └─ agg_admin_year_industry

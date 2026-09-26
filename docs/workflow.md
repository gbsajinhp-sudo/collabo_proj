# Three-human Workflow

## 전체 흐름

```text
human1 DATA_in 확정
    -> Gate 1 입력 승인
human2 Engine 실행 및 DATA_out 확정
    -> Gate 2 지표 승인
human3 FastAPI와 Frontend 통합
    -> Gate 3 Preview 승인
human1 전체 결과 최종 확인
    -> Gate 4 Production 배포
```

## Gate 1: DATA_in

human1이 스키마, 행 수, 좌표, 행정구역, KSIC 연도별 적용과 manifest를 확인한다. 통과한 버전만 human2가 사용한다.

## Gate 2: Engine과 DATA_out

human2가 집적도, LQ, 증감률과 사전집계를 생성한다. human1은 계약 준수와 기존 기준값 대사를 확인한다.

## Gate 3: Output Preview

human3가 읽기 전용 FastAPI와 프론트엔드를 통합하고 Preview를 제출한다. 세 명이 필터, 지도, 히트맵, 주소지 점과 API 오류를 검수한다.

## Gate 4: Production

human1이 다음을 최종 확인하고 Production을 배포한다.

- 승인된 DATA_in과 DATA_out 버전
- Preview smoke test
- 환경변수와 읽기 전용 토큰
- Source Map과 비밀정보 미노출
- GitHub main의 승인된 commit SHA
- 롤백 대상 Production

## Git 흐름

```text
feature branch -> Pull Request -> 역할 검토 -> human1 merge -> main
main -> human1 Production 승인 및 배포
```

긴 수명의 역할별 branch를 운영하지 않는다. 작업 단위의 짧은 feature branch를 사용해 통합 지연을 줄인다.

# Shared Contracts

세 역할을 연결하는 고정 인터페이스다. 구현보다 먼저 합의하며 변경 시 관련 역할의 검토가 필요하다.

- `data_in_schema.md`: human1이 human2에게 전달하는 입력 규격
- `metric_definition.md`: human2가 구현하는 지표 공식과 예외 규칙
- `data_out_schema.md`: human2가 human3에게 전달하는 집계 규격
- `api_spec.md`: human3이 프론트엔드에 제공하는 API 규격

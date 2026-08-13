# MembershipFlow Observability

MembershipFlow 운영 서버와 분리된 관찰·장애 분석 시스템이다.

## Responsibilities

- 운영 Spring Boot 및 호스트 메트릭 수집
- 운영 Alloy가 전송한 JSON 로그 저장
- Grafana 경보 평가
- Loki 근거 수집 및 Gemini 분석
- Slack 인시던트 전송
- 분석 작업과 전송 이력을 위한 독립 `membershipflow_incident` DB 운영

운영 서비스의 `membershipflow` DB는 이 저장소와 모니터링 서버로 이전하지 않는다.

## Deployment flow

```text
issue branch -> develop -> main -> monitoring EC2
```

- 일반 작업: `<type>/<issue-number>/<keyword>` → `develop`
- 릴리즈: `develop` → `main`
- `main` 병합: 이미지 빌드·GHCR 업로드
- `MONITORING_DEPLOY_ENABLED=true`: 모니터링 EC2 배포

자세한 규칙은 [.github/BRANCH_WORKFLOW.md](.github/BRANCH_WORKFLOW.md)를 참고한다.

## Required server configuration

1. `.env.example`을 `/opt/membershipflow-observability/.env`로 복사
2. 비밀값과 운영 서버 사설 IP 입력
3. 운영 EC2 보안 그룹에서 모니터링 EC2의 `8081`, `9100` 접근 허용
4. 모니터링 EC2 보안 그룹에서 운영 EC2의 `3100` 접근 허용
5. Grafana는 기본적으로 `127.0.0.1:3000`에만 바인딩

비밀값과 실제 운영 로그는 저장소에 커밋하지 않는다.


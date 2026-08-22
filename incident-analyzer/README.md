# MembershipFlow Incident Analyzer

현재 범위는 HMAC 기반 incident 접수, 전용 MySQL 작업 큐, Grafana 경보 평가값과
Loki log Evidence 조회, Gemini 구조화 분석, Evidence·분석 결과 저장, Slack 장애 알림
전송까지다. Prometheus 추가 조회 Evidence는 포함하지 않는다.

## 디렉터리 구조

```text
app/
├── api/             # FastAPI 요청·응답과 라우팅
├── collectors/      # Loki 등 외부 Evidence 수집
├── domain/          # 인시던트·Evidence·분석 결과 규칙
├── llm/             # LLM 공통 계약과 Gemini 구현
├── notifications/   # Slack 메시지 생성과 Incoming Webhook 전송
├── persistence/     # DB 연결·SQLAlchemy 모델·저장소
├── security/        # 웹훅 서명 검증
├── config.py        # 환경 설정
├── main.py          # API 실행 진입점
└── worker.py        # 분석 worker 실행 진입점
```

## 로컬 실행

1. database·전용 계정 생성과 migration 적용

```bash
docker compose --profile incident-setup run --rm incident-db-bootstrap
docker compose --profile incident-setup run --rm --no-deps incident-migrate
```

2. API 실행

```bash
docker compose up -d incident-api
```

3. 분석 worker 실행

`.env`에 새로 발급한 `GEMINI_API_KEY`, 실제 사용 가능한 고정 `LLM_MODEL`,
`SLACK_WEBHOOK_URL`을 설정한 뒤 Loki와 함께 실행한다. API key,
모델명, Webhook URL은 저장소에 커밋하지 않는다.

```bash
docker compose up -d loki incident-worker
```

4. 상태 확인

```bash
docker compose exec incident-api python -m app.healthcheck live
docker compose exec incident-api python -m app.healthcheck ready
```

API는 host port를 열지 않고 `incident-ingress`에서 Grafana webhook만 받는다. worker만
Loki, Gemini, Slack에 접근하며, Spring Boot와 프론트엔드에는 외부 API 비밀값을 제공하지
않는다.

운영 CD는 동일 Dockerfile을 `membershipflow-observability-incident-analyzer:<git-sha>`로 한 번 빌드해
API, migration, worker가 같은 불변 이미지를 사용하도록 배포한다. DB bootstrap과 migration
완료 후 API·worker를 기동하며, API readiness와 Loki readiness를 모두 통과해야 배포 성공으로
처리한다.

API·worker 컨테이너 메모리 상한은 각각 160MB다. 운영 애플리케이션과 운영 DB는 별도
서버에서 실행하며 analyzer 배포가 해당 컨테이너의 재시작 정책에 영향을 주지 않는다.

실제 비밀번호는 `.env`에만 둔다. 운영에서는
`INCIDENT_DB_RUNTIME_PASSWORD`, `INCIDENT_DB_MIGRATION_PASSWORD`를 base64url 문자로 생성해
환경변수로 주입한다.

## 테스트

```bash
python -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.lock
.venv/bin/pytest
```

통합 테스트는 일회용 MySQL 8 Testcontainer를 사용해 migration, 권한 격리,
incident·job 원자 저장, worker 상태 전이, Evidence·분석 결과·Slack 전송 작업의 원자 저장,
전송 상태 전이를 검증한다. Loki, Gemini, Slack은 가짜 응답으로 timeout, 5xx, 429,
데이터 부재, 잘못된 JSON, 잘못된 Evidence ID를 검증하며 일반 CI에서 실제 외부 API를
호출하지 않는다.

Slack 전송은 분석 성공 트랜잭션에서 `notification_deliveries`에 함께 등록한다. worker는
전송 작업을 lease 기반으로 선점하며 429의 `Retry-After`, timeout, 5xx를 재시도한다.
Slack 장애는 저장된 분석 결과를 실패로 되돌리지 않는다. Incoming Webhook 특성상 Slack이
수신한 직후 worker가 종료되면 중복 알림 가능성은 남는다.

Docker Desktop for Mac에서 Docker socket 자동 탐지가 실패하면 다음과 같이 실행한다.

```bash
DOCKER_HOST=unix://$HOME/.docker/run/docker.sock .venv/bin/pytest
```

`requirements.in`, `requirements-dev.in`은 직접 의존성 목록이고, 실제 설치에는
해시가 포함된 `requirements.lock`, `requirements-dev.lock`만 사용한다.

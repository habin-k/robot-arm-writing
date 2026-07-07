# server 패키지 문서

Doosan M0609 로봇팔 글씨 쓰기 시스템의 백엔드 서버입니다.
FastAPI 기반으로 구축되며, HMI(프론트엔드)와 ROS2(로봇 제어) 사이를 연결합니다.

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 백엔드 서버 | FastAPI |
| 프론트엔드 HMI | React (별도 팀원 담당) |
| 실시간 통신 | WebSocket (FastAPI 내장) |
| 인증 | JWT (python-jose) |
| 로봇 통신 | ROS2 서비스/토픽 (TODO) |

---

## 전체 아키텍처

```
React 프론트엔드 (HMI)
    ↕ REST API + WebSocket
FastAPI 백엔드 (이 서버)
    ↕ ROS2 서비스/토픽
writing_node.py (로봇 제어)
    ↕ DSR API
Doosan M0609 로봇팔
```

---

## 디렉토리 구조

```
server/
├── requirements.txt
└── app/
    ├── main.py                  ← FastAPI 앱 진입점, Swagger 자동 생성
    ├── core/
    │   ├── config.py            ← 관리자 계정, JWT 설정
    │   ├── auth.py              ← JWT 인증 로직
    │   └── robot_state.py       ← 작업 상태 공유 저장소 (진행률 등)
    ├── models/
    │   ├── auth.py              ← 로그인 요청/응답 스키마
    │   ├── writing.py           ← 글씨 쓰기 요청/응답 스키마
    │   └── robot.py             ← 로봇 제어 요청/응답 스키마
    ├── routers/
    │   ├── auth.py              ← POST /auth/login, /logout
    │   ├── fonts.py             ← GET /fonts
    │   ├── writing.py           ← POST /writing/preview, /execute 등
    │   └── robot.py             ← POST /robot/home, /jog 등 (관리자 전용)
    └── websockets/
        ├── progress.py          ← WS /ws/progress (작업 진행률 실시간)
        └── robot.py             ← WS /ws/robot (로봇 상태 실시간)
```

---

## 설치 및 실행

```bash
cd server/
pip install -r requirements.txt

# 로컬에서만 접속
uvicorn app.main:app --reload --port 8000

# 팀원도 접속 가능하도록 (같은 네트워크)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실행 후 Swagger: `http://localhost:8000/docs`
팀원 접속: `http://<내 IP>:8000/docs` (IP는 `hostname -I` 로 확인)

---

## HMI 요구사항

### 탭 구성

| 탭 | 접근 방법 | 기능 |
|---|---|---|
| 사용자 탭 | 로그인 없이 바로 접속 | 문구 입력, 미리보기, 실행, 진행률 확인 |
| 관리자 탭 | 로그인 필요 (JWT) | 로봇 제어, 비상정지, 조그, 원점 복귀 |

> **관리자가 로그인한 경우** 사용자 탭도 이용 가능해야 합니다.
> (한 컴퓨터에서 HMI를 실행하기 때문)
> React Router의 권한 분기로 구현: 비로그인 → 사용자 탭만, 로그인 → 모든 탭

---

### 사용자 탭 기능 상세

#### 입력 요소
| 항목 | 설명 |
|---|---|
| 문구 입력 | 사용자가 직접 입력하는 텍스트 (`\n`으로 줄바꿈 가능) |
| 글씨 크기 | 슬라이더 또는 숫자 입력 (최솟값 5mm ~ 최댓값 50mm) |
| 폰트 선택 | `GET /fonts` 로 목록 불러와 버튼/드롭다운으로 선택 |

#### 버튼
| 버튼 | 동작 |
|---|---|
| 시뮬레이션 | `POST /writing/preview` 호출 → Canvas에 경로 렌더링 (로봇 동작 없음) |
| 실행 | `POST /writing/execute` 호출 → 실제 로봇 동작 시작 |
| 취소 | `DELETE /writing/cancel` 호출 → 진행 중인 작업 중단 |

#### 미리보기 (Canvas 렌더링)
- `POST /writing/preview` 응답의 `waypoints` 배열을 Canvas에 그림
- `pen_down=1` 구간은 선으로, `pen_down=0` 구간은 이동(선 없음)으로 표시
- A4 용지 비율에 맞게 렌더링

#### 작업 진행률 (실시간 — WebSocket)
`WS /ws/progress` 연결 후 아래 데이터를 실시간으로 표시:

```json
{
  "job_id": "abc123",
  "status": "writing",
  "progress_pct": 45,
  "current_stroke": 10,
  "total_strokes": 23,
  "current_char": "o",
  "error_msg": ""
}
```

| 표시 항목 | 설명 |
|---|---|
| 진행률 바 | `progress_pct` (0~100%) |
| 현재 작업 글자 | `current_char` |
| 획 진행 | `current_stroke` / `total_strokes` |
| 상태 | `status` (idle / writing / done / error / cancelled) |
| 에러 메시지 | `error_msg` (에러 발생 시 표시) |

---

### 관리자 탭 기능 상세

> 모든 API에 JWT 토큰 필요 (`Authorization: Bearer <token>`)

#### 버튼
| 버튼 | API | 설명 |
|---|---|---|
| 비상정지 | `POST /robot/emergency-stop` | 즉시 로봇 정지 |
| 원점 복귀 | `POST /robot/home` | 홈 자세로 이동 |
| 에러 리셋 | `POST /robot/error-reset` | 에러 상태 초기화 |

#### 수동 조그 패널
`POST /robot/jog` 호출. 요청 형식:
```json
{
  "axis": "z",
  "direction": -1,
  "step_mm": 5.0
}
```
- 축: X / Y / Z / RX / RY / RZ
- 방향: + / -
- 이동거리: 조절 가능 (예: 1mm / 5mm / 10mm 버튼)

#### 로봇 상태 모니터링 (실시간 — WebSocket)
`WS /ws/robot` 연결 후 TCP 위치, 조인트 각도, 에러 코드 실시간 표시

---

## API 전체 목록

### 인증
| Method | Endpoint | 인증 필요 | 설명 |
|---|---|---|---|
| POST | `/auth/login` | X | 관리자 로그인 → JWT 반환 |
| POST | `/auth/logout` | X | 로그아웃 |

### 폰트
| Method | Endpoint | 인증 필요 | 설명 |
|---|---|---|---|
| GET | `/fonts` | X | 사용 가능한 폰트 목록 |

### 글씨 쓰기
| Method | Endpoint | 인증 필요 | 설명 |
|---|---|---|---|
| POST | `/writing/preview` | X | 미리보기 웨이포인트 생성 |
| POST | `/writing/execute` | X | 로봇 실행 시작 |
| DELETE | `/writing/cancel` | X | 작업 취소 |
| GET | `/writing/status` | X | 현재 작업 상태 조회 |

### 로봇 제어 (관리자 전용)
| Method | Endpoint | 인증 필요 | 설명 |
|---|---|---|---|
| POST | `/robot/home` | O | 원점 복귀 |
| POST | `/robot/emergency-stop` | O | 비상정지 |
| POST | `/robot/error-reset` | O | 에러 리셋 |
| POST | `/robot/jog` | O | 수동 조그 |
| GET | `/robot/status` | O | 로봇 상태 조회 |

### WebSocket
| Endpoint | 인증 필요 | 설명 |
|---|---|---|
| `WS /ws/progress` | X | 작업 진행률 실시간 스트림 |
| `WS /ws/robot` | X | 로봇 상태 실시간 스트림 |

---

## ROS2 연동 (TODO)

현재 로봇 제어 API들은 stub 상태입니다. 아래 파일의 `# TODO` 주석 위치에 ROS2 서비스 호출을 추가해야 합니다.

| 파일 | 연동 내용 |
|---|---|
| `routers/writing.py` | `/writing/execute` → ROS2 writing 서비스 호출 |
| `routers/writing.py` | `/writing/cancel` → ROS2 cancel 서비스 호출 |
| `routers/robot.py` | 모든 엔드포인트 → ROS2 서비스 호출 |
| `websockets/robot.py` | ROS2 토픽 구독 → WebSocket으로 전달 |
| `core/robot_state.py` | writing_node 진행률 → `broadcast_progress()` 호출 |

---

## 관리자 계정 설정

`app/core/config.py` 에서 수정:

```python
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin1234"  # 실제 배포 시 환경변수로 교체
```

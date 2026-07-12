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
| 로봇 통신 | ROS2 토픽 (`/robot/target_moving`, `/robot/status`) |

---

## 전체 아키텍처

```
React 프론트엔드 (HMI)
    ↕ REST API + WebSocket
FastAPI 백엔드 (이 서버)
    ↕ ROS2 토픽 발행 (/robot/target_moving)
pub_sub.py (ControllerNode)
    ↕ DSR API (movel, posx)
Doosan M0609 로봇팔
    ↕ ROS2 토픽 구독 (/robot/status)
FastAPI 백엔드 (상태 수신)
```

---

## 디렉토리 구조

```
server/
├── requirements.txt
├── pub_sub.py               ← ROS2 구독/발행 노드 (로봇 직접 제어, init_dsr() 패턴)
└── app/
    ├── main.py              ← FastAPI 앱 진입점, Swagger·ROS2 노드 시작, hmi/dist 정적 서빙(/)
    ├── core/
    │   ├── config.py        ← 관리자 계정, JWT 설정
    │   ├── auth.py          ← JWT 인증 로직
    │   ├── robot_state.py   ← 작업 상태 공유 저장소 (진행률 등)
    │   └── ros_node.py      ← FastAPI용 ROS2 publisher 노드 (백그라운드 실행)
    ├── models/
    │   ├── auth.py          ← 로그인 요청/응답 스키마
    │   ├── writing.py       ← 글씨 쓰기 요청/응답 스키마
    │   └── robot.py         ← 로봇 제어 요청/응답 스키마
    ├── routers/
    │   ├── auth.py          ← POST /auth/login, /logout
    │   ├── fonts.py         ← GET /fonts
    │   ├── writing.py       ← POST /writing/preview, /execute 등
    │   └── robot.py         ← POST /robot/home, /jog 등 (관리자 전용)
    └── websockets/
        ├── progress.py      ← WS /ws/progress (작업 진행률 실시간)
        └── robot.py         ← WS /ws/robot (로봇 상태 실시간)
```

---

## 설치 및 실행

```bash
cd server/
pip install -r requirements.txt
```

### 실행 순서 (반드시 이 순서로)

```bash
# 터미널 1: ROS2 환경 source 후 pub_sub.py 실행
source /home/dongmin/ws_cobot_pjt/ws_dsr/install/setup.bash
cd /home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing
python3 server/pub_sub.py

# 터미널 2: FastAPI 서버 실행
cd /home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실행 후:
- HMI 화면: `http://localhost:8000/` (팀원: `http://172.23.0.201:8000/`)
- Swagger: `http://localhost:8000/docs`

> **HMI 화면도 이 서버(8000)가 서빙한다.** `main.py` 가 `hmi/dist/`(React 빌드물)를
> 루트 `/` 에 `StaticFiles` 로 마운트하므로, uvicorn 하나로 화면+API 를 모두 제공한다.
> (예전엔 Vite 개발 서버(5173)가 화면을 따로 띄웠음 → 이제 별도 서버 불필요.)
> - **화면(`hmi/src`) 을 수정하면** `hmi/` 에서 `npm run build` 를 다시 돌려 `dist/` 를
>   갱신해야 8000 에 반영된다.
> - 화면을 자주 고치는 **개발 중에는** 예전처럼 `hmi/` 에서 `npm run dev`(5173)로 핫리로드
>   하는 게 편하다. 그때도 API 호출은 8000 을 그대로 쓴다(`client.js` BASE_URL).
> - `dist/` 가 없으면(빌드 전) API 만 뜨고 `/` 접속 시 "not built" 안내가 나온다.
>   헬스체크 엔드포인트는 `GET /health`.

팀원 접속: `http://172.23.0.201:8000/`  (같은 WiFi에 접속한 팀원)

> **접속 IP 주의**
> `hostname -I`에 여러 IP가 뜨는데, 팀원 공유용은 **WiFi 대역(예: `172.23.0.201`)**입니다.
> - `172.23.0.201` (`wlx...` 무선랜) → 팀원 공유용. 같은 WiFi면 여기로 접속.
> - `192.168.1.10` (`enx...` 유선랜) → **로봇 컨트롤러 직결 라인**. 팀원은 이 대역에 없으므로 공유 불가.
> - `172.17.0.1` (`docker0`) → 도커 가상 주소. 무시.
>
> 실제 IP는 `ip -brief addr`로 인터페이스별 확인. WiFi가 바뀌면 IP도 바뀝니다.
> 팀원이 접속 안 되면: ① `sudo ufw allow 8000/tcp` ② WiFi의 AP isolation(단말 격리) 여부 확인.

---

## ROS2 토픽 통신 구조

### FastAPI → pub_sub.py (글씨 쓰기 명령)

| 토픽 | 타입 | 발행자 | 구독자 |
|---|---|---|---|
| `/robot/target_moving` | `Float32MultiArray` | FastAPI (ros_node.py) | pub_sub.py |
| `/safety/emergency_stop` | `Bool` | FastAPI (ros_node.py) | pub_sub.py |

### pub_sub.py → FastAPI (로봇 상태)

| 토픽 | 타입 | 데이터 | 발행자 | 구독자 |
|---|---|---|---|---|
| `/robot/status` | `String` | WRITING/HOMING/IDLE/ERROR | pub_sub.py | FastAPI (ros_node `_on_status`) |
| `/robot/progress` | `Float32MultiArray` | `[완료 획, 전체 획]` | pub_sub.py | FastAPI (ros_node `_on_progress`) |
| `/robot/current_pose` | `Float32MultiArray` | `[x,y,z,rx,ry,rz]` (User_102) | pub_sub.py | FastAPI (ros_node `_on_pose`) |
| `/robot/force` | `Float32MultiArray` | `[fx,fy,fz,tx,ty,tz]` (User_102) | pub_sub.py | FastAPI (ros_node `_on_force`) |

> **진행률/현재 글자**: `/robot/progress` 의 완료 획 수 → `job_state.current_stroke`·`progress_pct`
> 갱신 + `job_state.stroke_chars`(execute 시 `PathGenerator.stroke_char_map` 으로 채움)로
> **현재 글자(`current_char`)** 를 역추적한다. 완료율 100%는 `/robot/status`(IDLE→done)에서 확정.
>
> **실시간 좌표·외력(User_102)**: 유휴/조그뿐 아니라 **글씨 쓰는 도중에도** 실시간 갱신된다.
> 이를 위해 그리기 모션을 블로킹 `movesx` 대신 **async `amovesx` + `check_motion()` 폴링**으로
> 실행하고, 폴링 루프(`_wait_motion_done`)에서 `_publish_live()` 로 좌표·외력을 발행한다
> (단일 스레드 폴링이라 DSR 노드 spin 충돌 없음).
>
> **외력 좌표 변환**: `get_tool_force` 는 BASE/TOOL/WORLD 만 지원하므로, 시작 시
> `get_user_cart_coord(102)` 로 회전행렬을 캐시해 BASE 외력을 User_102 로 변환해 발행한다
> (`_force_user102`). 조회 실패 시 BASE 그대로 폴백.

### 웨이포인트 데이터 포맷

`/robot/target_moving` 토픽의 `Float32MultiArray` 데이터 구조:

```
[x1, y1, z1, rx1, ry1, rz1, pen_down1,  x2, y2, z2, rx2, ry2, rz2, pen_down2, ...]
```

점 하나당 **7개 값**. `pen_down`은 `1.0`(글씨) 또는 `0.0`(공이동).

### 좌표 변환 (ros_node.py)

`path_generator.py`의 도화지 좌표 → 로봇 베이스 좌표:

```python
robot_X = PAPER_ORIGIN_X - path_y   # 567.77 - path_y
robot_Y = PAPER_ORIGIN_Y + path_x   # -155.60 + path_x
robot_Z = PAPER_ORIGIN_Z            # pen_down: 98.0mm
robot_Z = PAPER_ORIGIN_Z + 30.0     # pen_up: 128.0mm (hover)
rx, ry, rz = 90.0, 180.0, 90.0      # TCP 자세 고정
```

---

## HMI 요구사항

### 탭 구성

| 탭 | 접근 방법 | 기능 |
|---|---|---|
| 사용자 탭 | 로그인 없이 바로 접속 | 문구 입력, 미리보기, 실행, 진행률 확인 |
| 관리자 탭 | 로그인 필요 (JWT) | 로봇 제어, 비상정지, 조그, 원점 복귀 |

> **관리자가 로그인한 경우** 사용자 탭도 이용 가능해야 합니다.
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
| 취소 | `DELETE /writing/cancel` 호출 → `/safety/emergency_stop` 토픽 발행 |

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
| 비상정지 | `POST /robot/emergency-stop` | `/safety/emergency_stop` 토픽 발행 |
| 원점 복귀 | `POST /robot/home` | 홈 자세로 이동 (TODO: ROS2 연동) |
| 에러 리셋 | `POST /robot/error-reset` | 에러 상태 초기화 (TODO: ROS2 연동) |

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

### 기타
| Method | Endpoint | 인증 필요 | 설명 |
|---|---|---|---|
| GET | `/` | X | HMI 화면(`hmi/dist` 정적 서빙). dist 없으면 "not built" 안내 |
| GET | `/health` | X | 헬스체크 `{"status":"ok"}` (예전 `GET /` 자리) |
| GET | `/docs` | X | Swagger UI |

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
| POST | `/writing/execute` | X | 경로 생성 후 `/robot/target_moving` 토픽 발행 |
| DELETE | `/writing/cancel` | X | `/safety/emergency_stop` 토픽 발행 |
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

## pub_sub.py DSR 초기화 주의사항

`writing_node.py`와 동일한 패턴을 사용합니다. DSR_ROBOT2 import 시점에 `DR_init.__dsr__node`가 반드시 설정되어 있어야 합니다.

```python
# main() 에서의 올바른 순서
node = ControllerNode()       # 1. ROS2 노드 생성
DR_init.__dsr__node = node    # 2. DR_init에 노드 등록
node.init_dsr()               # 3. DSR_ROBOT2 import (이 시점에 g_node 읽힘)
```

`__init__` 안에서 DSR_ROBOT2를 import하면 `g_node = None` 에러가 발생합니다.

---

## ROS2 연동 현황

| 파일 | 내용 | 상태 |
|---|---|---|
| `core/ros_node.py` | `/robot/status`·`/robot/progress`·`/robot/current_pose`·`/robot/force` 구독 → job_state/robot_live 갱신 + 브로드캐스트 | ✅ 완료 |
| `core/robot_state.py` | 진행률·좌표·외력 → `broadcast_progress()`/`broadcast_robot()` | ✅ 완료 |
| `websockets/robot.py` | `/ws/robot` 로 좌표·외력·종이감지 실시간 전달 | ✅ 완료 |
| `routers/robot.py` | `/robot/home`, `/robot/error-reset`, `/robot/jog` → ROS2 서비스 호출 | 일부 (jog 연동됨) |

### 실기 검증 필요 (하드웨어 없이 확정 불가)
- `get_current_posx(ref=102)` / `get_user_cart_coord(102)` 반환값·ref 가 BASE 기준인지
- `f_user`(외력) 회전 변환의 부호/자세 규약 (ZYZ) 이 실제 값과 일치하는지
- async `amovesx` + `check_motion()==0` 완료 판정이 획 단위로 정확히 끊기는지
  (문제 시 그리기 루프를 블로킹 `movesx` 로 되돌리면 실시간 힘만 포기하고 동작은 복구됨)

---

## 관리자 계정 설정

`app/core/config.py` 에서 수정:

```python
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"  # 실제 배포 시 환경변수로 교체
```

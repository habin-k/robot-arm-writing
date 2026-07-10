# hmi 패키지 문서

Doosan M0609 로봇팔 글씨 쓰기 시스템의 프론트엔드 HMI입니다.
React + Vite 기반이며, FastAPI 백엔드(`../server`)와 REST/WebSocket으로 통신합니다.

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 프레임워크 | React 19 + Vite |
| HTTP 통신 | axios |
| 실시간 통신 | WebSocket (브라우저 내장) |
| 스타일 | CSS Modules (다크 테마) |

---

## 디자인

OpenAI Platform 대시보드를 벤치마킹한 **다크 테마 + 좌측 사이드바** 레이아웃입니다.

- 배경 `#111`, 사이드바 `#0d0d0d`, 카드 `#1a1a1a`, 테두리 `#2a2a2a`
- 사이드바에 사용자/관리자 메뉴 섹션 분리
- 로그인 없이 바로 사용자 화면 표시, **관리자 메뉴 클릭 시에만 로그인 요구**

---

## 디렉토리 구조

```
hmi/src/
├── main.jsx                 ← 진입점
├── App.jsx                  ← 사이드바 + 페이지 라우팅 + 로그인 상태 관리
├── App.css                  ← 전역 스타일, 사이드바
├── api/
│   ├── client.js            ← axios 인스턴스, BASE_URL, JWT 토큰, WS_URL
│   ├── writing.js           ← 글씨 쓰기 API (preview, execute, cancel, status)
│   └── robot.js             ← 로그인 + 로봇 제어 API (home, estop, jog 등)
├── hooks/
│   ├── useProgress.js       ← WS /ws/progress 진행률 구독 훅 (연결 상태 포함)
│   └── useRobotState.js     ← WS /ws/robot 구독 훅 (좌표·외력·종이감지, User_102)
└── components/
    ├── user/
    │   ├── UserTab.jsx       ← 글씨 쓰기 탭 (입력, 폰트, 크기, 미리보기, 실행)
    │   ├── PreviewCanvas.jsx ← 웨이포인트 → Canvas 렌더링 (A4 비율)
    │   └── StatusTab.jsx     ← 작업 상태 탭 (진행률·현재글자·획진행, 실시간)
    └── admin/
        ├── AdminTab.jsx      ← 로봇 제어 탭 (비상정지, 원점복귀, 조그, 좌표·외력 모니터)
        └── LoginModal.jsx    ← 관리자 로그인 모달
```

---

## 페이지 구성

| 메뉴 | 컴포넌트 | 접근 | 설명 |
|---|---|---|---|
| 글씨 쓰기 | `UserTab` | 누구나 | 문구 입력, 미리보기, 실행 |
| 작업 상태 | `StatusTab` | 누구나 | 진행률·상태 실시간 표시 |
| 로봇 제어 | `AdminTab` | 로그인 | 원점복귀, 에러리셋, 조그 |
| 비상정지 | `AdminTab estopOnly` | 로그인 | 비상정지 버튼만 |

> 로그인 상태는 `App.jsx`가 관리. 관리자 메뉴 클릭 시 토큰 없으면 `LoginModal` 표시.

---

## 백엔드 연동

### 서버 주소 설정

`src/api/client.js`의 `BASE_URL`을 서버 주소에 맞게 수정합니다.

```js
const BASE_URL = 'http://localhost:8000'   // 로컬 테스트
// const BASE_URL = 'http://172.23.0.201:8000'  // 팀원 접속 시 서버 IP (WiFi 대역)
// 주의: 192.168.1.x는 로봇 직결 유선 라인이라 팀원 공유 불가. WiFi 대역(172.23.x) 사용.
```

WebSocket 주소(`WS_URL`)는 `BASE_URL`에서 자동 파생됩니다.

### 사용 API

| 기능 | 호출 | 백엔드 |
|---|---|---|
| 폰트 목록 | `getFonts()` | `GET /fonts` |
| 미리보기 | `previewWriting()` | `POST /writing/preview` |
| 실행 | `executeWriting()` | `POST /writing/execute` |
| 취소 | `cancelWriting()` | `DELETE /writing/cancel` |
| 로그인 | `login()` | `POST /auth/login` |
| 원점 복귀 | `goHome()` | `POST /robot/home` |
| 비상정지 | `emergencyStop()` | `POST /robot/emergency-stop` |
| 에러 리셋 | `errorReset()` | `POST /robot/error-reset` |
| 조그 | `jog()` | `POST /robot/jog` |

### 실시간 진행률 (WebSocket)

`useProgress()` 훅이 `ws://<서버>/ws/progress`에 연결합니다.

```js
const { progress, connected } = useProgress()
// progress: { status, progress_pct, current_stroke, total_strokes, current_char, error_msg, job_id }
// connected: WebSocket 연결 여부 (StatusTab 연결 상태 표시에 사용)
```

- **실시간**: 서버가 상태/획 완료마다 push → StatusTab이 즉시 갱신(새로고침 불필요).
- `current_char`(현재 글자): 서버가 획 인덱스로 역추적해 채운다(획→글자 매핑).
- `progress_pct`·`current_stroke`: 획 완료마다 갱신, 완료 시 100%.

### 실시간 로봇 상태 (WebSocket)

`useRobotState()` 훅이 `ws://<서버>/ws/robot`에 연결합니다. (AdminTab 로봇 제어 탭)

```js
const { robot, connected } = useRobotState()
// robot: { tcp_position: [x,y,z,rx,ry,rz],   // User_102 좌표 (mm, °)
//          tcp_force:    [fx,fy,fz,tx,ty,tz], // User_102 외력 (N, Nm) — Fx/Fy/Fz 표시
//          paper_present: true|false|null }
```

- 좌표·외력 모두 **User_102 좌표계** 기준이며, **글씨 쓰는 도중에도** 실시간 갱신된다.

두 훅 모두 연결이 끊기면 2초마다 자동 재연결을 시도합니다.

---

## 주요 UI 동작

### 미리보기 (PreviewCanvas)
- `POST /writing/preview` 응답의 `waypoints` 배열을 Canvas에 렌더링
- `pen_down=1`은 선, `pen_down=0`은 이동(선 없음)
- Y축 반전(도화지 원점은 좌하단), A4 landscape 비율(295.57:209.72) 유지

### 연속 조그 (AdminTab)
- 버튼을 **누르면 이동 시작**, **떼면 정지** (네이티브 DSR jog 서비스)
- `onMouseDown` → `jog({moving: true})`, `onMouseUp` → `jog({moving: false})`
- 저속(10) / 중속(30) / 고속(60) mm·s 속도 선택

---

## 설치 및 실행

```bash
cd hmi/
npm install

# 로컬
npm run dev

# 팀원 접속 (같은 네트워크)
npm run dev -- --host
```

기본 포트: `http://localhost:5173`
팀원 접속: `http://172.23.0.201:5173`  (WiFi 대역 IP. `ip -brief addr`의 `wlx...` 인터페이스 주소)

---

## 전체 시스템 실행 순서

HMI가 실제로 동작하려면 백엔드/로봇도 함께 실행해야 합니다.

```bash
# 1. 로봇 드라이버
ros-bringup_real_mode

# 2. ROS2 통신 노드
python3 server/pub_sub.py

# 3. FastAPI 서버
uvicorn app.main:app --host 0.0.0.0 --port 8000   # server/ 에서

# 4. HMI
npm run dev   # hmi/ 에서
```

> UI만 확인하려면 4번만 실행해도 되지만, API 호출은 실패하고 캔버스는 빈 상태로 표시됩니다.

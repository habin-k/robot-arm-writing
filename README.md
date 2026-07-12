# Cobot Writing System

두산 M0609 협동로봇, OnRobot RG2 그리퍼, Arduino 종이 감지 센서, FastAPI 서버, React HMI를 연동한 자동 필기 시스템입니다. 사용자가 HMI에서 문장과 글꼴을 입력하면 서버가 폰트 경로를 로봇 웨이포인트로 변환하고, ROS2 작업 관리자가 펜 파지, 필기, 도장, 종이 배출 시퀀스를 수행합니다.

---

## 1. 시스템 설계

### 1.1 전체 구성

```mermaid
flowchart LR
    User["사용자"]

    subgraph UI["HMI"]
        direction TB
        HMI["React HMI"]
    end

    subgraph Server["Backend"]
        direction TB
        API["FastAPI Server"]
        PathGen["Path Generator<br/>TTF/OTF -> Waypoints"]
        RosPub["writing_publisher"]
    end

    subgraph ROS["ROS2 Control"]
        direction TB
        TaskManager["task_manager"]
        SensorNode["paper_sensor_publisher"]
        Bringup["m0609_rg2_bringup"]
    end

    subgraph HW["Hardware"]
        direction TB
        Robot["Doosan M0609"]
        Gripper["OnRobot RG2"]
        Arduino["Arduino<br/>Paper Sensor"]
    end

    User --> HMI
    HMI --> API
    API --> PathGen
    PathGen --> RosPub
    RosPub -->|"작업 요청<br/>/robot/target_moving"| TaskManager
    TaskManager --> Bringup
    Bringup --> Robot
    Robot --> Gripper

    Arduino --> SensorNode
    SensorNode -->|"종이 감지<br/>/paper_sensor"| TaskManager

    TaskManager -.->|"상태 피드백<br/>status, pose, force, progress"| API
    API -.-> HMI

    classDef user fill:#fff7ed,stroke:#f97316,stroke-width:1px,color:#111827;
    classDef ui fill:#eff6ff,stroke:#2563eb,stroke-width:1px,color:#111827;
    classDef server fill:#ecfdf5,stroke:#059669,stroke-width:1px,color:#111827;
    classDef ros fill:#f5f3ff,stroke:#7c3aed,stroke-width:1px,color:#111827;
    classDef hw fill:#fef2f2,stroke:#dc2626,stroke-width:1px,color:#111827;

    class User user;
    class HMI ui;
    class API,PathGen,RosPub server;
    class TaskManager,SensorNode,Bringup ros;
    class Arduino,Robot,Gripper hw;
```

### 1.2 작업 플로우

```mermaid
flowchart TD
    A[Arduino 종이 센서 준비] --> B[ROS2 워크스페이스 빌드 및 source]
    B --> C[HMI 정적 파일 빌드]
    C --> D[FastAPI 서버 실행]
    D --> E[ROS2 통합 launch 실행]
    E --> F[HMI에서 문장/폰트/펜 선택]
    F --> G[서버가 글씨 경로 생성]
    G --> H["/robot/target_moving 발행"]
    H --> I{"종이 감지됨?"}
    I -- 아니오 --> J[NO_PAPER 상태 표시]
    I -- 예 --> K[펜 파지]
    K --> L[힘 제어 기반 필기]
    L --> M[펜 반납]
    M --> N[도장 파지 및 도장 찍기]
    N --> O[종이 배출]
    O --> P[원점 복귀 및 작업 완료]
```

### 1.3 예외 처리 플로우

```mermaid
flowchart TD
    A[작업 중 예외 발생] --> B{"예외 종류"}
    B -- 종이 없음 --> C[NO_PAPER 상태 표시]
    B -- 펜/도장 파지 실패 --> D[파지 재시도]
    D --> E{"재시도 성공?"}
    E -- 예 --> F[기존 작업 계속 진행]
    E -- 아니오 --> G[MANUAL_REQUIRED 상태 표시]
    B -- 비상정지 또는 모션 오류 --> G
    B -- 종이 배출 오류 --> G
    G --> H[관리자 수동 복구]
    H --> I{"재시도 요청?"}
    I -- 예 --> J[같은 웨이포인트로 재실행]
    I -- 아니오 --> K[작업 중단]
```

### 1.4 주요 ROS2 노드, 토픽, 서비스

#### 노드

| 노드 | 실행 위치 | 역할 |
| :--- | :--- | :--- |
| `paper_sensor_publisher` | `hand_writing.launch.py` | Arduino 시리얼 값을 읽어 종이 감지 상태 발행 |
| `writing_publisher` | FastAPI 서버 내부 | HMI/API 요청을 ROS2 토픽과 서비스 호출로 변환 |
| `task_manager` | `hand_writing.launch.py` | 종이 확인, 펜/도장 파지, 필기, 배출 전체 시퀀스 수행 |
| `dsr_motion` | `task_manager` 내부 | DSR 모션 함수 호출용 ROS2 노드 |
| `m0609_rg2_bringup` 관련 노드 | `hand_writing.launch.py`에서 include | Doosan M0609 및 OnRobot RG2 bringup |

#### 서버가 발행하는 제어 토픽

| 토픽 | 타입 | 역할 |
| :--- | :--- | :--- |
| `/robot/target_moving` | `std_msgs/Float32MultiArray` | 필기 웨이포인트 전달 |
| `/robot/pen` | `std_msgs/String` | 사용할 펜 색상 선택 |
| `/robot/tuning` | `std_msgs/String` | 관리자 모션/경로 파라미터 전달 |
| `/safety/emergency_stop` | `std_msgs/Bool` | 비상정지 명령 |
| `/robot/go_home` | `std_msgs/Bool` | 원점 복귀 명령 |
| `/robot/error_reset` | `std_msgs/Bool` | 에러 리셋 명령 |
| `/robot/jog` | `std_msgs/Float32MultiArray` | HMI 수동 조그 명령 |
| `/robot/grip` | `std_msgs/Bool` | 그리퍼 수동 열기/닫기 명령 |

#### task_manager가 구독하는 입력 토픽

| 토픽 | 타입 | 역할 |
| :--- | :--- | :--- |
| `/paper_sensor` | `std_msgs/Bool` | 종이 감지 상태 |
| `/robot/target_moving` | `std_msgs/Float32MultiArray` | 작업 시작 트리거 및 웨이포인트 |
| `/robot/pen` | `std_msgs/String` | 작업에 사용할 펜 선택 |
| `/robot/tuning` | `std_msgs/String` | 속도, 힘, 접촉 판단값 등 튜닝값 |
| `/safety/emergency_stop` | `std_msgs/Bool` | 작업 중단 요청 |
| `/robot/go_home` | `std_msgs/Bool` | 원점 복귀 요청 |
| `/robot/error_reset` | `std_msgs/Bool` | 수동 복구 후 에러 리셋 |
| `/robot/jog` | `std_msgs/Float32MultiArray` | 수동 조그 요청 |
| `/robot/grip` | `std_msgs/Bool` | 수동 그리퍼 제어 |
| `/OnRobotRGInput` | `onrobot_rg_msgs/OnRobotRGInput` | 그리퍼 폭 피드백 및 파지 성공 판단 |

#### 로봇 상태 피드백 토픽

| 토픽 | 타입 | 역할 |
| :--- | :--- | :--- |
| `/robot/status` | `std_msgs/String` | `WRITING`, `IDLE`, `NO_PAPER`, `MANUAL_REQUIRED` 등 작업 상태 |
| `/robot/current_pose` | `std_msgs/Float32MultiArray` | HMI 표시용 TCP 좌표 |
| `/robot/current_pose_base` | `std_msgs/Float32MultiArray` | BASE 기준 TCP 좌표 |
| `/robot/force` | `std_msgs/Float32MultiArray` | HMI 표시용 TCP 외력 |
| `/robot/force_base` | `std_msgs/Float32MultiArray` | BASE 기준 TCP 외력 |
| `/robot/progress` | `std_msgs/Float32MultiArray` | 필기 진행률 `[완료 획, 전체 획]` |

#### 서비스

| 서비스 | 타입 | 역할 |
| :--- | :--- | :--- |
| `/dsr01/task_manager/retry` | `std_srvs/Trigger` | 수동 복구 후 같은 웨이포인트로 작업 재시도 |
| `/dsr01/motion/move_stop` | `dsr_msgs2/MoveStop` | 비상정지 시 진행 중 모션 정지 |
| `/dsr01/motion/jog` | `dsr_msgs2/Jog` | HMI 수동 조그 명령 전달 |

---

## 2. 운영체제 환경

| 항목 | 환경 |
| :--- | :--- |
| OS | Ubuntu 22.04 LTS 권장 |
| ROS | ROS2 Humble 기준 |
| Python | Python 3.10 기준 |
| Node.js | Vite/React 실행 가능한 Node.js LTS |
| 로봇 통신 | PC와 두산 로봇 제어기 이더넷 연결 |
| 기본 로봇 포트 | `12345` |
| Arduino 포트 예시 | `/dev/ttyACM0` 또는 `/dev/ttyUSB0` |

> 현재 `setup.py`는 폰트 설치 경로에 Python 3.10 경로를 사용합니다. Python 3.8 환경에서는 설치 경로를 확인해야 합니다.

---

## 3. 권장 워크스페이스 구조

본 패키지는 ROS2 워크스페이스의 `src` 아래에 위치하는 것을 기준으로 설명합니다. 두산 로봇 및 OnRobot RG2 관련 패키지는 별도 워크스페이스에 설치되어 있을 수 있으므로, 실행 시 두 워크스페이스의 `setup.bash`를 함께 source 합니다.

```text
~/<workspace>/
├── build/
├── install/
├── log/
└── src/
    └── cobot_writing/
        ├── README.md
        ├── package.xml
        ├── setup.py
        ├── launch/
        │   └── hand_writing.launch.py
        ├── cobot_writing/
        │   ├── path_generator.py
        │   ├── paper_sensor_publisher.py
        │   ├── task_manager_node.py
        │   ├── writer.py
        │   └── fonts/
        ├── server/
        │   ├── requirements.txt
        │   └── app/
        ├── hmi/
        │   ├── package.json
        │   └── src/
        └── arduino/
            └── paper_sensor/
                └── paper_sensor.ino

~/<dsr_workspace>/
├── install/
└── src/
    ├── dsr_msgs2/
    ├── m0609_rg2_bringup/
    └── onrobot_rg_msgs/
```

기본 실행 전 source 순서:

```bash
source ~/<workspace>/install/setup.bash
source ~/<dsr_workspace>/install/setup.bash
```

---

## 4. 사용 장비 목록

| 분류 | 장비 | 용도 |
| :--- | :--- | :--- |
| 로봇 | Doosan Robotics M0609 | 필기, 도장, 종이 배출 모션 수행 |
| 그리퍼 | OnRobot RG2 | 펜, 도장, 종이 파지 |
| 제어 PC | Ubuntu 워크스테이션 또는 노트북 | ROS2, FastAPI, HMI 실행 |
| 센서 | Arduino + 종이 감지 센서 | 작업 시작 전 종이 유무 확인 |
| 필기 도구 | 펜 3종 | HMI에서 선택 가능한 필기 도구 |
| 도장 | 도장 및 보관 지그 | 필기 후 도장 작업 |
| 작업물 | A4 용지 | 필기 대상 |
| 지그 | 펜/도장/용지 정렬 지그 | 반복 작업 위치 고정 |
| 네트워크 | LAN 케이블 | PC와 로봇 제어기 연결 |

---

## 5. 의존성

### 5.1 ROS2 패키지 의존성

`package.xml` 기준 실행 의존성은 다음과 같습니다.

```text
launch
launch_ros
rclpy
std_msgs
std_srvs
dsr_msgs2
onrobot_rg_msgs
m0609_rg2_bringup
```

Ubuntu 패키지 예시:

```bash
sudo apt install python3-serial python3-numpy
```

Python 모듈:

```bash
pip install fonttools
```

### 5.2 FastAPI 서버 의존성

서버 의존성은 `server/requirements.txt`에 정의되어 있습니다.

```text
fastapi
uvicorn[standard]
python-jose[cryptography]
passlib[bcrypt]
python-multipart
python-dotenv
fonttools
```

설치:

```bash
cd server
pip install -r requirements.txt
```

### 5.3 HMI 의존성

HMI는 Vite + React 기반입니다. 의존성은 `hmi/package.json`에 정의되어 있습니다.

```bash
cd hmi
npm install
```

---

## 6. 실행 순서

### Step 1. Arduino 종이 감지 센서 업로드

Arduino IDE에서 다음 스케치를 보드에 업로드합니다.

```text
arduino/paper_sensor/paper_sensor.ino
```

Arduino 연결 포트를 확인합니다.

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```

시리얼 권한이 없으면 사용자를 `dialout` 그룹에 추가한 뒤 로그아웃/로그인합니다.

```bash
sudo usermod -aG dialout $USER
```

### Step 2. ROS2 워크스페이스 빌드

워크스페이스 루트에서 패키지를 빌드합니다.

```bash
cd ~/<workspace>
colcon build --packages-select cobot_writing
source install/setup.bash
```

두산 로봇 및 OnRobot RG2 패키지가 별도 워크스페이스에 있다면 함께 source 합니다.

```bash
source ~/<dsr_workspace>/install/setup.bash
```

### Step 3. HMI 정적 파일 빌드

FastAPI 서버가 HMI 정적 파일을 함께 제공하므로, 운영/시연 전 HMI를 빌드합니다.

```bash
cd ~/<workspace>/src/cobot_writing/hmi
npm install
npm run build
```

### Step 4. FastAPI 서버 실행

새 터미널에서 ROS2 환경을 source 한 뒤 서버를 실행합니다.

```bash
cd ~/<workspace>/src/cobot_writing
source ~/<workspace>/install/setup.bash
source ~/<dsr_workspace>/install/setup.bash
cd server
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

브라우저 접속:

```text
http://localhost:8000
```

개발 중 HMI만 따로 확인하려면 Vite 개발 서버를 실행합니다.

```bash
cd ~/<workspace>/src/cobot_writing/hmi
npm run dev
```

기본 접속 주소:

```text
http://localhost:5173
```

### Step 5. ROS2 통합 launch 실행

새 터미널에서 ROS2 환경을 source 한 뒤 통합 launch를 실행합니다.

가상 로봇:

```bash
source ~/<workspace>/install/setup.bash
source ~/<dsr_workspace>/install/setup.bash
ros2 launch cobot_writing hand_writing.launch.py mode:=virtual sensor_port:=/dev/ttyACM0
```

실제 로봇:

```bash
source ~/<workspace>/install/setup.bash
source ~/<dsr_workspace>/install/setup.bash
ros2 launch cobot_writing hand_writing.launch.py mode:=real host:=<ROBOT_IP> port:=12345 sensor_port:=/dev/ttyACM0
```

통합 launch는 다음 구성을 함께 실행합니다.

```text
m0609_rg2_bringup/bringup.launch.py
cobot_writing/paper_sensor_publisher
cobot_writing/task_manager
```

### Step 6. 작업 실행

1. HMI에서 로봇 상태와 종이 감지 상태를 확인합니다.
2. 작성할 문장, 글꼴, 펜 색상, 글자 크기 등 작업 조건을 입력합니다.
3. 실행 버튼을 누르면 FastAPI 서버가 글씨 경로를 생성합니다.
4. 서버 내부 ROS2 노드가 `/robot/target_moving` 토픽으로 웨이포인트를 발행합니다.
5. `task_manager`가 종이 감지 여부를 확인한 뒤 펜 파지, 필기, 도장, 종이 배출, 원점 복귀 시퀀스를 수행합니다.

---

## 7. 동작 확인 명령

서버 상태 확인:

```bash
curl http://localhost:8000/health
```

ROS2 토픽 확인:

```bash
ros2 topic list
ros2 topic echo /paper_sensor --once
ros2 topic echo /robot/status --once
```

launch 인자 확인:

```bash
ros2 launch cobot_writing hand_writing.launch.py --show-args
```

import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .routers import auth, fonts, writing, robot, tuning
from .websockets import progress, robot as ws_robot
from .core.ros_node import start_ros_node
from .core import robot_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ROS 콜백에서 WebSocket 브로드캐스트를 예약할 수 있도록 이벤트 루프 저장
    robot_state.event_loop = asyncio.get_running_loop()
    start_ros_node()   # FastAPI 시작 시 ROS2 노드 백그라운드 실행
    yield


app = FastAPI(
    title="Robot Arm Writing API",
    description="Doosan M0609 로봇팔 글씨 쓰기 제어 서버",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(fonts.router)
app.include_router(writing.router)
app.include_router(robot.router)
app.include_router(tuning.router)
app.include_router(progress.router)
app.include_router(ws_robot.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


# React 빌드 결과물을 FastAPI 루트에 마운트한다.
# API 라우터 등록 뒤에 마운트해야 정적 파일 라우트가 API 경로를 가로채지 않는다.
_HMI_DIST = Path(__file__).resolve().parents[2] / "hmi" / "dist"
if _HMI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_HMI_DIST), html=True), name="hmi")
else:
    # 프론트 빌드 전에는 API만 구동하고 루트에서 상태를 안내한다.
    @app.get("/", tags=["Health"])
    def _no_dist():
        return {"status": "ok", "hmi": "not built — run `npm run build` in hmi/"}

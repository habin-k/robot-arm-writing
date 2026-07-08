import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, fonts, writing, robot
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
app.include_router(progress.router)
app.include_router(ws_robot.router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok"}

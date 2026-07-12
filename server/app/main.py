import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


# --- HMI(React 빌드 결과물) 정적 서빙 ---------------------------------------
# hmi/dist 를 루트("/")에 마운트해서, uvicorn 8000 하나로 화면+API 를 모두 제공한다.
# (기존엔 Vite 개발 서버(5173)가 화면을 따로 서빙했음)
# ⚠ 이 mount 는 반드시 모든 API 라우터 등록 뒤에 와야 한다. "/" 가 API 경로까지
#    가로채지 않도록, 라우터에 매칭되지 않은 요청만 정적 파일로 처리된다.
# dist 경로: .../cobot_writing/server/app/main.py → parents[2] == cobot_writing
_HMI_DIST = Path(__file__).resolve().parents[2] / "hmi" / "dist"
if _HMI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_HMI_DIST), html=True), name="hmi")
else:
    # dist 가 없으면(빌드 전) API 만 뜨고, 루트 접속 시 안내를 위해 헬스체크를 루트에도 남긴다.
    @app.get("/", tags=["Health"])
    def _no_dist():
        return {"status": "ok", "hmi": "not built — run `npm run build` in hmi/"}

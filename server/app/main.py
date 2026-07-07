from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, fonts, writing, robot
from .websockets import progress, robot as ws_robot

app = FastAPI(
    title="Robot Arm Writing API",
    description="Doosan M0609 로봇팔 글씨 쓰기 제어 서버",
    version="1.0.0",
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

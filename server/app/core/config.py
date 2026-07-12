import os
from pathlib import Path

from dotenv import load_dotenv

# server/.env가 있으면 관리자 계정과 JWT 설정을 환경변수로 덮어쓴다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 제출/로컬 실행용 기본값. 실제 운영 환경에서는 .env나 환경변수로 교체한다.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

import os
from pathlib import Path

from dotenv import load_dotenv

# server/.env 를 로드한다. (이 파일 위치: server/app/core/config.py → parents[2] = server/)
# .env 가 없어도 오류 없이 넘어가며, 이 경우 아래 기본값이 사용된다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 민감 정보는 환경변수로 주입한다. 환경변수가 없으면 로컬 개발용 기본값을 사용.
# 배포 시에는 반드시 환경변수(ADMIN_PASSWORD, SECRET_KEY)를 설정할 것.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

from fastapi import APIRouter, HTTPException, status
from ..models.auth import LoginRequest, TokenResponse
from ..core.auth import verify_password, create_access_token
from ..core.config import ADMIN_USERNAME, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["인증"])


@router.post("/login", response_model=TokenResponse, summary="관리자 로그인")
def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or not verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸습니다.",
        )
    token = create_access_token(
        {"sub": req.username}, ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return TokenResponse(access_token=token)


@router.post("/logout", summary="로그아웃")
def logout():
    # JWT는 stateless — 클라이언트가 토큰을 삭제하면 됨
    return {"message": "로그아웃 완료"}

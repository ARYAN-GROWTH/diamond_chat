# src/api/auth.py
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from src.db.connection import get_db
from src.core.config import settings
from src.core.logging import get_logger
import bcrypt
import uuid
import jwt

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ============================================================
# 🧩 MODELS
# ============================================================
class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "user"  # optional role field (default = user)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ============================================================
# 🔐 JWT HELPERS
# ============================================================
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Generate JWT access token with expiry."""
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=getattr(settings, "JWT_EXPIRE_MINUTES", 60)))
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode a JWT and return payload, or raise HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_user_by_email(db: AsyncSession, email: str):
    """Fetch a user by email from DB."""
    result = await db.execute(
        text("SELECT id, email, display_name, password, 'user' AS role, last_session_id FROM public.users WHERE email = :email LIMIT 1"),
        {"email": email},
    )
    row = result.first()
    return dict(row._mapping) if row else None


# ============================================================
# 🧾 SIGNUP
# ============================================================
@router.post("/signup")
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    existing = await get_user_by_email(db, request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = bcrypt.hashpw(request.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    await db.execute(
        text("""
            INSERT INTO public.users (external_id, display_name, email, password, created_at, last_session_id)
            VALUES (:external_id, :display_name, :email, :password, NOW(), :last_session_id)
        """),
        {
            "external_id": request.username,
            "display_name": request.username,
            "email": request.email,
            "password": hashed_pw,
            "last_session_id": str(uuid.uuid4()),  # initialize first session_id
        },
    )
    await db.commit()

    logger.info(f"🆕 New user registered: {request.email}")
    return {"message": "Signup successful"}


# ============================================================
# 🔑 LOGIN
# ============================================================
@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and issue JWT token."""
    user = await get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(request.password.encode("utf-8"), user["password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ✅ Generate a new session on each login (ChatGPT style)
    new_session = str(uuid.uuid4())
    await db.execute(
        text("UPDATE public.users SET last_session_id = :sid WHERE id = :uid"),
        {"sid": new_session, "uid": user["id"]},
    )
    await db.commit()

    # ✅ Include role + username inside JWT
    token = create_access_token(
        {
            "sub": user["email"],
            "user_id": user["id"],
            "username": user["display_name"],
            "role": user.get("role", "user"),
        }
    )

    logger.info(f"✅ Login success for user: {user['email']} — new session: {new_session}")
    return TokenResponse(access_token=token)


# ============================================================
# 👤 ME ENDPOINT
# ============================================================
@router.get("/me")
async def get_me(token: str):
    """Decode token and return user info."""
    try:
        payload = decode_access_token(token)  # ✅ use central decoder
        return {
            "email": payload.get("sub"),
            "username": payload.get("username"),
            "user_id": payload.get("user_id"),
            "role": payload.get("role", "user"),
            "exp": payload.get("exp"),
        }
    except HTTPException as e:
        raise e

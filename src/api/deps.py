
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timezone
from src.core.config import settings

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """Decode JWT and return user info or guest identity if not authenticated."""

    #  Case 1: No token → Guest mode
    if not credentials:
        return {
            "user_id": None,
            "email": "guest@local",
            "username": "guest",
            "role": "guest",
            "exp": None,
        }

    token = credentials.credentials

    try:
      
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])

        # Expiry validation
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Token expired")

        return {
            "user_id": payload.get("user_id"),
            "email": payload.get("sub"),
            "username": payload.get("username"),
            "role": payload.get("role", "user"),
            "exp": exp,
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")



async def require_role(required_role: str, current_user: dict = Depends(get_current_user)):
    """Ensure user has the required role (e.g., admin)."""
    if current_user.get("role") != required_role:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied — requires {required_role} role."
        )
    return current_user

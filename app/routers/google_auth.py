import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.core.security import create_access_token

router = APIRouter(prefix="/api/google_auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FRONTEND_SUCCESS_URI = os.getenv("FRONTEND_SUCCESS_URI")


@router.get("/google")
async def login_google():
    """Redirect the user to Google's consent screen"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google Client ID missing")

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&scope=openid%20profile%20email"
        "&access_type=offline"
    )
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def auth_google_callback(code: str, db: AsyncSession = Depends(get_db)):
    """Receive the gode from Google, verifies it, and issues JWT"""
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to exchange token with Google"
            )

        google_tokens = token_response.json()
        google_access_token = google_tokens["access_token"]

        userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
        userinfo_response = await client.get(
            userinfo_url, headers={"Authorization": f"Bearer {google_access_token}"}
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to exchange token with Google"
            )

        userinfo_json = userinfo_response.json()
        google_email = userinfo_json.get("email")

    result = await db.execute(select(User).where(User.email == google_email))
    user = result.scalars().first()

    if not user:
        user = User(email=google_email, hashed_password="GOOGLE_AUTH_NO_PASSWORD")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.email)})

    response = RedirectResponse(url=FRONTEND_SUCCESS_URI)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=1800,
        path="/",
    )

    return response


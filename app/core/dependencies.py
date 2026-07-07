import jwt
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.core.security import SECRET_KEY, ALGORITHM

async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    # Extract the raw cookie string
    token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception

    try:
        # open the JWT and extract payload
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception

    except jwt.PyJWTError:
        # catches expired tokens
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    await db.execute(text(f"SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(int(user.id))})


    return user

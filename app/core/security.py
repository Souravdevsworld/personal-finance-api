from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": subject,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
    )


# if __name__ == "__main__":
#     password = "MySecurePassword123!"
#
#     hashed = hash_password(password)
#
#     print("Original:", password)
#     print("Hashed:", hashed)
#     print("Correct password:", verify_password(password, hashed))
#     print("Wrong password:", verify_password("wrong-password", hashed))

# if __name__ == "__main__":
#     token = create_access_token("123")
#
#     print("Token:")
#     print(token)
#
#     decoded = decode_access_token(token)
#
#     print("Decoded:")
#     print(decoded)





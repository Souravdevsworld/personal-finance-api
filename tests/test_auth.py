"""Tests for the authentication endpoints.

Run from the project root with:

    pytest -q tests/test_auth.py

The suite uses an isolated temporary SQLite database. The application's
real finance.db is never opened, created, or modified.
"""

import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.core.config import settings

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# Make the `app` package importable when pytest is run from different locations.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from app.db.database import Base, get_db  # noqa: E402
from app.db.models import User  # noqa: E402
from app.main import app  # noqa: E402


REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"

# An existing authenticated analytics endpoint is used as the protected
# endpoint because test_analytics.py already verifies that this route requires
# authentication.
PROTECTED_URL = "/api/analytics/summary"

SessionFactory = Callable[[], Session]

VALID_EMAIL = "auth.test@example.com"
VALID_PASSWORD = "test-password-123"


# --------------------------------------------------------------------------- #
# Database / client fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    """Create a completely isolated SQLite database for the auth tests."""
    db_path = tmp_path_factory.mktemp("auth_db") / "test_finance.db"

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(test_engine)

    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def clean_tables(
    session_factory: sessionmaker[Session],
) -> Iterator[None]:
    """Ensure every test starts with an empty database."""
    yield

    with session_factory() as session:
        session.execute(delete(User))
        session.commit()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    """Override the production DB dependency with the isolated test DB."""

    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def register_user(
    client: TestClient,
    email: str = VALID_EMAIL,
    password: str = VALID_PASSWORD,
):
    """Register a user and return the response."""
    return client.post(
        REGISTER_URL,
        json={
            "email": email,
            "password": password,
        },
    )


def get_user_by_email(
    session_factory: sessionmaker[Session],
    email: str,
) -> User | None:
    with session_factory() as session:
        return session.query(User).filter(User.email == email).first()


def create_database_user(
    session_factory: sessionmaker[Session],
    email: str,
    password: str,
) -> User:
    """Create a user directly in the isolated test database."""
    with session_factory() as session:
        user = User(
            email=email,
            hashed_password=hash_password(password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        user_id = user.id

    with session_factory() as session:
        return session.get(User, user_id)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
class TestRegistration:
    def test_successful_registration(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        response = register_user(client)

        assert response.status_code == 201

        body = response.json()

        assert body["email"] == VALID_EMAIL
        assert "id" in body

        # Sensitive password information must never be returned.
        assert "password" not in body
        assert "hashed_password" not in body

        # Verify that the user was actually persisted.
        user = get_user_by_email(session_factory, VALID_EMAIL)

        assert user is not None
        assert user.email == VALID_EMAIL
        assert user.id == body["id"]

    def test_duplicate_registration(
        self,
        client: TestClient,
    ) -> None:
        first_response = register_user(client)

        assert first_response.status_code == 201

        second_response = register_user(client)

        assert second_response.status_code == 400
        assert second_response.json() == {
            "detail": "Email already registered"
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "email": "not-an-email",
                "password": VALID_PASSWORD,
            },
            {
                "email": "missing-password@example.com",
            },
            {
                "email": "short-password@example.com",
                "password": "x",
            },
        ],
    )
    def test_invalid_registration_returns_422(
        self,
        client: TestClient,
        payload: dict[str, str],
    ) -> None:
        response = client.post(
            REGISTER_URL,
            json=payload,
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    def test_registered_password_is_hashed(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        response = register_user(client)

        assert response.status_code == 201

        user = get_user_by_email(session_factory, VALID_EMAIL)

        assert user is not None
        assert user.hashed_password != VALID_PASSWORD
        assert user.hashed_password

        # The stored value must be a valid password hash for the plaintext
        # password used during registration.
        assert verify_password(
            VALID_PASSWORD,
            user.hashed_password,
        )

        # The plaintext password must not have been stored.
        assert user.hashed_password != VALID_PASSWORD


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
class TestLogin:
    def test_successful_login(
        self,
        client: TestClient,
    ) -> None:
        registration_response = register_user(client)

        assert registration_response.status_code == 201

        response = client.post(
            LOGIN_URL,
            data={
                "username": VALID_EMAIL,
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert "access_token" in body
        assert body["access_token"]
        assert body["token_type"] == "bearer"

    def test_login_with_wrong_password(
        self,
        client: TestClient,
    ) -> None:
        registration_response = register_user(client)

        assert registration_response.status_code == 201

        response = client.post(
            LOGIN_URL,
            data={
                "username": VALID_EMAIL,
                "password": "definitely-wrong-password",
            },
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Incorrect email or password"
        }

    def test_login_with_nonexistent_email(
        self,
        client: TestClient,
    ) -> None:
        response = client.post(
            LOGIN_URL,
            data={
                "username": "does-not-exist@example.com",
                "password": VALID_PASSWORD,
            },
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Incorrect email or password"
        }

    @pytest.mark.parametrize(
        "form_data",
        [
            {
                "password": VALID_PASSWORD,
            },
            {
                "username": VALID_EMAIL,
            },
        ],
    )
    def test_login_validation_returns_422(
        self,
        client: TestClient,
        form_data: dict[str, str],
    ) -> None:
        response = client.post(
            LOGIN_URL,
            data=form_data,
        )

        assert response.status_code == 422
        assert "detail" in response.json()


# --------------------------------------------------------------------------- #
# Protected endpoint / authentication failures
# --------------------------------------------------------------------------- #
class TestProtectedEndpoint:
    def test_protected_endpoint_without_token(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(PROTECTED_URL)

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Not authenticated"
        }

    def test_protected_endpoint_with_malformed_token(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(
            PROTECTED_URL,
            headers={
                "Authorization": "Bearer not-a-real-jwt",
            },
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Could not validate credentials"
        }

    def test_protected_endpoint_with_expired_token(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        user = create_database_user(
            session_factory,
            "expired-token@example.com",
            VALID_PASSWORD,
        )

        # Create an expired JWT using the same configuration and algorithm
        # used by the application.
        expired_payload = {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.SECRET_KEY,
            algorithm="HS256",
        )

        response = client.get(
            PROTECTED_URL,
            headers={
                "Authorization": f"Bearer {expired_token}",
            },
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Could not validate credentials"
        }


# --------------------------------------------------------------------------- #
# JWT identity
# --------------------------------------------------------------------------- #
class TestTokenIdentity:
    def test_token_contains_correct_user_identity(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        registration_response = register_user(
            client,
            email="identity@example.com",
            password=VALID_PASSWORD,
        )

        assert registration_response.status_code == 201

        created_user_id = registration_response.json()["id"]

        login_response = client.post(
            LOGIN_URL,
            data={
                "username": "identity@example.com",
                "password": VALID_PASSWORD,
            },
        )

        assert login_response.status_code == 200

        token = login_response.json()["access_token"]

        # Decode using the application's configured SECRET_KEY and algorithm.
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )

        assert payload["sub"] == str(created_user_id)

        user = get_user_by_email(
            session_factory,
            "identity@example.com",
        )

        assert user is not None
        assert payload["sub"] == str(user.id)


# --------------------------------------------------------------------------- #
# Additional authentication security checks
# --------------------------------------------------------------------------- #
class TestAuthenticationSecurity:
    def test_login_token_can_authenticate_user(
        self,
        client: TestClient,
    ) -> None:
        registration_response = register_user(
            client,
            email="protected@example.com",
            password=VALID_PASSWORD,
        )

        assert registration_response.status_code == 201

        login_response = client.post(
            LOGIN_URL,
            data={
                "username": "protected@example.com",
                "password": VALID_PASSWORD,
            },
        )

        assert login_response.status_code == 200

        token = login_response.json()["access_token"]

        protected_response = client.get(
            PROTECTED_URL,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert protected_response.status_code == 200

    def test_registration_response_does_not_expose_sensitive_fields(
        self,
        client: TestClient,
    ) -> None:
        response = register_user(
            client,
            email="response-security@example.com",
            password=VALID_PASSWORD,
        )

        assert response.status_code == 201

        body = response.json()

        sensitive_keys = {
            "password",
            "hashed_password",
            "hash",
            "password_hash",
        }

        assert sensitive_keys.isdisjoint(body.keys())

    def test_password_is_not_stored_as_plaintext(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        password = "plain-text-must-not-be-stored"
        email = "plaintext-check@example.com"

        response = register_user(
            client,
            email=email,
            password=password,
        )

        assert response.status_code == 201

        user = get_user_by_email(
            session_factory,
            email,
        )

        assert user is not None
        assert user.hashed_password != password
        assert password not in user.hashed_password
        assert verify_password(password, user.hashed_password)
"""Tests for the transaction endpoints.

Run from the project root with:

    pytest -q tests/test_transactions.py

The suite uses an isolated temporary SQLite database. The application's
real finance.db is never opened, created, or modified.
"""

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

# Make the app package importable when pytest is run from different locations.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.db.models import Budget, Transaction, User  # noqa: E402
from app.main import app  # noqa: E402


TRANSACTIONS_URL = "/api/transactions"

SessionFactory = Callable[[], Session]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TestUser:
    __test__ = False

    id: int
    email: str
    headers: dict[str, str]


def money(value: str | int | float | Decimal) -> Decimal:
    """Convert API/database money values to Decimal for exact assertions."""
    return Decimal(str(value))


def persist(session_factory: SessionFactory, *objects: object) -> None:
    with session_factory() as session:
        session.add_all(objects)
        session.commit()


def make_transaction(
    user_id: int,
    transaction_type: str,
    category: str,
    amount: str,
    transaction_date: date,
    description: str | None = None,
) -> Transaction:
    return Transaction(
        user_id=user_id,
        transaction_type=transaction_type,
        category=category,
        amount=Decimal(amount),
        description=description,
        transaction_date=transaction_date,
    )


def get_transaction_from_db(
    session_factory: sessionmaker[Session],
    transaction_id: int,
) -> Transaction | None:
    with session_factory() as session:
        return session.get(Transaction, transaction_id)


def create_database_user(
    session_factory: sessionmaker[Session],
    email: str,
    password: str = "test-password-123",
) -> TestUser:
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

    token = create_access_token(str(user_id))

    return TestUser(
        id=user_id,
        email=email,
        headers={"Authorization": f"Bearer {token}"},
    )


def create_transaction(
    client: TestClient,
    headers: dict[str, str],
    *,
    transaction_type: str = "expense",
    amount: str = "1200.50",
    category: str = "Food",
    description: str | None = "Lunch",
    transaction_date: str = "2026-10-05",
):
    payload = {
        "amount": amount,
        "transaction_type": transaction_type,
        "category": category,
        "description": description,
        "transaction_date": transaction_date,
    }

    return client.post(
        TRANSACTIONS_URL,
        json=payload,
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# Database / client fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    """Create a completely isolated SQLite database for transaction tests."""
    db_path = tmp_path_factory.mktemp("transactions_db") / "test_finance.db"

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
    """Ensure every transaction test starts with an empty database."""
    yield

    with session_factory() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Budget))
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


@pytest.fixture
def user_a(
    session_factory: sessionmaker[Session],
) -> TestUser:
    return create_database_user(
        session_factory,
        "transaction.user.a@example.com",
    )


@pytest.fixture
def user_b(
    session_factory: sessionmaker[Session],
) -> TestUser:
    return create_database_user(
        session_factory,
        "transaction.user.b@example.com",
    )


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class TestTransactionAuthentication:
    def test_create_without_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.post(
            TRANSACTIONS_URL,
            json={
                "amount": "100.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Test",
                "transaction_date": "2026-10-05",
            },
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_list_without_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(TRANSACTIONS_URL)

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_get_by_id_without_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(f"{TRANSACTIONS_URL}/1")

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_update_without_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.put(
            f"{TRANSACTIONS_URL}/1",
            json={
                "amount": "100.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Test",
                "transaction_date": "2026-10-05",
            },
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_delete_without_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.delete(f"{TRANSACTIONS_URL}/1")

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_invalid_bearer_token_returns_401(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(
            TRANSACTIONS_URL,
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Could not validate credentials"
        }


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
class TestCreateTransaction:
    def test_create_valid_income_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        response = create_transaction(
            client,
            user_a.headers,
            transaction_type="income",
            amount="50000.00",
            category="Salary",
            description="October salary",
            transaction_date="2026-10-01",
        )

        assert response.status_code == 201

        body = response.json()

        assert "id" in body
        assert body["user_id"] == user_a.id
        assert money(body["amount"]) == Decimal("50000.00")
        assert body["transaction_type"] == "income"
        assert body["category"] == "Salary"
        assert body["description"] == "October salary"
        assert body["transaction_date"] == "2026-10-01"

        transaction = get_transaction_from_db(
            session_factory,
            body["id"],
        )

        assert transaction is not None
        assert transaction.user_id == user_a.id
        assert transaction.amount == Decimal("50000.00")
        assert transaction.transaction_type == "income"
        assert transaction.category == "Salary"
        assert transaction.description == "October salary"
        assert transaction.transaction_date == date(2026, 10, 1)

    def test_create_valid_expense_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        response = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="1250.75",
            category="Food",
            description="Dinner",
            transaction_date="2026-10-05",
        )

        assert response.status_code == 201

        body = response.json()

        assert "id" in body
        assert body["user_id"] == user_a.id
        assert money(body["amount"]) == Decimal("1250.75")
        assert body["transaction_type"] == "expense"
        assert body["category"] == "Food"
        assert body["description"] == "Dinner"
        assert body["transaction_date"] == "2026-10-05"

        transaction = get_transaction_from_db(
            session_factory,
            body["id"],
        )

        assert transaction is not None
        assert transaction.user_id == user_a.id

    def test_create_transaction_cannot_assign_another_user(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
    ) -> None:
        response = client.post(
            TRANSACTIONS_URL,
            json={
                "user_id": user_b.id,
                "amount": "1000.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Attempted ownership override",
                "transaction_date": "2026-10-05",
            },
            headers=user_a.headers,
        )

        assert response.status_code == 201

        body = response.json()

        assert body["user_id"] == user_a.id
        assert body["user_id"] != user_b.id

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {
                "transaction_type": "expense",
                "category": "Food",
                "description": "Missing amount",
                "transaction_date": "2026-10-05",
            },
            {
                "amount": "100.00",
                "category": "Food",
                "description": "Missing type",
                "transaction_date": "2026-10-05",
            },
            {
                "amount": "100.00",
                "transaction_type": "expense",
                "description": "Missing category",
                "transaction_date": "2026-10-05",
            },
            {
                "amount": "100.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Missing date",
            },
        ],
    )
    def test_create_missing_required_fields_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        payload: dict,
    ) -> None:
        response = client.post(
            TRANSACTIONS_URL,
            json=payload,
            headers=user_a.headers,
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    def test_create_invalid_transaction_type_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = create_transaction(
            client,
            user_a.headers,
            transaction_type="transfer",
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "amount",
        [
            "not-a-number",
            "0",
            "-100.00",
        ],
    )
    def test_create_invalid_amount_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        amount: str,
    ) -> None:
        response = create_transaction(
            client,
            user_a.headers,
            amount=amount,
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "transaction_date",
        [
            "not-a-date",
            "2026-13-01",
            "2026-02-30",
        ],
    )
    def test_create_invalid_transaction_date_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        transaction_date: str,
    ) -> None:
        response = create_transaction(
            client,
            user_a.headers,
            transaction_date=transaction_date,
        )

        assert response.status_code == 422
        assert "detail" in response.json()


# --------------------------------------------------------------------------- #
# Read / list
# --------------------------------------------------------------------------- #
class TestReadTransactions:
    def test_authenticated_user_can_list_transactions(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="1200.00",
            category="Food",
            description="Lunch",
            transaction_date="2026-10-05",
        )

        assert created.status_code == 201

        response = client.get(
            TRANSACTIONS_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["user_id"] == user_a.id
        assert money(body[0]["amount"]) == Decimal("1200.00")
        assert body[0]["category"] == "Food"

    def test_user_sees_multiple_own_transactions(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        income = create_transaction(
            client,
            user_a.headers,
            transaction_type="income",
            amount="50000.00",
            category="Salary",
            description="October salary",
            transaction_date="2026-10-01",
        )

        expense = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="2500.50",
            category="Travel",
            description="Train ticket",
            transaction_date="2026-10-03",
        )

        assert income.status_code == 201
        assert expense.status_code == 201

        response = client.get(
            TRANSACTIONS_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert isinstance(body, list)
        assert len(body) == 2

        amounts = {
            money(item["amount"])
            for item in body
        }

        categories = {
            item["category"]
            for item in body
        }

        assert amounts == {
            Decimal("50000.00"),
            Decimal("2500.50"),
        }
        assert categories == {"Salary", "Travel"}
        assert all(item["user_id"] == user_a.id for item in body)

    def test_user_does_not_see_another_users_transactions(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
    ) -> None:
        transaction_a = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="1000.00",
            category="Food",
            description="User A food",
            transaction_date="2026-10-05",
        )

        transaction_b = create_transaction(
            client,
            user_b.headers,
            transaction_type="expense",
            amount="2000.00",
            category="Shopping",
            description="User B shopping",
            transaction_date="2026-10-06",
        )

        assert transaction_a.status_code == 201
        assert transaction_b.status_code == 201

        response_a = client.get(
            TRANSACTIONS_URL,
            headers=user_a.headers,
        )

        response_b = client.get(
            TRANSACTIONS_URL,
            headers=user_b.headers,
        )

        assert response_a.status_code == 200
        assert response_b.status_code == 200

        body_a = response_a.json()
        body_b = response_b.json()

        assert len(body_a) == 1
        assert len(body_b) == 1

        assert body_a[0]["user_id"] == user_a.id
        assert body_b[0]["user_id"] == user_b.id

        assert body_a[0]["id"] == transaction_a.json()["id"]
        assert body_b[0]["id"] == transaction_b.json()["id"]

    def test_user_can_retrieve_own_transaction_by_id(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="875.25",
            category="Entertainment",
            description="Movie",
            transaction_date="2026-10-07",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.get(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == transaction_id
        assert body["user_id"] == user_a.id
        assert money(body["amount"]) == Decimal("875.25")
        assert body["transaction_type"] == "expense"
        assert body["category"] == "Entertainment"
        assert body["description"] == "Movie"
        assert body["transaction_date"] == "2026-10-07"

    def test_get_nonexistent_transaction_returns_404(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.get(
            f"{TRANSACTIONS_URL}/999999",
            headers=user_a.headers,
        )

        assert response.status_code == 404

    def test_user_a_cannot_retrieve_user_b_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_b.headers,
            transaction_type="expense",
            amount="4500.00",
            category="Shopping",
            description="User B transaction",
            transaction_date="2026-10-08",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.get(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
class TestUpdateTransaction:
    def test_user_can_update_own_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="1200.00",
            category="Food",
            description="Original description",
            transaction_date="2026-10-05",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.put(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            json={
                "amount": "2500.75",
                "transaction_type": "expense",
                "category": "Travel",
                "description": "Updated description",
                "transaction_date": "2026-10-10",
            },
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == transaction_id
        assert body["user_id"] == user_a.id
        assert money(body["amount"]) == Decimal("2500.75")
        assert body["transaction_type"] == "expense"
        assert body["category"] == "Travel"
        assert body["description"] == "Updated description"
        assert body["transaction_date"] == "2026-10-10"

    def test_updated_transaction_is_persisted(
        self,
        client: TestClient,
        user_a: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="income",
            amount="10000.00",
            category="Freelance",
            description="Original",
            transaction_date="2026-10-01",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        update_response = client.put(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            json={
                "amount": "15000.50",
                "transaction_type": "income",
                "category": "Consulting",
                "description": "Updated",
                "transaction_date": "2026-10-12",
            },
            headers=user_a.headers,
        )

        assert update_response.status_code == 200

        transaction = get_transaction_from_db(
            session_factory,
            transaction_id,
        )

        assert transaction is not None
        assert transaction.user_id == user_a.id
        assert transaction.amount == Decimal("15000.50")
        assert transaction.transaction_type == "income"
        assert transaction.category == "Consulting"
        assert transaction.description == "Updated"
        assert transaction.transaction_date == date(2026, 10, 12)

    def test_updating_nonexistent_transaction_returns_404(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.put(
            f"{TRANSACTIONS_URL}/999999",
            json={
                "amount": "100.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Does not exist",
                "transaction_date": "2026-10-05",
            },
            headers=user_a.headers,
        )

        assert response.status_code == 404

    def test_user_a_cannot_update_user_b_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        created = create_transaction(
            client,
            user_b.headers,
            transaction_type="expense",
            amount="3000.00",
            category="Shopping",
            description="User B original",
            transaction_date="2026-10-06",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.put(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            json={
                "amount": "99999.99",
                "transaction_type": "income",
                "category": "Salary",
                "description": "Unauthorized update",
                "transaction_date": "2026-10-20",
            },
            headers=user_a.headers,
        )

        assert response.status_code == 404

        transaction = get_transaction_from_db(
            session_factory,
            transaction_id,
        )

        assert transaction is not None
        assert transaction.user_id == user_b.id
        assert transaction.amount == Decimal("3000.00")
        assert transaction.transaction_type == "expense"
        assert transaction.category == "Shopping"
        assert transaction.description == "User B original"
        assert transaction.transaction_date == date(2026, 10, 6)

    @pytest.mark.parametrize(
        "payload",
        [
            {
                "amount": "not-a-number",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Invalid amount",
                "transaction_date": "2026-10-05",
            },
            {
                "amount": "100.00",
                "transaction_type": "transfer",
                "category": "Food",
                "description": "Invalid type",
                "transaction_date": "2026-10-05",
            },
            {
                "amount": "100.00",
                "transaction_type": "expense",
                "category": "Food",
                "description": "Invalid date",
                "transaction_date": "not-a-date",
            },
        ],
    )
    def test_invalid_update_payload_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        payload: dict,
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.put(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            json=payload,
            headers=user_a.headers,
        )

        assert response.status_code == 422
        assert "detail" in response.json()


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
class TestDeleteTransaction:
    def test_user_can_delete_own_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="750.00",
            category="Food",
            description="To be deleted",
            transaction_date="2026-10-09",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.delete(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert response.status_code == 204

        assert get_transaction_from_db(
            session_factory,
            transaction_id,
        ) is None

    def test_deleted_transaction_is_not_retrievable(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="650.00",
            category="Entertainment",
            description="Delete me",
            transaction_date="2026-10-11",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        delete_response = client.delete(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert delete_response.status_code == 204

        get_response = client.get(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert get_response.status_code == 404

    def test_deleting_nonexistent_transaction_returns_404(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.delete(
            f"{TRANSACTIONS_URL}/999999",
            headers=user_a.headers,
        )

        assert response.status_code == 404

    def test_user_a_cannot_delete_user_b_transaction(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        session_factory: sessionmaker[Session],
    ) -> None:
        created = create_transaction(
            client,
            user_b.headers,
            transaction_type="expense",
            amount="1800.00",
            category="Shopping",
            description="User B protected transaction",
            transaction_date="2026-10-12",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        response = client.delete(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert response.status_code == 404

        transaction = get_transaction_from_db(
            session_factory,
            transaction_id,
        )

        assert transaction is not None
        assert transaction.user_id == user_b.id
        assert transaction.amount == Decimal("1800.00")
        assert transaction.category == "Shopping"

    def test_user_b_can_still_access_transaction_after_user_a_attempts_delete(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
    ) -> None:
        created = create_transaction(
            client,
            user_b.headers,
            transaction_type="income",
            amount="25000.00",
            category="Salary",
            description="User B salary",
            transaction_date="2026-10-01",
        )

        assert created.status_code == 201

        transaction_id = created.json()["id"]

        delete_response = client.delete(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_a.headers,
        )

        assert delete_response.status_code == 404

        get_response = client.get(
            f"{TRANSACTIONS_URL}/{transaction_id}",
            headers=user_b.headers,
        )

        assert get_response.status_code == 200

        body = get_response.json()

        assert body["id"] == transaction_id
        assert body["user_id"] == user_b.id
        assert money(body["amount"]) == Decimal("25000.00")
        assert body["transaction_type"] == "income"
        assert body["category"] == "Salary"


# --------------------------------------------------------------------------- #
# Cross-user ownership integration checks
# --------------------------------------------------------------------------- #
class TestTransactionOwnership:
    def test_users_are_fully_isolated(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
    ) -> None:
        a_income = create_transaction(
            client,
            user_a.headers,
            transaction_type="income",
            amount="50000.00",
            category="Salary",
            description="User A income",
            transaction_date="2026-10-01",
        )

        a_expense = create_transaction(
            client,
            user_a.headers,
            transaction_type="expense",
            amount="3000.00",
            category="Food",
            description="User A expense",
            transaction_date="2026-10-03",
        )

        b_income = create_transaction(
            client,
            user_b.headers,
            transaction_type="income",
            amount="40000.00",
            category="Salary",
            description="User B income",
            transaction_date="2026-10-01",
        )

        b_expense = create_transaction(
            client,
            user_b.headers,
            transaction_type="expense",
            amount="5000.00",
            category="Travel",
            description="User B expense",
            transaction_date="2026-10-04",
        )

        assert a_income.status_code == 201
        assert a_expense.status_code == 201
        assert b_income.status_code == 201
        assert b_expense.status_code == 201

        a_ids = {
            a_income.json()["id"],
            a_expense.json()["id"],
        }
        b_ids = {
            b_income.json()["id"],
            b_expense.json()["id"],
        }

        a_list = client.get(
            TRANSACTIONS_URL,
            headers=user_a.headers,
        )

        b_list = client.get(
            TRANSACTIONS_URL,
            headers=user_b.headers,
        )

        assert a_list.status_code == 200
        assert b_list.status_code == 200

        a_visible_ids = {
            item["id"]
            for item in a_list.json()
        }
        b_visible_ids = {
            item["id"]
            for item in b_list.json()
        }

        assert a_visible_ids == a_ids
        assert b_visible_ids == b_ids

        assert a_visible_ids.isdisjoint(b_ids)
        assert b_visible_ids.isdisjoint(a_ids)

        for transaction_id in b_ids:
            assert (
                client.get(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    headers=user_a.headers,
                ).status_code
                == 404
            )

            assert (
                client.put(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    json={
                        "amount": "99999.99",
                        "transaction_type": "expense",
                        "category": "Unauthorized",
                        "description": "Should never be applied",
                        "transaction_date": "2026-10-20",
                    },
                    headers=user_a.headers,
                ).status_code
                == 404
            )

            assert (
                client.delete(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    headers=user_a.headers,
                ).status_code
                == 404
            )

        for transaction_id in a_ids:
            assert (
                client.get(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    headers=user_b.headers,
                ).status_code
                == 404
            )

            assert (
                client.put(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    json={
                        "amount": "88888.88",
                        "transaction_type": "income",
                        "category": "Unauthorized",
                        "description": "Should never be applied",
                        "transaction_date": "2026-10-21",
                    },
                    headers=user_b.headers,
                ).status_code
                == 404
            )

            assert (
                client.delete(
                    f"{TRANSACTIONS_URL}/{transaction_id}",
                    headers=user_b.headers,
                ).status_code
                == 404
            )
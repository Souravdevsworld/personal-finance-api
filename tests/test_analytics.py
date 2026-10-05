"""Tests for the analytics endpoints.

Run from the project root (where the .env file lives) with:

    pytest -q tests/test_analytics.py

The suite uses an isolated temporary SQLite database. The developer's real
finance.db is never opened, created, or modified.
"""

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

# Make the `app` package importable even when pytest is not started with
# `python -m pytest` or a configured pythonpath.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.db.models import Budget, Transaction, User  # noqa: E402
from app.main import app  # noqa: E402


SUMMARY_URL = "/api/analytics/summary"
CATEGORIES_URL = "/api/analytics/categories"
TREND_URL = "/api/analytics/trend"
BUDGET_VS_ACTUAL_URL = "/api/analytics/budget-vs-actual"
SAVINGS_RATE_URL = "/api/analytics/savings-rate"

INVALID_MONTHS = ["2026-1", "2026-13", "2026-00", "202610", "abcd-10"]

SessionFactory = Callable[[], Session]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TestUser:
    __test__ = False  # Prevent pytest from trying to collect this class.

    id: int
    email: str
    headers: dict[str, str]


def money(value: str | int | float) -> Decimal:
    """Parse a JSON money value into Decimal (the API serialises Decimal as str)."""
    return Decimal(str(value))


def make_transaction(
    user_id: int,
    transaction_type: str,
    category: str,
    amount: str,
    transaction_date: date,
) -> Transaction:
    return Transaction(
        user_id=user_id,
        transaction_type=transaction_type,
        category=category,
        amount=Decimal(amount),
        description=None,
        transaction_date=transaction_date,
    )


def persist(session_factory: SessionFactory, *objects: object) -> None:
    with session_factory() as session:
        session.add_all(objects)
        session.commit()


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def by_category(items: list[dict]) -> dict[str, dict]:
    return {item["category"]: item for item in items}


# --------------------------------------------------------------------------- #
# Database / client fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    db_path = tmp_path_factory.mktemp("analytics_db") / "test_finance.db"
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
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_tables(session_factory: sessionmaker[Session]) -> Iterator[None]:
    """Give every test an empty database."""
    yield

    with session_factory() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Budget))
        session.execute(delete(User))
        session.commit()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
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


@pytest.fixture(scope="session")
def hashed_test_password() -> str:
    return hash_password("test-password-123")


def _create_user(
    session_factory: SessionFactory,
    email: str,
    hashed_password: str,
) -> TestUser:
    with session_factory() as session:
        user = User(email=email, hashed_password=hashed_password)
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


@pytest.fixture
def user_a(
    session_factory: sessionmaker[Session],
    hashed_test_password: str,
) -> TestUser:
    return _create_user(
        session_factory,
        "user.a@example.com",
        hashed_test_password,
    )


@pytest.fixture
def user_b(
    session_factory: sessionmaker[Session],
    hashed_test_password: str,
) -> TestUser:
    return _create_user(
        session_factory,
        "user.b@example.com",
        hashed_test_password,
    )


# --------------------------------------------------------------------------- #
# Deterministic seed data
#
# User A
#   2026-10: income Salary 50000 | expense Food 3000 + 1200
#             | expense Travel 5000
#   2026-09: income Salary 40000 | expense Rent 10000
#   Budgets: 2026-10 Food 5000, Travel 4000, Entertainment 1500
#            2026-09 Food 2000
#
#   All time:  income 90000, expenses 19200, balance 70800, count 6
#   2026-10:  income 50000, expenses 9200, balance 40800, count 4
#
# User B
#   2026-10: income Salary 10000 | expense Food 7000 | expense Gadgets 500
#   Budgets: 2026-10 Food 6000, Gadgets 400
# --------------------------------------------------------------------------- #
@pytest.fixture
def seeded(
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    a, b = user_a.id, user_b.id

    persist(
        session_factory,
        # User A transactions
        make_transaction(
            a, "income", "Salary", "50000.00", date(2026, 10, 1)
        ),
        make_transaction(
            a, "expense", "Food", "3000.00", date(2026, 10, 3)
        ),
        make_transaction(
            a, "expense", "Food", "1200.00", date(2026, 10, 10)
        ),
        make_transaction(
            a, "expense", "Travel", "5000.00", date(2026, 10, 15)
        ),
        make_transaction(
            a, "income", "Salary", "40000.00", date(2026, 9, 1)
        ),
        make_transaction(
            a, "expense", "Rent", "10000.00", date(2026, 9, 5)
        ),
        # User A budgets
        Budget(
            user_id=a,
            category="Food",
            amount=Decimal("5000.00"),
            month="2026-10",
        ),
        Budget(
            user_id=a,
            category="Travel",
            amount=Decimal("4000.00"),
            month="2026-10",
        ),
        Budget(
            user_id=a,
            category="Entertainment",
            amount=Decimal("1500.00"),
            month="2026-10",
        ),
        Budget(
            user_id=a,
            category="Food",
            amount=Decimal("2000.00"),
            month="2026-09",
        ),
        # User B transactions
        make_transaction(
            b, "income", "Salary", "10000.00", date(2026, 10, 2)
        ),
        make_transaction(
            b, "expense", "Food", "7000.00", date(2026, 10, 4)
        ),
        make_transaction(
            b, "expense", "Gadgets", "500.00", date(2026, 10, 6)
        ),
        # User B budgets
        Budget(
            user_id=b,
            category="Food",
            amount=Decimal("6000.00"),
            month="2026-10",
        ),
        Budget(
            user_id=b,
            category="Gadgets",
            amount=Decimal("400.00"),
            month="2026-10",
        ),
    )


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class TestAuthentication:
    @pytest.mark.parametrize(
        "url",
        [
            SUMMARY_URL,
            CATEGORIES_URL,
            TREND_URL,
            f"{BUDGET_VS_ACTUAL_URL}?month=2026-10",
            SAVINGS_RATE_URL,
        ],
    )
    def test_requires_token(
        self,
        client: TestClient,
        url: str,
    ) -> None:
        response = client.get(url)

        # assert response.status_code == 401
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    @pytest.mark.parametrize(
        "url",
        [
            SUMMARY_URL,
            CATEGORIES_URL,
            TREND_URL,
            f"{BUDGET_VS_ACTUAL_URL}?month=2026-10",
            SAVINGS_RATE_URL,
        ],
    )
    def test_rejects_invalid_token(
        self,
        client: TestClient,
        url: str,
    ) -> None:
        response = client.get(
            url,
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )

        assert response.status_code == 401

    def test_rejects_token_for_nonexistent_user(
        self,
        client: TestClient,
    ) -> None:
        token = create_access_token("999999")

        response = client.get(
            SUMMARY_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
class TestSummary:
    def test_all_time_summary(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("90000.00")
        assert money(body["total_expenses"]) == Decimal("19200.00")
        assert money(body["balance"]) == Decimal("70800.00")
        assert body["transaction_count"] == 6

    def test_month_filtered_summary(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("50000.00")
        assert money(body["total_expenses"]) == Decimal("9200.00")
        assert money(body["balance"]) == Decimal("40800.00")
        assert body["transaction_count"] == 4

    def test_other_month_summary(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            params={"month": "2026-09"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("40000.00")
        assert money(body["total_expenses"]) == Decimal("10000.00")
        assert money(body["balance"]) == Decimal("30000.00")
        assert body["transaction_count"] == 2

    def test_month_without_transactions_returns_zeros(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            params={"month": "2025-01"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("0.00")
        assert money(body["total_expenses"]) == Decimal("0.00")
        assert money(body["balance"]) == Decimal("0.00")
        assert body["transaction_count"] == 0

    def test_new_user_without_data_returns_zeros(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["balance"]) == Decimal("0.00")
        assert body["transaction_count"] == 0

    @pytest.mark.parametrize("month", INVALID_MONTHS)
    def test_invalid_month_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        month: str,
    ) -> None:
        response = client.get(
            SUMMARY_URL,
            params={"month": month},
            headers=user_a.headers,
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
class TestCategories:
    def test_all_time_category_totals(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        totals = {
            item["category"]: money(item["amount"])
            for item in response.json()
        }

        assert totals == {
            "Food": Decimal("4200.00"),
            "Travel": Decimal("5000.00"),
            "Rent": Decimal("10000.00"),
        }

    def test_results_are_sorted_by_amount_descending(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        assert [item["category"] for item in response.json()] == [
            "Rent",
            "Travel",
            "Food",
        ]

    def test_month_filtered_category_totals(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        totals = {
            item["category"]: money(item["amount"])
            for item in response.json()
        }

        assert totals == {
            "Food": Decimal("4200.00"),
            "Travel": Decimal("5000.00"),
        }

    def test_income_is_not_counted_as_expense_category(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        assert "Salary" not in {
            item["category"] for item in response.json()
        }

    def test_month_without_expenses_returns_empty_list(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            params={"month": "2025-01"},
            headers=user_a.headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("month", INVALID_MONTHS)
    def test_invalid_month_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        month: str,
    ) -> None:
        response = client.get(
            CATEGORIES_URL,
            params={"month": month},
            headers=user_a.headers,
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #
class TestTrend:
    """Trend windows are relative to 'now', so data is built relative to today."""

    @pytest.fixture
    def trend_data(
        self,
        session_factory: sessionmaker[Session],
        user_a: TestUser,
        user_b: TestUser,
    ) -> dict[int, tuple[int, int]]:
        today = datetime.now(timezone.utc).date()

        offsets = {
            offset: shift_month(today.year, today.month, -offset)
            for offset in range(0, 7)
        }

        def first_of(offset: int) -> date:
            year, month = offsets[offset]
            return date(year, month, 1)

        persist(
            session_factory,
            # User A
            make_transaction(
                user_a.id,
                "income",
                "Salary",
                "1000.00",
                first_of(0),
            ),
            make_transaction(
                user_a.id,
                "expense",
                "Food",
                "400.00",
                first_of(0),
            ),
            make_transaction(
                user_a.id,
                "expense",
                "Food",
                "100.50",
                first_of(0),
            ),
            make_transaction(
                user_a.id,
                "expense",
                "Rent",
                "250.00",
                first_of(2),
            ),
            make_transaction(
                user_a.id,
                "income",
                "Bonus",
                "300.00",
                first_of(5),
            ),
            make_transaction(
                user_a.id,
                "income",
                "Bonus",
                "999.00",
                first_of(6),
            ),
            # User B
            make_transaction(
                user_b.id,
                "income",
                "Salary",
                "77777.00",
                first_of(0),
            ),
            make_transaction(
                user_b.id,
                "expense",
                "Food",
                "5555.00",
                first_of(1),
            ),
        )

        return offsets

    def test_default_returns_six_months_in_order(
        self,
        client: TestClient,
        user_a: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        response = client.get(
            TREND_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        expected_months = [
            month_label(*trend_data[offset])
            for offset in range(5, -1, -1)
        ]

        assert [item["month"] for item in body] == expected_months

    def test_trend_values_for_user_a(
        self,
        client: TestClient,
        user_a: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": 6},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        trend = {
            item["month"]: (
                money(item["income"]),
                money(item["expenses"]),
            )
            for item in response.json()
        }

        zero = Decimal("0.00")

        assert trend[month_label(*trend_data[0])] == (
            Decimal("1000.00"),
            Decimal("500.50"),
        )
        assert trend[month_label(*trend_data[1])] == (zero, zero)
        assert trend[month_label(*trend_data[2])] == (
            zero,
            Decimal("250.00"),
        )
        assert trend[month_label(*trend_data[3])] == (zero, zero)
        assert trend[month_label(*trend_data[4])] == (zero, zero)
        assert trend[month_label(*trend_data[5])] == (
            Decimal("300.00"),
            zero,
        )

    def test_months_without_transactions_are_included_as_zero(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": 4},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 4

        for item in body:
            assert money(item["income"]) == Decimal("0.00")
            assert money(item["expenses"]) == Decimal("0.00")

    def test_months_one_returns_only_current_month(
        self,
        client: TestClient,
        user_a: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": 1},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["month"] == month_label(*trend_data[0])
        assert money(body[0]["income"]) == Decimal("1000.00")
        assert money(body[0]["expenses"]) == Decimal("500.50")

    def test_months_twelve_includes_older_data(
        self,
        client: TestClient,
        user_a: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": 12},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 12

        trend = {
            item["month"]: money(item["income"])
            for item in body
        }

        assert trend[month_label(*trend_data[6])] == Decimal("999.00")

    def test_smaller_window_excludes_older_data(
        self,
        client: TestClient,
        user_a: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": 3},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert [item["month"] for item in body] == [
            month_label(*trend_data[2]),
            month_label(*trend_data[1]),
            month_label(*trend_data[0]),
        ]

        assert sum(
            money(item["income"])
            for item in body
        ) == Decimal("1000.00")

    def test_other_users_data_is_not_included(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        trend_data: dict[int, tuple[int, int]],
    ) -> None:
        body_a = client.get(
            TREND_URL,
            headers=user_a.headers,
        ).json()

        body_b = client.get(
            TREND_URL,
            headers=user_b.headers,
        ).json()

        assert Decimal("77777.00") not in {
            money(item["income"]) for item in body_a
        }
        assert Decimal("5555.00") not in {
            money(item["expenses"]) for item in body_a
        }

        trend_b = {
            item["month"]: item
            for item in body_b
        }

        current = trend_b[month_label(*trend_data[0])]
        previous = trend_b[month_label(*trend_data[1])]

        assert money(current["income"]) == Decimal("77777.00")
        assert money(previous["expenses"]) == Decimal("5555.00")

        # None of user A's figures appear for user B.
        assert money(current["expenses"]) == Decimal("0.00")

    @pytest.mark.parametrize("months", [0, 13, -1])
    def test_months_out_of_range_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        months: int,
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": months},
            headers=user_a.headers,
        )

        assert response.status_code == 422

    def test_non_integer_months_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.get(
            TREND_URL,
            params={"months": "abc"},
            headers=user_a.headers,
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Budget vs actual
# --------------------------------------------------------------------------- #
class TestBudgetVsActual:
    def test_budget_vs_actual_values(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        items = by_category(response.json())

        food = items["Food"]

        assert money(food["budget"]) == Decimal("5000.00")
        assert money(food["spent"]) == Decimal("4200.00")
        assert money(food["remaining"]) == Decimal("800.00")
        assert money(food["percentage_used"]) == Decimal("84.00")

    def test_overspending_is_not_clamped(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        travel = by_category(response.json())["Travel"]

        assert money(travel["budget"]) == Decimal("4000.00")
        assert money(travel["spent"]) == Decimal("5000.00")
        assert money(travel["remaining"]) == Decimal("-1000.00")
        assert money(travel["percentage_used"]) == Decimal("125.00")

    def test_budget_without_spending(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        entertainment = by_category(response.json())["Entertainment"]

        assert money(entertainment["budget"]) == Decimal("1500.00")
        assert money(entertainment["spent"]) == Decimal("0.00")
        assert money(entertainment["remaining"]) == Decimal("1500.00")
        assert money(entertainment["percentage_used"]) == Decimal("0.00")

    def test_only_budgets_for_requested_month_are_returned(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        items = response.json()

        assert {item["category"] for item in items} == {
            "Food",
            "Travel",
            "Entertainment",
        }
        assert len(items) == 3

    def test_spending_from_other_months_is_not_counted(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-09"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        items = response.json()

        assert len(items) == 1

        food = items[0]

        assert food["category"] == "Food"
        assert money(food["budget"]) == Decimal("2000.00")
        assert money(food["spent"]) == Decimal("0.00")
        assert money(food["remaining"]) == Decimal("2000.00")
        assert money(food["percentage_used"]) == Decimal("0.00")

    def test_month_without_budgets_returns_empty_list(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2025-01"},
            headers=user_a.headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_zero_budget_does_not_divide_by_zero(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        user_a: TestUser,
    ) -> None:
        persist(
            session_factory,
            Budget(
                user_id=user_a.id,
                category="Misc",
                amount=Decimal("0.00"),
                month="2026-10",
            ),
            make_transaction(
                user_a.id,
                "expense",
                "Misc",
                "50.00",
                date(2026, 10, 5),
            ),
        )

        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        misc = by_category(response.json())["Misc"]

        assert money(misc["budget"]) == Decimal("0.00")
        assert money(misc["spent"]) == Decimal("50.00")
        assert money(misc["remaining"]) == Decimal("-50.00")
        assert money(misc["percentage_used"]) == Decimal("0.00")

    def test_income_is_not_counted_as_spending(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        user_a: TestUser,
    ) -> None:
        persist(
            session_factory,
            Budget(
                user_id=user_a.id,
                category="Salary",
                amount=Decimal("100.00"),
                month="2026-10",
            ),
            make_transaction(
                user_a.id,
                "income",
                "Salary",
                "5000.00",
                date(2026, 10, 1),
            ),
        )

        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        salary = by_category(response.json())["Salary"]

        assert money(salary["spent"]) == Decimal("0.00")

    def test_other_users_budgets_and_spending_are_excluded(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        items = by_category(response.json())

        # User B's Gadgets budget must not appear for User A.
        assert "Gadgets" not in items

        # User B's Food budget/spending must not leak into User A.
        assert money(items["Food"]["budget"]) == Decimal("5000.00")
        assert money(items["Food"]["spent"]) == Decimal("4200.00")

    def test_user_b_sees_only_their_own_figures(
        self,
        client: TestClient,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_b.headers,
        )

        assert response.status_code == 200

        items = by_category(response.json())

        assert set(items) == {"Food", "Gadgets"}

        food = items["Food"]

        assert money(food["budget"]) == Decimal("6000.00")
        assert money(food["spent"]) == Decimal("7000.00")
        assert money(food["remaining"]) == Decimal("-1000.00")
        assert money(food["percentage_used"]) == Decimal("116.67")

        gadgets = items["Gadgets"]

        assert money(gadgets["budget"]) == Decimal("400.00")
        assert money(gadgets["spent"]) == Decimal("500.00")
        assert money(gadgets["remaining"]) == Decimal("-100.00")
        assert money(gadgets["percentage_used"]) == Decimal("125.00")

    def test_month_is_required(
        self,
        client: TestClient,
        user_a: TestUser,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("month", INVALID_MONTHS)
    def test_invalid_month_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        month: str,
    ) -> None:
        response = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": month},
            headers=user_a.headers,
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Savings rate
# --------------------------------------------------------------------------- #
class TestSavingsRate:
    def test_month_filtered_savings_rate(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("50000.00")
        assert money(body["total_expenses"]) == Decimal("9200.00")
        assert money(body["savings"]) == Decimal("40800.00")
        assert money(body["savings_rate"]) == Decimal("81.60")

    def test_all_time_savings_rate_is_rounded_to_two_places(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SAVINGS_RATE_URL,
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("90000.00")
        assert money(body["total_expenses"]) == Decimal("19200.00")
        assert money(body["savings"]) == Decimal("70800.00")

        # 70800 / 90000 * 100 = 78.666... -> 78.67
        assert money(body["savings_rate"]) == Decimal("78.67")

    def test_zero_income_returns_zero_rate(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        user_a: TestUser,
    ) -> None:
        persist(
            session_factory,
            make_transaction(
                user_a.id,
                "expense",
                "Food",
                "100.00",
                date(2026, 8, 10),
            ),
        )

        response = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2026-08"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("0.00")
        assert money(body["total_expenses"]) == Decimal("100.00")
        assert money(body["savings"]) == Decimal("-100.00")
        assert money(body["savings_rate"]) == Decimal("0.00")

    def test_month_without_transactions_returns_zeros(
        self,
        client: TestClient,
        user_a: TestUser,
        seeded: None,
    ) -> None:
        response = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2025-01"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["total_income"]) == Decimal("0.00")
        assert money(body["total_expenses"]) == Decimal("0.00")
        assert money(body["savings"]) == Decimal("0.00")
        assert money(body["savings_rate"]) == Decimal("0.00")

    def test_negative_savings_rate_when_expenses_exceed_income(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        user_a: TestUser,
    ) -> None:
        persist(
            session_factory,
            make_transaction(
                user_a.id,
                "income",
                "Salary",
                "1000.00",
                date(2026, 7, 1),
            ),
            make_transaction(
                user_a.id,
                "expense",
                "Rent",
                "1500.00",
                date(2026, 7, 2),
            ),
        )

        response = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2026-07"},
            headers=user_a.headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert money(body["savings"]) == Decimal("-500.00")
        assert money(body["savings_rate"]) == Decimal("-50.00")

    @pytest.mark.parametrize("month", INVALID_MONTHS)
    def test_invalid_month_returns_422(
        self,
        client: TestClient,
        user_a: TestUser,
        month: str,
    ) -> None:
        response = client.get(
            SAVINGS_RATE_URL,
            params={"month": month},
            headers=user_a.headers,
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Ownership / data isolation
# --------------------------------------------------------------------------- #
class TestDataIsolation:
    def test_summary_is_isolated_per_user(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        body_a = client.get(
            SUMMARY_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        ).json()

        body_b = client.get(
            SUMMARY_URL,
            params={"month": "2026-10"},
            headers=user_b.headers,
        ).json()

        assert money(body_a["total_income"]) == Decimal("50000.00")
        assert money(body_a["total_expenses"]) == Decimal("9200.00")
        assert body_a["transaction_count"] == 4

        assert money(body_b["total_income"]) == Decimal("10000.00")
        assert money(body_b["total_expenses"]) == Decimal("7500.00")
        assert money(body_b["balance"]) == Decimal("2500.00")
        assert body_b["transaction_count"] == 3

    def test_all_time_summary_is_isolated_per_user(
        self,
        client: TestClient,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        body = client.get(
            SUMMARY_URL,
            headers=user_b.headers,
        ).json()

        assert money(body["total_income"]) == Decimal("10000.00")
        assert money(body["total_expenses"]) == Decimal("7500.00")
        assert body["transaction_count"] == 3

    def test_categories_are_isolated_per_user(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        totals_a = {
            item["category"]: money(item["amount"])
            for item in client.get(
                CATEGORIES_URL,
                headers=user_a.headers,
            ).json()
        }

        totals_b = {
            item["category"]: money(item["amount"])
            for item in client.get(
                CATEGORIES_URL,
                headers=user_b.headers,
            ).json()
        }

        assert "Gadgets" not in totals_a
        assert totals_a["Food"] == Decimal("4200.00")

        assert totals_b == {
            "Food": Decimal("7000.00"),
            "Gadgets": Decimal("500.00"),
        }

    def test_savings_rate_is_isolated_per_user(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        seeded: None,
    ) -> None:
        body_a = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2026-10"},
            headers=user_a.headers,
        ).json()

        body_b = client.get(
            SAVINGS_RATE_URL,
            params={"month": "2026-10"},
            headers=user_b.headers,
        ).json()

        assert money(body_a["total_income"]) == Decimal("50000.00")
        assert money(body_a["total_expenses"]) == Decimal("9200.00")
        assert money(body_a["savings"]) == Decimal("40800.00")
        assert money(body_a["savings_rate"]) == Decimal("81.60")

        assert money(body_b["total_income"]) == Decimal("10000.00")
        assert money(body_b["total_expenses"]) == Decimal("7500.00")
        assert money(body_b["savings"]) == Decimal("2500.00")
        assert money(body_b["savings_rate"]) == Decimal("25.00")

    def test_user_without_data_sees_nothing_from_other_users(
        self,
        client: TestClient,
        user_a: TestUser,
        user_b: TestUser,
        hashed_test_password: str,
        session_factory: sessionmaker[Session],
        seeded: None,
    ) -> None:
        user_c = _create_user(
            session_factory,
            "user.c@example.com",
            hashed_test_password,
        )

        summary = client.get(
            SUMMARY_URL,
            headers=user_c.headers,
        ).json()

        categories = client.get(
            CATEGORIES_URL,
            headers=user_c.headers,
        ).json()

        budgets = client.get(
            BUDGET_VS_ACTUAL_URL,
            params={"month": "2026-10"},
            headers=user_c.headers,
        ).json()

        assert money(summary["total_income"]) == Decimal("0.00")
        assert summary["transaction_count"] == 0
        assert categories == []
        assert budgets == []


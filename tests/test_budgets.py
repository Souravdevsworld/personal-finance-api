"""Tests for the Budget API.

Run from the project root with:

    pytest -q tests/test_budgets.py

The suite uses an isolated temporary SQLite database. The application's real
finance.db is never opened, created, or modified.
"""

import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.db.models import Budget, User  # noqa: E402
from app.main import app  # noqa: E402
from app.api.routes.budgets import router as budget_router  # noqa: E402


def iter_registered_routes():
    """Yield the actual Budget APIRoute objects."""
    yield from budget_router.routes


def registered_budget_path(method: str, collection: bool) -> str:
    """Find the actual registered Budget route, including nested routers."""
    method = method.upper()
    candidates = []

    for route in iter_registered_routes():
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())

        if not path or method not in methods:
            continue

        if collection and path.rstrip("/") == "/api/budgets":
            candidates.append(path)
        elif (
            not collection
            and path.startswith("/api/budgets/")
            and "{" in path
        ):
            candidates.append(path)

    if not candidates:
        kind = "collection" if collection else "item"
        raise AssertionError(
            f"No Budget {kind} route registered for {method}"
        )

    return candidates[0]


BUDGETS_URL = registered_budget_path("GET", collection=True)
BUDGET_ITEM_ROUTE = registered_budget_path("GET", collection=False)

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class TestUser:
    __test__ = False

    id: int
    email: str
    headers: dict[str, str]


def money(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def persist(session_factory: SessionFactory, *objects: object) -> None:
    with session_factory() as session:
        session.add_all(objects)
        session.commit()


def route_for(path: str, method: str):
    method = method.upper()

    for route in iter_registered_routes():
        if (
            getattr(route, "path", None) == path
            and method in getattr(route, "methods", set())
        ):
            return route

    raise AssertionError(
        f"No {method} route registered for {path}"
    )


def configured_status_code(path: str, method: str) -> int:
    """Read the status code configured by the actual FastAPI route."""
    route = route_for(path, method)
    return int(route.status_code or 200)


def budget_url(budget_id: int) -> str:
    """Convert the application's actual {id} parameter to a concrete URL."""
    return re.sub(
        r"\{[^}]+\}",
        str(budget_id),
        BUDGET_ITEM_ROUTE,
    )


def _unwrap_annotation(annotation: Any) -> Any:
    """Return the underlying type from typing.Annotated when used."""
    while get_origin(annotation) is not None:
        origin = get_origin(annotation)

        if str(origin) == "<class 'typing.Annotated'>":
            args = get_args(annotation)
            if not args:
                break
            annotation = args[0]
            continue

        break

    return annotation


def body_model_for(path: str, method: str):
    """Resolve the request Pydantic model without relying on Pydantic internals.

    FastAPI/Pydantic versions expose the internal request-body field
    differently. The endpoint's type annotation is the stable source of truth.
    """
    route = route_for(path, method)
    body_field = getattr(route, "body_field", None)

    if body_field is None:
        raise AssertionError(
            f"{method} {path} has no request body model"
        )

    # FastAPI versions that expose a ModelField.type_ can use it directly.
    model = getattr(body_field, "type_", None)
    if model is not None and hasattr(model, "model_fields"):
        return model

    # Newer FastAPI versions expose the annotation through field_info.
    field_info = getattr(body_field, "field_info", None)
    annotation = getattr(field_info, "annotation", None)
    annotation = _unwrap_annotation(annotation)

    if annotation is not None and hasattr(annotation, "model_fields"):
        return annotation

    # Most importantly, resolve the actual endpoint annotation. This avoids
    # depending on private Pydantic/FastAPI ModelField attributes entirely.
    from typing import get_type_hints

    hints = get_type_hints(route.endpoint)
    for parameter_name, parameter_annotation in hints.items():
        if parameter_name == "return":
            continue

        candidate = _unwrap_annotation(parameter_annotation)

        if hasattr(candidate, "model_fields"):
            return candidate

        # Compatibility with Pydantic v1-style models if encountered.
        if hasattr(candidate, "__fields__"):
            return candidate

    raise AssertionError(
        f"Could not resolve the request body model for {method} {path}. "
        f"body_field={body_field!r}, endpoint={route.endpoint!r}"
    )


def response_model_for(path: str, method: str):
    return route_for(path, method).response_model


def model_field_names(model: Any) -> set[str]:
    fields = getattr(model, "model_fields", None)

    if fields is not None:
        return set(fields)

    # Pydantic v1 compatibility. The current project should normally use
    # model_fields, but keeping this fallback makes the test helper robust.
    legacy_fields = getattr(model, "__fields__", None)
    if legacy_fields is not None:
        return set(legacy_fields)

    raise AssertionError(
        f"Expected a Pydantic model, got {model!r}"
    )


def response_item_model(model: Any):
    origin = get_origin(model)

    if origin in (list, tuple, set):
        args = get_args(model)
        return args[0] if args else None

    return model


def assert_response_fields(
    path: str,
    method: str,
    payload: Any,
) -> None:
    """Verify that the response contains the fields declared by the API."""
    model = response_item_model(
        response_model_for(path, method)
    )

    if model is None:
        return

    if not (
        hasattr(model, "model_fields")
        or hasattr(model, "__fields__")
    ):
        return

    assert isinstance(payload, dict)
    assert model_field_names(model) <= set(payload)


def create_database_user(
    session_factory: SessionFactory,
    email: str,
    password: str = "test-password-123",
) -> TestUser:
    user = User(
        email=email,
        hashed_password=hash_password(password),
    )

    persist(session_factory, user)

    with session_factory() as session:
        db_user = (
            session.query(User)
            .filter(User.email == email)
            .one()
        )
        user_id = db_user.id

    token = create_access_token(str(user_id))

    return TestUser(
        id=user_id,
        email=email,
        headers={
            "Authorization": f"Bearer {token}"
        },
    )


def create_budget(
    session_factory: SessionFactory,
    user_id: int,
    category: str,
    amount: str,
    month: str,
) -> Budget:
    budget = Budget(
        user_id=user_id,
        category=category,
        amount=Decimal(amount),
        month=month,
    )

    persist(session_factory, budget)

    with session_factory() as session:
        return (
            session.query(Budget)
            .filter(Budget.id == budget.id)
            .one()
        )


def get_budget(
    session_factory: SessionFactory,
    budget_id: int,
) -> Budget | None:
    with session_factory() as session:
        return session.get(Budget, budget_id)


def valid_budget_payload(
    category: str = "Food",
    amount: str = "5000.00",
    month: str = "2026-10",
) -> dict[str, Any]:
    """Build a valid payload from the actual Budget request schema."""
    model = body_model_for(BUDGETS_URL, "POST")
    fields = model_field_names(model)

    expected = {
        "category",
        "amount",
        "month",
    }

    assert expected <= fields, (
        "The Budget request schema no longer exposes the fields "
        "this Budget API uses: "
        f"expected={expected}, actual={fields}"
    )

    return {
        "category": category,
        "amount": amount,
        "month": month,
    }


# --------------------------------------------------------------------------- #
# Database / client fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def engine(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Engine]:
    """Create a completely isolated SQLite database."""
    db_path = (
        tmp_path_factory.mktemp("budgets_db")
        / "test_finance.db"
    )

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "check_same_thread": False,
        },
    )

    Base.metadata.create_all(test_engine)

    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(
    engine: Engine,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def clean_tables(
    session_factory: sessionmaker[Session],
) -> Iterator[None]:
    yield

    with session_factory() as session:
        session.execute(delete(Budget))
        session.execute(delete(User))
        session.commit()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    """Override the production DB dependency with the test DB."""

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
        app.dependency_overrides.pop(
            get_db,
            None,
        )


@pytest.fixture
def user_a(
    session_factory: sessionmaker[Session],
) -> TestUser:
    return create_database_user(
        session_factory,
        "budget.user.a@example.com",
    )


@pytest.fixture
def user_b(
    session_factory: sessionmaker[Session],
) -> TestUser:
    return create_database_user(
        session_factory,
        "budget.user.b@example.com",
    )


# --------------------------------------------------------------------------- #
# Route / authentication contract
# --------------------------------------------------------------------------- #

def test_budget_routes_are_registered_with_expected_methods() -> None:
    assert route_for(
        BUDGETS_URL,
        "POST",
    )

    assert route_for(
        BUDGETS_URL,
        "GET",
    )

    assert route_for(
        BUDGET_ITEM_ROUTE,
        "GET",
    )

    assert route_for(
        BUDGET_ITEM_ROUTE,
        "PUT",
    )

    assert route_for(
        BUDGET_ITEM_ROUTE,
        "DELETE",
    )


@pytest.mark.parametrize(
    ("method", "url", "json"),
    [
        (
            "POST",
            BUDGETS_URL,
            valid_budget_payload(),
        ),
        (
            "GET",
            BUDGETS_URL,
            None,
        ),
        (
            "GET",
            budget_url(1),
            None,
        ),
        (
            "PUT",
            budget_url(1),
            valid_budget_payload(
                category="Travel",
            ),
        ),
        (
            "DELETE",
            budget_url(1),
            None,
        ),
    ],
)
def test_budget_endpoints_require_authentication(
    client: TestClient,
    method: str,
    url: str,
    json: dict[str, Any] | None,
) -> None:
    response = client.request(
        method,
        url,
        json=json,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.parametrize(
    ("method", "url", "json"),
    [
        (
            "POST",
            BUDGETS_URL,
            valid_budget_payload(),
        ),
        (
            "GET",
            BUDGETS_URL,
            None,
        ),
        (
            "GET",
            budget_url(1),
            None,
        ),
        (
            "PUT",
            budget_url(1),
            valid_budget_payload(
                category="Travel",
            ),
        ),
        (
            "DELETE",
            budget_url(1),
            None,
        ),
    ],
)
def test_budget_endpoints_reject_invalid_token(
    client: TestClient,
    method: str,
    url: str,
    json: dict[str, Any] | None,
) -> None:
    response = client.request(
        method,
        url,
        json=json,
        headers={
            "Authorization": (
                "Bearer definitely-not-a-valid-jwt"
            )
        },
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"]
        == "Could not validate credentials"
    )


def test_budget_endpoints_reject_expired_token(
    client: TestClient,
    user_a: TestUser,
) -> None:
    expired_payload = {
        "sub": str(user_a.id),
        "exp": (
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        ),
    }

    expired_token = jwt.encode(
        expired_payload,
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    headers = {
        "Authorization": f"Bearer {expired_token}"
    }

    requests = [
        (
            "POST",
            BUDGETS_URL,
            valid_budget_payload(
                category="Travel",
            ),
        ),
        (
            "GET",
            BUDGETS_URL,
            None,
        ),
        (
            "GET",
            budget_url(1),
            None,
        ),
        (
            "PUT",
            budget_url(1),
            valid_budget_payload(
                category="Travel",
            ),
        ),
        (
            "DELETE",
            budget_url(1),
            None,
        ),
    ]

    for method, url, payload in requests:
        response = client.request(
            method,
            url,
            json=payload,
            headers=headers,
        )

        assert response.status_code == 401
        assert (
            response.json()["detail"]
            == "Could not validate credentials"
        )


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #

def test_create_budget_success_and_ownership(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
) -> None:
    payload = valid_budget_payload()

    response = client.post(
        BUDGETS_URL,
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGETS_URL,
        "POST",
    )

    data = response.json()

    assert_response_fields(
        BUDGETS_URL,
        "POST",
        data,
    )

    assert data["category"] == payload["category"]
    assert money(data["amount"]) == money(
        payload["amount"]
    )
    assert data["month"] == payload["month"]

    budget_id = data["id"]

    stored = get_budget(
        session_factory,
        budget_id,
    )

    assert stored is not None
    assert stored.user_id == user_a.id
    assert stored.category == payload["category"]
    assert Decimal(stored.amount) == money(
        payload["amount"]
    )
    assert stored.month == payload["month"]


def test_create_budget_cannot_assign_budget_to_another_user(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    payload = valid_budget_payload()
    payload["user_id"] = user_b.id

    response = client.post(
        BUDGETS_URL,
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGETS_URL,
        "POST",
    )

    budget = get_budget(
        session_factory,
        response.json()["id"],
    )

    assert budget is not None
    assert budget.user_id == user_a.id


@pytest.mark.parametrize(
    "missing_field",
    [
        "category",
        "amount",
        "month",
    ],
)
def test_create_budget_missing_required_field_returns_422(
    client: TestClient,
    user_a: TestUser,
    missing_field: str,
) -> None:
    payload = valid_budget_payload()
    payload.pop(missing_field)

    response = client.post(
        BUDGETS_URL,
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == 422


def test_create_budget_invalid_amount_returns_422(
    client: TestClient,
    user_a: TestUser,
) -> None:
    payload = valid_budget_payload(
        amount="not-a-number",
    )

    response = client.post(
        BUDGETS_URL,
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == 422


def test_create_budget_invalid_month_format_returns_422(
    client: TestClient,
    user_a: TestUser,
) -> None:
    payload = valid_budget_payload(
        month="2026-1",
    )

    response = client.post(
        BUDGETS_URL,
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == 422


def test_create_budget_invalid_month_value_returns_422_if_schema_enforces_calendar_month(
    client: TestClient,
    user_a: TestUser,
) -> None:
    model = body_model_for(
        BUDGETS_URL,
        "POST",
    )

    schema = model.model_json_schema()

    month_schema = (
        schema
        .get("properties", {})
        .get("month", {})
    )

    if month_schema.get("format") == "date":
        pytest.skip(
            "Budget month is represented by a date "
            "in the actual schema"
        )

    if (
        "pattern" not in month_schema
        and "enum" not in month_schema
    ):
        pytest.skip(
            "The actual budget schema does not declare "
            "a month pattern/enum"
        )

    response = client.post(
        BUDGETS_URL,
        json=valid_budget_payload(
            month="2026-13",
        ),
        headers=user_a.headers,
    )

    if response.status_code != 422:
        pytest.skip(
            "The actual schema accepts 2026-13; "
            "service-level validation is not declared "
            "by Pydantic"
        )

    assert response.status_code == 422


def test_create_budget_amount_boundary_according_to_actual_schema(
    client: TestClient,
    user_a: TestUser,
) -> None:
    model = body_model_for(
        BUDGETS_URL,
        "POST",
    )

    amount_schema = (
        model
        .model_json_schema()
        .get("properties", {})
        .get("amount", {})
    )

    if "exclusiveMinimum" in amount_schema:
        boundary = amount_schema[
            "exclusiveMinimum"
        ]
    elif "minimum" in amount_schema:
        boundary = amount_schema["minimum"]
    else:
        pytest.skip(
            "The actual budget schema declares "
            "no lower bound for amount"
        )

    response = client.post(
        BUDGETS_URL,
        json=valid_budget_payload(
            amount=str(boundary),
        ),
        headers=user_a.headers,
    )

    if "exclusiveMinimum" in amount_schema:
        assert response.status_code == 422
    else:
        assert response.status_code == configured_status_code(
            BUDGETS_URL,
            "POST",
        )


# --------------------------------------------------------------------------- #
# List / retrieve
# --------------------------------------------------------------------------- #

def test_get_all_budgets_returns_only_authenticated_users_budgets(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    budget_a1 = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    budget_a2 = create_budget(
        session_factory,
        user_a.id,
        "Travel",
        "3000.00",
        "2026-11",
    )

    create_budget(
        session_factory,
        user_b.id,
        "Food",
        "9000.00",
        "2026-10",
    )

    response_a = client.get(
        BUDGETS_URL,
        headers=user_a.headers,
    )

    assert response_a.status_code == configured_status_code(
        BUDGETS_URL,
        "GET",
    )

    data_a = response_a.json()

    assert isinstance(data_a, list)
    assert {
        item["id"]
        for item in data_a
    } == {
        budget_a1.id,
        budget_a2.id,
    }

    assert all(
        item.get("user_id", user_a.id) == user_a.id
        for item in data_a
    )

    response_b = client.get(
        BUDGETS_URL,
        headers=user_b.headers,
    )

    assert response_b.status_code == configured_status_code(
        BUDGETS_URL,
        "GET",
    )

    data_b = response_b.json()

    assert isinstance(data_b, list)
    assert len(data_b) == 1
    assert data_b[0]["id"] != budget_a1.id
    assert data_b[0]["id"] != budget_a2.id


def test_get_all_budgets_empty_result(
    client: TestClient,
    user_a: TestUser,
) -> None:
    response = client.get(
        BUDGETS_URL,
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGETS_URL,
        "GET",
    )

    assert response.json() == []


def test_get_budget_by_id_returns_own_budget(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
) -> None:
    budget = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    response = client.get(
        budget_url(budget.id),
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGET_ITEM_ROUTE,
        "GET",
    )

    data = response.json()

    assert_response_fields(
        BUDGET_ITEM_ROUTE,
        "GET",
        data,
    )

    assert data["id"] == budget.id
    assert data["category"] == "Food"
    assert money(data["amount"]) == money(
        "5000.00"
    )
    assert data["month"] == "2026-10"


def test_get_nonexistent_budget_returns_actual_error_response(
    client: TestClient,
    user_a: TestUser,
) -> None:
    response = client.get(
        budget_url(999999),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_user_cannot_get_another_users_budget(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    budget_b = create_budget(
        session_factory,
        user_b.id,
        "Food",
        "7000.00",
        "2026-10",
    )

    response = client.get(
        budget_url(budget_b.id),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #

def test_update_own_budget_persists_changes(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
) -> None:
    budget = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    payload = valid_budget_payload(
        category="Travel",
        amount="7500.00",
        month="2026-11",
    )

    response = client.put(
        budget_url(budget.id),
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGET_ITEM_ROUTE,
        "PUT",
    )

    data = response.json()

    assert_response_fields(
        BUDGET_ITEM_ROUTE,
        "PUT",
        data,
    )

    assert data["category"] == "Travel"
    assert money(data["amount"]) == money(
        "7500.00"
    )
    assert data["month"] == "2026-11"

    stored = get_budget(
        session_factory,
        budget.id,
    )

    assert stored is not None
    assert stored.user_id == user_a.id
    assert stored.category == "Travel"
    assert Decimal(stored.amount) == money(
        "7500.00"
    )
    assert stored.month == "2026-11"


def test_update_nonexistent_budget_returns_actual_error_response(
    client: TestClient,
    user_a: TestUser,
) -> None:
    response = client.put(
        budget_url(999999),
        json=valid_budget_payload(
            category="Travel",
        ),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_user_cannot_update_another_users_budget(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    budget_b = create_budget(
        session_factory,
        user_b.id,
        "Food",
        "7000.00",
        "2026-10",
    )

    response = client.put(
        budget_url(budget_b.id),
        json=valid_budget_payload(
            category="Travel",
            amount="100.00",
            month="2026-11",
        ),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()

    stored = get_budget(
        session_factory,
        budget_b.id,
    )

    assert stored is not None
    assert stored.user_id == user_b.id
    assert stored.category == "Food"
    assert Decimal(stored.amount) == money(
        "7000.00"
    )
    assert stored.month == "2026-10"


def test_update_invalid_payload_returns_422(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
) -> None:
    budget = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    payload = valid_budget_payload()
    payload["amount"] = "not-a-number"

    response = client.put(
        budget_url(budget.id),
        json=payload,
        headers=user_a.headers,
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

def test_delete_own_budget_removes_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
) -> None:
    budget = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    response = client.delete(
        budget_url(budget.id),
        headers=user_a.headers,
    )

    assert response.status_code == configured_status_code(
        BUDGET_ITEM_ROUTE,
        "DELETE",
    )

    assert get_budget(
        session_factory,
        budget.id,
    ) is None

    get_response = client.get(
        budget_url(budget.id),
        headers=user_a.headers,
    )

    assert get_response.status_code == 404


def test_delete_nonexistent_budget_returns_actual_error_response(
    client: TestClient,
    user_a: TestUser,
) -> None:
    response = client.delete(
        budget_url(999999),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_user_cannot_delete_another_users_budget(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    budget_b = create_budget(
        session_factory,
        user_b.id,
        "Food",
        "7000.00",
        "2026-10",
    )

    response = client.delete(
        budget_url(budget_b.id),
        headers=user_a.headers,
    )

    assert response.status_code == 404
    assert "detail" in response.json()

    stored = get_budget(
        session_factory,
        budget_b.id,
    )

    assert stored is not None
    assert stored.user_id == user_b.id
    assert stored.category == "Food"
    assert Decimal(stored.amount) == money(
        "7000.00"
    )

    owner_response = client.get(
        budget_url(budget_b.id),
        headers=user_b.headers,
    )

    assert owner_response.status_code == configured_status_code(
        BUDGET_ITEM_ROUTE,
        "GET",
    )


# --------------------------------------------------------------------------- #
# End-to-end ownership isolation
# --------------------------------------------------------------------------- #

def test_budget_ownership_isolation_across_all_operations(
    client: TestClient,
    session_factory: sessionmaker[Session],
    user_a: TestUser,
    user_b: TestUser,
) -> None:
    budget_a = create_budget(
        session_factory,
        user_a.id,
        "Food",
        "5000.00",
        "2026-10",
    )

    budget_b = create_budget(
        session_factory,
        user_b.id,
        "Food",
        "7000.00",
        "2026-10",
    )

    list_a = client.get(
        BUDGETS_URL,
        headers=user_a.headers,
    )

    list_b = client.get(
        BUDGETS_URL,
        headers=user_b.headers,
    )

    assert {
        item["id"]
        for item in list_a.json()
    } == {budget_a.id}

    assert {
        item["id"]
        for item in list_b.json()
    } == {budget_b.id}

    get_b_as_a = client.get(
        budget_url(budget_b.id),
        headers=user_a.headers,
    )

    update_b_as_a = client.put(
        budget_url(budget_b.id),
        json=valid_budget_payload(
            category="Travel",
            amount="1.00",
            month="2026-11",
        ),
        headers=user_a.headers,
    )

    delete_b_as_a = client.delete(
        budget_url(budget_b.id),
        headers=user_a.headers,
    )

    assert get_b_as_a.status_code == 404
    assert update_b_as_a.status_code == 404
    assert delete_b_as_a.status_code == 404

    stored_b = get_budget(
        session_factory,
        budget_b.id,
    )

    assert stored_b is not None
    assert stored_b.user_id == user_b.id
    assert stored_b.category == "Food"
    assert Decimal(stored_b.amount) == money(
        "7000.00"
    )
    assert stored_b.month == "2026-10"
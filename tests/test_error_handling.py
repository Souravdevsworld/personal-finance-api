"""Tests for global API exception handling."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import (  # noqa: E402
    global_exception_handler,
    integrity_error_handler,
)


# --------------------------------------------------------------------------- #
# Test application
# --------------------------------------------------------------------------- #

test_app = FastAPI()

test_app.add_exception_handler(
    IntegrityError,
    integrity_error_handler,
)

test_app.add_exception_handler(
    Exception,
    global_exception_handler,
)


# --------------------------------------------------------------------------- #
# Test routes
# --------------------------------------------------------------------------- #

INTEGRITY_ERROR_TEST_ROUTE = "/__test__/integrity-error"
UNEXPECTED_ERROR_TEST_ROUTE = "/__test__/unexpected-error"


@test_app.get(INTEGRITY_ERROR_TEST_ROUTE)
def raise_integrity_error():
    raise IntegrityError(
        "test statement",
        {},
        Exception("test database constraint violation"),
    )


@test_app.get(UNEXPECTED_ERROR_TEST_ROUTE)
def raise_unexpected_error():
    raise RuntimeError("This is a test exception")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_integrity_error_returns_409() -> None:
    client = TestClient(
        test_app,
        raise_server_exceptions=False,
    )

    response = client.get(INTEGRITY_ERROR_TEST_ROUTE)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Database constraint violation"
    }


def test_unexpected_exception_returns_500() -> None:
    client = TestClient(
        test_app,
        raise_server_exceptions=False,
    )

    response = client.get(UNEXPECTED_ERROR_TEST_ROUTE)

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error"
    }
"""
Standard API response envelope, per project spec §25.

Success: {"success": true, "data": {...}}
Error:   {"success": false, "error": {"code": "...", "message": "..."}}
"""
from typing import Any, Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None


def success_response(data: Any) -> dict:
    return {"success": True, "data": data}


def error_response(code: str, message: str, details: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"success": False, "error": error}


class ApiError(HTTPException):
    """
    Raise this anywhere in the app to produce a standardized error envelope.
    The global exception handler (see app.main) converts it to the
    {"success": false, "error": {...}} shape.
    """

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class NotFoundError(ApiError):
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "Not authenticated", code: str = "UNAUTHORIZED"):
        super().__init__(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "Not authorized", code: str = "FORBIDDEN"):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class ConflictError(ApiError):
    def __init__(self, message: str = "Conflict", code: str = "CONFLICT"):
        super().__init__(code=code, message=message, status_code=status.HTTP_409_CONFLICT)


class RateLimitError(ApiError):
    def __init__(self, message: str = "Too many requests", code: str = "RATE_LIMITED"):
        super().__init__(code=code, message=message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)

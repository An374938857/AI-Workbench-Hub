from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: Optional[T] = None

    @classmethod
    def success(cls, data: Any = None, message: str = "success") -> "ApiResponse":
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> "ApiResponse":
        return cls(code=code, message=message, data=data)


class PaginatedData(BaseModel, Generic[T]):
    items: list
    total: int
    page: int
    page_size: int

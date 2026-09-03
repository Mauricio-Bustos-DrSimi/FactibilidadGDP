"""Transport-neutral failures raised by document use cases."""


class DocumentError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


__all__ = ["DocumentError"]

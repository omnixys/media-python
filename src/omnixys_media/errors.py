from __future__ import annotations


class StorageError(Exception):
    def __init__(self, message: str, code: str = "STORAGE_ERROR") -> None:
        self.code = code
        super().__init__(message)

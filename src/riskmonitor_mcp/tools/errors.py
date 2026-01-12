"""Tool error payload helpers."""

from __future__ import annotations


def error_payload(code: str, message: str, request_id: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }

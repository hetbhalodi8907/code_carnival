from typing import Any

from app.main import app


async def call_app(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], dict[str, str]]:
    """Invoke the application through its real ASGI interface."""
    path, _, query_string = path.partition("?")
    request_headers = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string.encode(),
        "root_path": "",
        "headers": request_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "content_length": len(body),
    }
    response_messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        response_messages.append(message)

    await app(scope, receive, send)

    start = next(
        message
        for message in response_messages
        if message["type"] == "http.response.start"
    )
    body_messages = [
        message
        for message in response_messages
        if message["type"] == "http.response.body"
    ]
    body = b"".join(message.get("body", b"") for message in body_messages)
    response_headers = {
        key.decode(): value.decode()
        for key, value in start["headers"]
    }
    return start["status"], response_headers, {"body": body.decode()}

"""Localhost setup console: a FastAPI app over the shared host actions, token-protected."""

from __future__ import annotations

import hmac
import os
import secrets
import signal
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from paid_media_agent.admin import actions
from paid_media_agent.admin.processes import ProcessError, ProcessManager
from paid_media_agent.admin.routes import build_routes
from paid_media_agent.domain.common import JsonValue

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
)

ACTIONS: dict[str, Callable[..., actions.ActionResult]] = {
    "model_test": lambda root, **_: actions.model_test(root),
    "pipeboard_test": lambda root, **_: actions.pipeboard_test(root),
    "accounts_discover": lambda root, **_: actions.accounts_discover(root),
    "accounts_list": lambda root, **_: actions.accounts_list(root),
    "catalog_show": lambda root, live=False, **_: actions.catalog_show(root, live=bool(live)),
    "policy_validate": lambda root, live=False, **_: actions.policy_validate(root, live=bool(live)),
    "slack_test": lambda root, **_: actions.slack_test(root),
    "database_test": lambda root, **_: actions.database_test(root),
    "mda_check": lambda root, **_: actions.mda_check(root),
    "demo_run": lambda root, with_proposal=False, **_: actions.demo_run(
        root, with_proposal=bool(with_proposal)
    ),
    "snapshot_check": lambda root, **_: actions.snapshot_check(root),
    "status": lambda root, **_: actions.status(root),
    "ask": lambda root, question="", **_: actions.ask_question(root, str(question)),
}


class ConfigUpdate(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    key: str


class AccountAdd(BaseModel):
    alias: str
    platform: str
    provider_account_id: str
    currency: str = "USD"
    timezone: str = "UTC"


class ProcessStart(BaseModel):
    confirm: bool = False


class KillSwitchRequest(BaseModel):
    engaged: bool
    confirm: bool = False


class ConsoleState:
    def __init__(self, root: Path, token: str, processes: ProcessManager) -> None:
        self.root = root
        self.token = token
        self.processes = processes
        self.shutdown: Callable[[], None] | None = None


def create_console_app(
    root: Path, *, token: str | None = None, processes: ProcessManager | None = None
) -> FastAPI:
    state = ConsoleState(
        root, token or secrets.token_urlsafe(32), processes or ProcessManager(root)
    )
    app = FastAPI(
        title="Paid Media Agent setup console", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.console = state

    def _authorized(request: Request) -> ConsoleState:
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="console is local only")
        provided = request.headers.get("x-admin-token", "")
        if not hmac.compare_digest(provided, state.token):
            raise HTTPException(status_code=401, detail="missing or invalid admin token")
        return state

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Callable[[Request], Any]) -> Any:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index(request: Request) -> Response:
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="console is local only")
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/static/{name}")
    def static(name: str, request: Request) -> Response:
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="console is local only")
        path = (STATIC_DIR / name).resolve()
        if path.parent != STATIC_DIR.resolve() or not path.is_file():
            raise HTTPException(status_code=404)
        media = {
            ".css": "text/css",
            ".js": "text/javascript",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".html": "text/html",
        }.get(path.suffix, "application/octet-stream")
        return FileResponse(path, media_type=media)

    @app.get("/api/status")
    def get_status(console: ConsoleState = Depends(_authorized)) -> dict[str, JsonValue]:
        result = actions.status(console.root)
        return {
            "result": result.model_dump(mode="json"),
            "routes": [r.model_dump(mode="json") for r in build_routes(result.detail)],
            "processes": [p.model_dump(mode="json") for p in console.processes.views()],
        }

    @app.get("/api/config")
    def get_config(console: ConsoleState = Depends(_authorized)) -> dict[str, JsonValue]:
        return actions.config_view(console.root).model_dump(mode="json")

    @app.post("/api/config")
    def post_config(
        body: ConfigUpdate, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.config_set(console.root, body.updates).model_dump(mode="json")

    @app.post("/api/config/generate")
    def post_generate(
        body: GenerateRequest, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.generate_secret(console.root, body.key).model_dump(mode="json")

    @app.post("/api/actions/{name}")
    def post_action(
        name: str,
        body: dict[str, JsonValue] | None = None,
        console: ConsoleState = Depends(_authorized),
    ) -> dict[str, JsonValue]:
        if name == "generate_secrets":
            first = actions.generate_secret(console.root, "PAID_MEDIA_APPROVAL_SIGNING_KEY")
            second = actions.generate_secret(console.root, "PAID_MEDIA_API_TOKENS")
            merged = actions.ActionResult(
                action="generate_secrets",
                ok=first.ok and second.ok,
                status="ok" if first.ok and second.ok else "fail",
                summary="signing key and API token generated"
                if first.ok and second.ok
                else f"{first.summary}; {second.summary}",
                detail={"api_token_show_once": second.detail.get("show_once", "")},
                command="paid-media-agent config generate PAID_MEDIA_APPROVAL_SIGNING_KEY PAID_MEDIA_API_TOKENS",
            )
            return merged.model_dump(mode="json")
        handler = ACTIONS.get(name)
        if handler is None:
            raise HTTPException(status_code=404, detail="unknown action")
        return handler(console.root, **(body or {})).model_dump(mode="json")

    @app.post("/api/accounts")
    def post_account(
        body: AccountAdd, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.accounts_add(
            console.root,
            alias=body.alias,
            platform=body.platform,
            provider_account_id=body.provider_account_id,
            currency=body.currency,
            timezone=body.timezone,
        ).model_dump(mode="json")

    @app.delete("/api/accounts/{alias}")
    def delete_account(
        alias: str, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.accounts_remove(console.root, alias).model_dump(mode="json")

    @app.post("/api/processes/{name}/start")
    def start_process(
        name: str, body: ProcessStart | None = None, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        try:
            view = console.processes.start(name, confirmed=bool(body and body.confirm))
        except ProcessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return view.model_dump(mode="json")

    @app.post("/api/processes/{name}/stop")
    def stop_process(
        name: str, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        try:
            return console.processes.stop(name).model_dump(mode="json")
        except ProcessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/api/processes/{name}/log")
    def process_log(
        name: str, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        try:
            return console.processes.view(name).model_dump(mode="json")
        except ProcessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.post("/api/kill-switch")
    def kill_switch(
        body: KillSwitchRequest, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.kill_switch_set(
            console.root, engaged=body.engaged, confirmed=body.confirm
        ).model_dump(mode="json")

    @app.post("/api/shutdown")
    def shutdown(console: ConsoleState = Depends(_authorized)) -> JSONResponse:
        console.processes.stop_all()
        if console.shutdown is not None:
            threading.Timer(0.2, console.shutdown).start()
        return JSONResponse({"ok": True})

    return app


def run_console(root: Path, *, port: int = 8765, open_browser: bool = True) -> None:
    """Serve the console on 127.0.0.1 and open the browser with the per-run token."""
    import uvicorn  # noqa: PLC0415

    token = secrets.token_urlsafe(32)
    app = create_console_app(root, token=token)
    url = f"http://127.0.0.1:{port}/#token={token}"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    app.state.console.shutdown = lambda: os.kill(os.getpid(), signal.SIGINT)
    if open_browser:
        import webbrowser  # noqa: PLC0415

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Paid Media Agent setup console: {url}", flush=True)
    print("Press Ctrl+C to stop. The token is per run and only valid on this machine.", flush=True)
    try:
        server.run()
    finally:
        app.state.console.processes.stop_all()

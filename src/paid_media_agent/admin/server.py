"""Localhost setup console: a FastAPI app over the shared host actions, token-protected."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import signal
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, SecretStr

from paid_media_agent.admin import actions
from paid_media_agent.admin.model_presets import model_key_env
from paid_media_agent.admin.processes import ProcessError, ProcessManager
from paid_media_agent.admin.routes import build_routes
from paid_media_agent.admin.slack_icon import MAX_ICON_BYTES, icon_data_url, icon_path, save_icon
from paid_media_agent.deployment import DeploymentSettings
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
    "sandbox_test": lambda root, **_: actions.sandbox_test(root),
    "status": lambda root, **_: actions.status(root),
    "ask": lambda root, question="", **_: actions.ask_question(root, str(question)),
}


class OrgUpdate(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)


class ConfigUpdate(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)


class ModelCatalogRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))


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
        self.checks: dict[str, JsonValue] = {}
        self.check_stamps: dict[str, str] = {}
        self.shutdown: Callable[[], None] | None = None

    def stamp(self, name: str) -> str:
        settings = actions.load_settings(self.root)
        prefixes: tuple[str, ...] = (
            ("paid_media_model", "paid_media_tool_selector_model")
            if name == "model_test"
            else ("pipeboard_", "linkedin_", "x_ads_", "openai_ads_")
        )
        if name == "mda_check":
            prefixes += ("paid_media_model", "paid_media_sandbox_")
        values = {
            key: value.get_secret_value() if isinstance(value, SecretStr) else value
            for key, value in settings.model_dump().items()
            if key.startswith(prefixes)
        }
        if name in ("model_test", "mda_check"):
            try:
                key_name = model_key_env(settings)
            except ValueError:
                key_name = None
            values["model_key"] = os.environ.get(key_name, "") if key_name else ""
        if name == "mda_check":
            values["deployment_key"] = os.environ.get("LANGSMITH_API_KEY", "")
            values["customization"] = DeploymentSettings(
                _env_file=str(self.root / ".env")
            ).model_dump(mode="json")
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()

    def refresh_checks(self) -> None:
        for name in list(self.checks):
            if self.check_stamps.get(name) != self.stamp(name):
                self.checks.pop(name)


def _same_origin(request: Request) -> bool:
    """True when the browser says the call came from this console's own page.

    Token-less mode relies on this instead of the per-run token. Browsers send `Origin` on every
    cross-origin request and `Sec-Fetch-Site` on every request, so a page on another site cannot
    drive the console even though it runs on localhost.
    """
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    host = request.headers.get("host") or ""
    return origin.rstrip("/") in (f"http://{host}", f"https://{host}")


def create_console_app(
    root: Path,
    *,
    token: str | None = None,
    processes: ProcessManager | None = None,
    require_token: bool = True,
) -> FastAPI:
    """The console app. `require_token=False` is for a coding agent's browser pane, which can only
    open a plain URL: same-origin requests are accepted without the token."""
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
        if not require_token:
            if not _same_origin(request):
                raise HTTPException(
                    status_code=403, detail="console accepts same-origin calls only"
                )
            return state
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
        console.refresh_checks()
        return {
            "result": result.model_dump(mode="json"),
            "routes": [r.model_dump(mode="json") for r in build_routes(result.detail)],
            "processes": [p.model_dump(mode="json") for p in console.processes.views()],
            "connection_checks": console.checks,
        }

    @app.get("/api/config")
    def get_config(console: ConsoleState = Depends(_authorized)) -> dict[str, JsonValue]:
        return actions.config_view(console.root).model_dump(mode="json")

    @app.post("/api/models")
    def get_models(
        body: ModelCatalogRequest, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        return actions.models_list(
            console.root, body.provider, api_key=body.api_key.get_secret_value()
        ).model_dump(mode="json")

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

    @app.get("/api/slack/icon")
    def get_slack_icon(console: ConsoleState = Depends(_authorized)) -> dict[str, str]:
        try:
            return {"data_url": icon_data_url(console.root)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="No custom Slack icon") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/slack/icon")
    async def post_slack_icon(
        request: Request, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, bool]:
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_ICON_BYTES:
                raise HTTPException(status_code=413, detail="Choose a PNG no larger than 1 MB")
        try:
            save_icon(console.root, bytes(data))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        console.checks.pop("mda_check", None)
        return {"ok": True}

    @app.delete("/api/slack/icon")
    def delete_slack_icon(console: ConsoleState = Depends(_authorized)) -> dict[str, bool]:
        try:
            icon_path(console.root).unlink(missing_ok=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        console.checks.pop("mda_check", None)
        return {"ok": True}

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
        console.refresh_checks()
        stamp = console.stamp(name)
        result = handler(console.root, **(body or {})).model_dump(mode="json")
        console.refresh_checks()
        if name in (
            "model_test",
            "pipeboard_test",
            "accounts_discover",
            "mda_check",
        ) and stamp == console.stamp(name):
            console.check_stamps[name] = stamp
            console.checks[name] = {"status": result["status"], "summary": result["summary"]}
        return result

    @app.get("/api/org")
    def get_org(console: ConsoleState = Depends(_authorized)) -> dict[str, JsonValue]:
        return actions.org_show(console.root).model_dump(mode="json")

    @app.post("/api/org")
    def post_org(
        body: OrgUpdate, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        result = actions.org_set(console.root, body.answers) if body.answers else None
        links = [
            actions.org_add_link(console.root, url).model_dump(mode="json") for url in body.links
        ]
        if result is None:
            return {
                "action": "org_set",
                "ok": True,
                "status": "ok",
                "summary": "no answers changed",
                "detail": {"links": links},
            }
        merged = result.model_dump(mode="json")
        merged["detail"]["links"] = links
        return merged

    @app.post("/api/org/files")
    async def post_org_file(
        file: UploadFile, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        from paid_media_agent.org import MAX_SOURCE_BYTES

        data = await file.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="files up to 1 MB")
        name = Path(file.filename or "upload.txt").name
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / name
            staged.write_bytes(data)
            return actions.org_add_file(console.root, staged).model_dump(mode="json")

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
            confirmed = bool(body and body.confirm)
            if name == "mda-deploy":
                if not confirmed:
                    raise ProcessError("mda-deploy requires explicit confirmation")
                check = actions.mda_check(console.root)
                if check.status != "ok":
                    raise ProcessError(check.summary)
            view = console.processes.start(name, confirmed=confirmed)
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

    @app.post("/api/processes/{name}/continue")
    def continue_process(
        name: str, console: ConsoleState = Depends(_authorized)
    ) -> dict[str, JsonValue]:
        try:
            return console.processes.continue_authorization(name).model_dump(mode="json")
        except ProcessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

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


def run_console(
    root: Path, *, port: int = 8765, open_browser: bool = True, require_token: bool = True
) -> None:
    """Serve the console on 127.0.0.1 and open the browser with the per-run token.

    With `require_token=False` the URL carries no token, so an IDE's browser pane can open it as
    is; the console then accepts same-origin calls only.
    """
    import uvicorn

    token = secrets.token_urlsafe(32)
    app = create_console_app(root, token=token, require_token=require_token)
    url = f"http://127.0.0.1:{port}/" + (f"#token={token}" if require_token else "")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    app.state.console.shutdown = lambda: os.kill(os.getpid(), signal.SIGINT)
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Paid Media Agent setup console: {url}", flush=True)
    if require_token:
        print(
            "Press Ctrl+C to stop. The token is per run and only valid on this machine.", flush=True
        )
    else:
        print(
            "Press Ctrl+C to stop. No token: any local browser page can open this console while it "
            "runs; calls from other sites are refused.",
            flush=True,
        )
    try:
        server.run()
    finally:
        app.state.console.processes.stop_all()

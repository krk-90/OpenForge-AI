from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from APP.core.tracing import configure_langsmith_tracing
from APP.routes.agents import router as agents_router
from APP.routes.auth import router as auth_router

configure_langsmith_tracing()

app = FastAPI(title="OpenForge API")
app.include_router(auth_router)
app.include_router(agents_router)
FRONTEND_DIR = Path(__file__).resolve().parent / "Frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
FRONTEND_PAGE = FRONTEND_DIST / "index.html"
if (FRONTEND_DIST / "assets").is_dir():
	app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def login_page() -> FileResponse:
	if not FRONTEND_PAGE.is_file():
		raise RuntimeError("Frontend build is missing. Run `npm run build` in APP/Frontend.")
	return FileResponse(FRONTEND_PAGE)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
	return {"status": "ok"}

"""Serve the built React SPA from FastAPI (prod image): static files, plus index.html for client-side routes."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

# Never cached, so a new deploy reaches phones on the next load
NO_CACHE = {"Cache-Control": "no-cache"}
UNCACHED_FILES = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}


class HashedAssets(StaticFiles):
    """Vite puts a content hash in every file name under assets/, so browsers may keep them forever."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_spa(app: FastAPI, directory: Path) -> None:
    root = directory.resolve()
    if (root / "assets").is_dir():
        app.mount("/assets", HashedAssets(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            headers = NO_CACHE if candidate.name in UNCACHED_FILES else None
            return FileResponse(candidate, headers=headers)
        return FileResponse(root / "index.html", headers=NO_CACHE)

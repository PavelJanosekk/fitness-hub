from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import mount_spa


def make_app(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)")
    (tmp_path / "sw.js").write_text("// sw")
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    mount_spa(app, tmp_path)
    return TestClient(app)


def test_client_routes_get_index_html_uncached(tmp_path: Path) -> None:
    client = make_app(tmp_path)

    for path in ("/", "/gym", "/settings"):
        response = client.get(path)
        assert response.text == "<html>app</html>"
        assert response.headers["cache-control"] == "no-cache"


def test_files_and_assets_are_served(tmp_path: Path) -> None:
    client = make_app(tmp_path)

    asset = client.get("/assets/index-abc.js")
    assert asset.text == "console.log(1)"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"


def test_api_routes_win_and_unknown_api_paths_are_404(tmp_path: Path) -> None:
    client = make_app(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/nope").status_code == 404


def test_no_path_traversal(tmp_path: Path) -> None:
    (tmp_path.parent / "secret.txt").write_text("secret")
    client = make_app(tmp_path)

    assert "secret" not in client.get("/../secret.txt").text
    assert "secret" not in client.get("/%2e%2e/secret.txt").text

from app.routers.interface import INTERFACE_CSP


def test_home_serves_the_interface(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_home_sends_the_content_security_policy(client):
    response = client.get("/")
    assert response.headers["Content-Security-Policy"] == INTERFACE_CSP


def test_csp_blocks_external_resources():
    assert "default-src 'none'" in INTERFACE_CSP
    assert "script-src 'self'" in INTERFACE_CSP
    assert "frame-ancestors 'none'" in INTERFACE_CSP


def test_static_files_are_served(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_unknown_static_file_returns_404(client):
    assert client.get("/static/nao-existe.js").status_code == 404


def test_api_documentation_is_available(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/auth/login" in paths
    assert "/documents/{document_id}/questions" in paths

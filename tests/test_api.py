from fastapi.testclient import TestClient

from translator.api import create_app


def test_api_create_start_cancel_and_errors(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    app = create_app(tmp_path / "runs")
    client = TestClient(app)

    missing = client.post(
        "/runs", json={"source_pdf": str(tmp_path / "missing.pdf"), "idempotency_key": "x"}
    )
    assert missing.status_code == 400
    assert missing.json()["error_code"] == "INVALID_SOURCE_PDF"

    created = client.post(
        "/runs", json={"source_pdf": str(source), "idempotency_key": "request-1"}
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert client.post(f"/runs/{run_id}/start").json()["accepted"] is True
    assert client.post(f"/runs/{run_id}/cancel").json()["accepted"] is True
    assert client.get(f"/runs/{run_id}/events").status_code == 200


def test_artifact_download_rejects_unknown_file(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    app = create_app(tmp_path / "runs")
    client = TestClient(app)
    run_id = client.post(
        "/runs", json={"source_pdf": str(source), "idempotency_key": "request-1"}
    ).json()["run_id"]

    response = client.get(f"/runs/{run_id}/artifacts/not-there.pdf")
    assert response.status_code == 404
    assert response.json()["error_code"] == "ARTIFACT_NOT_FOUND"


def test_failed_run_does_not_expose_stale_translation(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    runs_root = tmp_path / "runs"
    app = create_app(runs_root)
    client = TestClient(app)
    run_id = client.post(
        "/runs", json={"source_pdf": str(source), "idempotency_key": "request-stale"}
    ).json()["run_id"]
    artifact = runs_root / run_id / "translated.pdf"
    artifact.write_bytes(b"stale")
    app.state.db.set_run(run_id, "render_failed", "overflow", "does not fit")

    listing = client.get(f"/runs/{run_id}/artifacts").json()["files"]
    assert "translated.pdf" not in {item["name"] for item in listing}
    response = client.get(f"/runs/{run_id}/artifacts/translated.pdf")
    assert response.status_code == 409
    assert response.json()["error_code"] == "ARTIFACT_STALE"


def test_upload_creates_run_without_original_path(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    app = create_app(tmp_path / "runs")
    client = TestClient(app)
    response = client.post(
        "/runs/upload",
        files={"file": ("book.pdf", source.read_bytes(), "application/pdf")},
        data={"idempotency_key": "upload-1", "glossary": "[]"},
    )

    assert response.status_code == 201
    run = app.state.db.run(response.json()["run_id"])
    assert run["source_path"].endswith(".pdf")
    assert run["source_path"] != str(source.resolve())
    assert "uploads" in run["source_path"]


def test_upload_rejects_non_pdf(tmp_path):
    app = create_app(tmp_path / "runs")
    response = TestClient(app).post(
        "/runs/upload",
        files={"file": ("book.txt", b"not a pdf", "text/plain")},
        data={"idempotency_key": "upload-bad", "glossary": "[]"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_SOURCE_PDF"

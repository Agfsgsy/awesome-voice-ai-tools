import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_path_traversal_downloads():
    response = client.get("/api/downloads/invalid_.._file")
    assert response.status_code == 404

def test_path_traversal_downloads_direct():
    from backend.api.routes import api_download_file
    import asyncio
    with pytest.raises(Exception) as excinfo:
        asyncio.run(api_download_file("../../../etc/passwd"))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid filename"

def test_path_traversal_uploads_direct():
    from backend.api.routes import api_download_upload
    import asyncio
    with pytest.raises(Exception) as excinfo:
        asyncio.run(api_download_upload("../../../etc/passwd"))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid filename"

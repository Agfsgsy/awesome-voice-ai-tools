from fastapi.testclient import TestClient
from main import app

def test_api_rename_file_404():
    client = TestClient(app)

    response = client.post(
        "/api/files/non_existent_file_12345.txt/rename",
        json={"new_name": "renamed_file.txt"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "File not found"}

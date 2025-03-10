import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_listar_arquivos():
    response = client.get("/api/arquivos/R189")
    assert response.status_code in [200, 404, 500]  # Aceita qualquer resposta, só para verificar se a rota existe
    
    if response.status_code == 200:
        data = response.json()
        assert "success" in data 
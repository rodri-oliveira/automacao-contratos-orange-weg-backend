import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_validate_mun_code_r189():
    """
    Testa a rota de validação MUN_CODE vs R189
    """
    response = client.post("/api/validation/mun_code_r189")
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    
    # Se a validação falhar, verifica se há uma mensagem de erro
    if not data["success"]:
        assert "error" in data
        print(f"Erro na validação: {data['error']}")
    else:
        assert "message" in data
        print(f"Mensagem de sucesso: {data['message']}")
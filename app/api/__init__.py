# Pode ficar vazio ou apenas com importações necessárias
from fastapi import APIRouter, FastAPI

api_router = APIRouter()
app = FastAPI()

# Adicione este endpoint temporário em app/main.py para teste
@app.get("/test")
async def test_route():
    return {"status": "ok", "message": "API está funcionando!"}


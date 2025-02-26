import uvicorn
import os
import sys

# Adicionar o diretório atual ao sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

if __name__ == "__main__":
    # Usando a porta 8000 para corresponder ao proxy no package.json
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

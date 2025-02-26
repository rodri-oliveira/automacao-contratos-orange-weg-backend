from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.core.config import settings
from app.api.main import api_router
import os
from dotenv import load_dotenv
from app.core.sharepoint import SharePointClient
from app.core.auth import SharePointAuth
from app.core.extractors.r189_extractor import R189Extractor
from io import BytesIO
from typing import List, Dict, Any
import requests

# Carregar variáveis de ambiente
load_dotenv()

# Configurando logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Automação de Contratos - Finanças",
    version="0.0.1",
    docs_url="/api",
)

# Configurando CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique as origens permitidas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.root_path is not None:
    app.root_path = settings.root_path

if settings.swagger_servers_list is not None:
    app.servers = list(map(lambda x: { "url": x }, settings.swagger_servers_list.split(",")))

# Incluindo rotas
app.include_router(api_router, prefix="/api")

# Constantes
SITE_URL = os.getenv('SITE_URL')
PASTAS = {
    'R189': "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    'QPE': "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    'SPB': "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
    'NFSERV': "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    'MUN_CODE': "/teams/BR-TI-TIN/AutomaoFinanas/R189"  # Usa a mesma pasta do R189
}

# Rota básica para teste
@app.get("/")
async def root():
    return {"message": "Bem-vindo à API de Automação de Contratos - Finanças"}

# Rota para buscar arquivos do SharePoint
@app.get("/api/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    print(f"Recebida requisição para buscar arquivos do tipo: {tipo}")
    
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
    
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            print("Falha ao obter token de autenticação")
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        pasta = PASTAS[tipo]
        url = f"{SITE_URL}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        print(f"Status code da resposta: {response.status_code}")
        
        if response.status_code == 200:
            dados = response.json()
            arquivos = [
                {
                    "name": arquivo["Name"],
                    "size": arquivo["Length"],
                    "modified": arquivo["TimeLastModified"]
                }
                for arquivo in dados["d"]["results"]
            ]
            print(f"Arquivos encontrados: {arquivos}")
            return {"arquivos": arquivos}
        else:
            print(f"Erro na resposta: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro ao buscar arquivos: {response.status_code}"
            )
            
    except Exception as e:
        print(f"Erro durante a busca: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Rota para processar arquivos R189
@app.post("/api/processar/R189")
async def processar_r189(arquivos: List[str]):
    try:
        auth = SharePointAuth()
        extractor = R189Extractor()
        
        resultados = []
        for arquivo in arquivos:
            # Baixa o arquivo do SharePoint
            conteudo = auth.baixar_arquivo_sharepoint(arquivo, PASTAS['R189'])
            
            if not conteudo:
                resultados.append({"arquivo": arquivo, "status": "erro", "mensagem": "Erro ao baixar arquivo"})
                continue
            
            # Processa o arquivo
            try:
                resultado = extractor.consolidar_r189(conteudo)
                if resultado:
                    resultados.append({"arquivo": arquivo, "status": "sucesso"})
                else:
                    resultados.append({"arquivo": arquivo, "status": "erro", "mensagem": "Erro ao processar arquivo"})
            except Exception as e:
                resultados.append({"arquivo": arquivo, "status": "erro", "mensagem": str(e)})
        
        # Verifica se todos os arquivos foram processados com sucesso
        todos_sucesso = all(r["status"] == "sucesso" for r in resultados)
        
        return {
            "processados": resultados,
            "status": "success" if todos_sucesso else "partial",
            "message": "Todos os arquivos foram processados com sucesso" if todos_sucesso else "Alguns arquivos não puderam ser processados"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rotas para processar outros tipos de arquivos
@app.post("/api/processar/{tipo}")
async def processar_arquivos(tipo: str, arquivos: List[str]):
    print(f"Iniciando processamento de {tipo} para arquivos: {arquivos}")  # Log adicional
    
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
    
    try:
        auth = SharePointAuth()
        pasta = PASTAS[tipo]
        resultados = []

        for nome_arquivo in arquivos:
            try:
                print(f"Processando arquivo: {nome_arquivo}")  # Log adicional
                
                # Baixa o arquivo do SharePoint
                conteudo = auth.baixar_arquivo_sharepoint(nome_arquivo, pasta)
                if not conteudo:
                    raise ValueError(f"Não foi possível baixar o arquivo {nome_arquivo}")

                # Processa o arquivo de acordo com o tipo
                if tipo == 'R189':
                    extractor = R189Extractor()
                    resultado = extractor.consolidar_r189(conteudo)
                    if resultado:
                        resultados.append({
                            "arquivo": nome_arquivo,
                            "status": "sucesso",
                            "mensagem": "Arquivo processado com sucesso"
                        })
                    else:
                        raise ValueError("Falha ao processar arquivo R189")
                else:
                    # Implementar processamento para outros tipos
                    raise NotImplementedError(f"Processamento de {tipo} ainda não implementado")

            except Exception as e:
                print(f"Erro ao processar {nome_arquivo}: {str(e)}")  # Log adicional
                resultados.append({
                    "arquivo": nome_arquivo,
                    "status": "erro",
                    "mensagem": str(e)
                })

        # Verifica se houve algum sucesso no processamento
        if not any(r["status"] == "sucesso" for r in resultados):
            raise HTTPException(
                status_code=500,
                detail="Nenhum arquivo foi processado com sucesso"
            )

        return {
            "status": "success",
            "mensagem": "Processamento concluído",
            "resultados": resultados
        }

    except Exception as e:
        print(f"Erro durante o processamento: {str(e)}")  # Log adicional
        raise HTTPException(status_code=500, detail=str(e))

# Rota para verificar validações
@app.post("/api/validar/{tipo}")
async def validar(tipo: str):
    tipos_validos = ['R189', 'QPE', 'SPB', 'NFSERV', 'MUN_CODE']
    if tipo not in tipos_validos:
        raise HTTPException(status_code=400, detail="Tipo de validação inválido")
    
    # Por enquanto, apenas simula a validação
    return {
        "status": "success",
        "message": f"Validação de {tipo} simulada com sucesso",
        "divergencias": []
    }

# Rota de teste para processamento
@app.post("/api/r189/process")
async def process_r189_file(request: dict):
    file_name = request.get("fileName", "")
    return {
        "success": True,
        "fileName": file_name,
        "processedFileName": "R189_consolidado.xlsx",
        "message": "Arquivo processado com sucesso (simulação)"
    }

# Rota de teste para verificar se o servidor está funcionando
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
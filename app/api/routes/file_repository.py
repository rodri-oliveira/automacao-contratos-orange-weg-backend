import os
import re
import logging
import traceback
import urllib.parse
import aiohttp
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from io import BytesIO
import requests
from dotenv import load_dotenv
import asyncio

from app.core.auth import SharePointAuth
from app.api.routes.file_processor import (
    make_request, 
    list_files, 
    download_file, 
    check_folder_exists, 
    create_folder
)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/files-repository",
    tags=["files-repository"],
    responses={404: {"description": "Not found"}},
)

# Função para codificar corretamente os caminhos do SharePoint
def encode_sharepoint_path(path):
    """
    Codifica o caminho preservando underscores como requerido pelo SharePoint.
    IMPORTANTE: Não deve converter underscores para %5F
    """
    if not path:
        return ""
    
    # Remove barras extras no início e fim
    path = path.strip("/")
    
    # Remove barras duplas
    path = re.sub(r"//+", "/", path)
    
    # Adiciona barra no início
    path = "/" + path
    
    # Log do caminho que será usado
    logger.info(f"[ENCODE] Caminho formatado (sem codificação): {path}")
    
    # Para o SharePoint, vamos retornar sem codificação adicional
    # Esta é a parte mais importante - os testes mostraram que precisamos 
    # manter os underscores e caracteres especiais como estão
    return path

# Caminhos das pastas de origem - mantendo os originais para referência
ORIGINAL_PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
    "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
}

# Caminhos das pastas de origem codificados para uso em URLs
PATHS = {key: encode_sharepoint_path(path) for key, path in ORIGINAL_PATHS.items()}

# Caminhos das pastas de destino (repositório) - USANDO CAMINHOS SEM CODIFICAÇÃO
REPOSITORY_PATHS = {
    "CADASTRAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar",
    "ESCRITURAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Escriturar",
    "NOTA_FISCAL": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Nota_Fiscal_Serviço"
}

# Variável global para controlar o estado de cancelamento
PROCESS_CANCELLED = False

async def get_sharepoint_auth():
    """
    Obtém o token e a URL do site SharePoint da mesma maneira que o file_processor.py
    """
    from app.core.auth import SharePointAuth
    
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token de autenticação")
            return None, None
            
        return token, site_url
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao obter autenticação: {str(e)}")
        return None, None

async def prepare_repository_folders(token, site_url):
    """Prepara as pastas do repositório, criando a estrutura de ano.mês conforme necessário."""
    try:
        logger.info("[REPOSITORY] Preparando pastas do repositório")
        
        # Obtém o ano.mês atual
        current_date = datetime.now()
        year_month_folder = f"{current_date.year}.{current_date.month:02d}"
        logger.info(f"[REPOSITORY] Pasta do ano.mês: {year_month_folder}")
        
        results = {}
        
        # Verifica cada pasta do repositório
        for folder_type, base_path in REPOSITORY_PATHS.items():
            logger.info(f"[REPOSITORY] Verificando pasta {folder_type}: {base_path}")
            
            # Verifica se a pasta base existe
            base_exists = await check_folder_exists(token, site_url, base_path)
            
            if not base_exists:
                logger.error(f"[REPOSITORY] Pasta base {folder_type} não existe: {base_path}")
                results[folder_type] = {"success": False, "reason": "Pasta base não existe"}
                continue
                
            # Verifica/cria a pasta do ano.mês
            year_month_path = f"{base_path}/{encode_sharepoint_path(year_month_folder)}"
            year_month_exists = await check_folder_exists(token, site_url, year_month_path)
            
            if not year_month_exists:
                logger.info(f"[REPOSITORY] Criando pasta ano.mês para {folder_type}: {year_month_path}")
                create_result = await create_folder(token, site_url, year_month_path)
                
                if create_result:
                    logger.info(f"[REPOSITORY] Pasta ano.mês criada com sucesso para {folder_type}")
                    results[folder_type] = {"success": True, "path": year_month_path}
                else:
                    logger.error(f"[REPOSITORY] Falha ao criar pasta ano.mês para {folder_type}")
                    results[folder_type] = {"success": False, "reason": "Falha ao criar pasta ano.mês"}
            else:
                logger.info(f"[REPOSITORY] Pasta ano.mês já existe para {folder_type}")
                results[folder_type] = {"success": True, "path": year_month_path}
        
        return results, year_month_folder
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao preparar pastas: {str(e)}")
        logger.error(traceback.format_exc())
        return {}, ""

async def copy_file_to_repository(token, site_url, source_path, file_name, destination_path):
    """
    Copia um arquivo de uma pasta para outra no SharePoint.
    """
    try:
        # Verificar se o processo foi cancelado
        if check_if_cancelled():
            logger.info(f"[REPOSITORY] Cópia do arquivo {file_name} cancelada pelo usuário")
            return False
            
        # Codificar corretamente os caminhos
        encoded_source_path = encode_sharepoint_path(source_path)
        
        logger.info(f"[REPOSITORY] Copiando arquivo {file_name}")
        logger.info(f"[REPOSITORY] De: {encoded_source_path}")
        logger.info(f"[REPOSITORY] Para: {destination_path}")
        
        # Download do arquivo
        file_content = await download_file(token, site_url, encoded_source_path, file_name)
        
        if not file_content:
            logger.error(f"[REPOSITORY] Não foi possível baixar o arquivo {file_name}")
            return False
        
        # Verificar novamente se o processo foi cancelado após download
        if check_if_cancelled():
            logger.info(f"[REPOSITORY] Cópia do arquivo {file_name} cancelada após download")
            return False
        
        # Upload para o destino usando nossa nova função que sabemos que funciona
        success = await upload_file_to_repository(token, file_content, file_name, destination_path)
        
        if success:
            logger.info(f"[REPOSITORY] Arquivo {file_name} copiado com sucesso")
            return True
        else:
            logger.error(f"[REPOSITORY] Falha ao copiar arquivo {file_name}")
            return False
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao copiar arquivo: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.post("/copy-to-repository")
async def copy_files_to_repository():
    """
    Endpoint para copiar arquivos para o repositório, usando apenas pastas existentes.
    """
    try:
        global PROCESS_CANCELLED
        # Resetar o estado de cancelamento no início do processo
        PROCESS_CANCELLED = False
        
        logger.info("[REPOSITORY] Iniciando processo de cópia para o repositório")
        
        # Obter token e URL do site
        from app.core.auth import SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token")
            raise HTTPException(status_code=500, detail="Falha ao obter token de autenticação")
        
        logger.info(f"[REPOSITORY] Token obtido com sucesso. Site URL: {site_url}")
        
        # Verificar se as pastas de destino existem
        dest_folders = {}
        for folder_name, folder_path in REPOSITORY_PATHS.items():
            # Verificar cancelamento
            if check_if_cancelled():
                logger.info("[REPOSITORY] Processo cancelado durante verificação de pastas")
                return {"success": False, "message": "Processo cancelado pelo usuário", "cancelled": True}
                
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            dest_folders[folder_name] = folder_exists
            logger.info(f"[REPOSITORY] Pasta {folder_name} ({folder_path}) existe: {folder_exists}")
        
        # Contadores
        total_files = 0
        copied_files = 0
        failed_files = 0
        skipped_files = 0
        
        # Processamento de arquivos NFSERV
        if dest_folders.get("CADASTRAR") or dest_folders.get("ESCRITURAR"):
            logger.info("[REPOSITORY] Processando arquivos NFSERV")
            nfserv_files = await list_files(token, site_url, PATHS["NFSERV"])
            total_files += len(nfserv_files)
            
            for file in nfserv_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de NFSERV")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                
                # Critério 1: QPE-\d{6}[A-Za-z] -> CADASTRAR
                if re.search(r"QPE-\d{6}[A-Za-z]", file_name) and dest_folders.get("CADASTRAR"):
                    logger.info(f"[REPOSITORY] Arquivo {file_name} corresponde ao critério para CADASTRAR")
                    
                    success = await copy_file_to_repository(
                        token, site_url, PATHS["NFSERV"], file_name, REPOSITORY_PATHS["CADASTRAR"]
                    )
                    
                    if success:
                        copied_files += 1
                    else:
                        failed_files += 1
                    continue
                
                # Critério 2: cidade + \d{6}[A-Za-z]\d{2} -> ESCRITURAR
                cities = ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]
                has_city = any(city in file_name for city in cities)
                has_pattern = re.search(r"\d{6}[A-Za-z]\d{2}", file_name) is not None
                
                if has_city and has_pattern and dest_folders.get("ESCRITURAR"):
                    logger.info(f"[REPOSITORY] Arquivo {file_name} corresponde ao critério para ESCRITURAR")
                    
                    success = await copy_file_to_repository(
                        token, site_url, PATHS["NFSERV"], file_name, REPOSITORY_PATHS["ESCRITURAR"]
                    )
                    
                    if success:
                        copied_files += 1
                    else:
                        failed_files += 1
                else:
                    logger.info(f"[REPOSITORY] Arquivo {file_name} não corresponde a nenhum critério ou pasta de destino não existe, ignorando")
                    skipped_files += 1
        else:
            logger.error("[REPOSITORY] Pastas CADASTRAR e ESCRITURAR não existem, ignorando arquivos NFSERV")
            nfserv_files = await list_files(token, site_url, PATHS["NFSERV"])
            total_files += len(nfserv_files)
            skipped_files += len(nfserv_files)
        
        # Verificar cancelamento antes de processar QPE
        if check_if_cancelled():
            logger.info("[REPOSITORY] Processo cancelado antes de processar QPE")
            return {
                "success": False,
                "message": "Processo cancelado pelo usuário",
                "cancelled": True,
                "details": {
                    "total_files": total_files,
                    "copied_files": copied_files,
                    "failed_files": failed_files,
                    "skipped_files": skipped_files
                }
            }
        
        # Processamento de arquivos QPE -> NOTA_FISCAL
        if dest_folders.get("NOTA_FISCAL"):
            logger.info("[REPOSITORY] Processando arquivos QPE")
            qpe_files = await list_files(token, site_url, PATHS["QPE"])
            total_files += len(qpe_files)
            
            for file in qpe_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de QPE")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                
                success = await copy_file_to_repository(
                    token, site_url, PATHS["QPE"], file_name, REPOSITORY_PATHS["NOTA_FISCAL"]
                )
                
                if success:
                    copied_files += 1
                else:
                    failed_files += 1
        else:
            logger.error("[REPOSITORY] Pasta NOTA_FISCAL não existe, ignorando arquivos QPE")
            qpe_files = await list_files(token, site_url, PATHS["QPE"])
            total_files += len(qpe_files)
            skipped_files += len(qpe_files)
        
        # Verificar cancelamento antes de processar SPB
        if check_if_cancelled():
            logger.info("[REPOSITORY] Processo cancelado antes de processar SPB")
            return {
                "success": False,
                "message": "Processo cancelado pelo usuário",
                "cancelled": True,
                "details": {
                    "total_files": total_files,
                    "copied_files": copied_files,
                    "failed_files": failed_files,
                    "skipped_files": skipped_files
                }
            }
        
        # Processamento de arquivos SPB -> NOTA_FISCAL
        if dest_folders.get("NOTA_FISCAL"):
            logger.info("[REPOSITORY] Processando arquivos SPB")
            spb_files = await list_files(token, site_url, PATHS["SPB"])
            total_files += len(spb_files)
            
            for file in spb_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de SPB")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                
                success = await copy_file_to_repository(
                    token, site_url, PATHS["SPB"], file_name, REPOSITORY_PATHS["NOTA_FISCAL"]
                )
                
                if success:
                    copied_files += 1
                else:
                    failed_files += 1
        else:
            logger.error("[REPOSITORY] Pasta NOTA_FISCAL não existe, ignorando arquivos SPB")
            spb_files = await list_files(token, site_url, PATHS["SPB"])
            total_files += len(spb_files)
            skipped_files += len(spb_files)
        
        # Relatório
        logger.info("[REPOSITORY] Processo de cópia concluído")
        logger.info(f"[REPOSITORY] Total de arquivos: {total_files}")
        logger.info(f"[REPOSITORY] Copiados com sucesso: {copied_files}")
        logger.info(f"[REPOSITORY] Falhas: {failed_files}")
        logger.info(f"[REPOSITORY] Ignorados: {skipped_files}")
        
        return {
            "success": True,
            "message": "Processo de cópia concluído",
            "details": {
                "total_files": total_files,
                "copied_files": copied_files,
                "failed_files": failed_files,
                "skipped_files": skipped_files
            },
            "destination_folders": {
                k: v for k, v in dest_folders.items()
            }
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro durante o processo: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/folder-access-test")
async def test_folder_access():
    """
    Endpoint para testar o acesso às pastas de origem e destino.
    Útil para diagnóstico de problemas de permissão.
    """
    try:
        logger.info("[REPOSITORY] Testando acesso às pastas")
        
        # Obter token e URL do site
        token, site_url = await get_sharepoint_auth()
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token de autenticação")
            raise HTTPException(status_code=500, detail="Falha ao obter token de autenticação")
        
        results = {}
        
        # Testar acesso às pastas de origem
        for folder_name, folder_path in PATHS.items():
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            results[folder_name] = {
                "path": folder_path,
                "original_path": ORIGINAL_PATHS[folder_name],
                "exists": folder_exists
            }
            
            if folder_exists:
                # Tentar listar arquivos
                files = await list_files(token, site_url, folder_path)
                results[folder_name]["files_count"] = len(files)
                if files:
                    results[folder_name]["sample_files"] = [f.get("Name") for f in files[:3]]
        
        # Testar acesso às pastas de destino
        for folder_name, folder_path in REPOSITORY_PATHS.items():
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            results[f"REPO_{folder_name}"] = {
                "path": folder_path,
                "original_path": REPOSITORY_PATHS[folder_name],
                "exists": folder_exists
            }
            
            if folder_exists:
                # Tentar listar arquivos
                files = await list_files(token, site_url, folder_path)
                results[f"REPO_{folder_name}"]["files_count"] = len(files)
                if files:
                    results[f"REPO_{folder_name}"]["sample_files"] = [f.get("Name") for f in files[:3]]
        
        return {
            "success": True,
            "message": "Teste de acesso concluído",
            "results": results
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro durante o teste de acesso: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro durante o teste de acesso: {str(e)}")

@router.get("/test-simple-upload")
async def test_simple_upload():
    """
    Endpoint para testar o upload com codificação correta de URL.
    O frontend pode chamar esta API para verificar se a solução funciona.
    """
    try:
        # Obter autenticação
        from app.core.auth import SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            return {"success": False, "error": "Falha ao obter token"}
        
        # Caminhos para teste (os três principais repositórios)
        test_paths = [
            ORIGINAL_PATHS["CADASTRAR"],
            ORIGINAL_PATHS["ESCRITURAR"],
            ORIGINAL_PATHS["NOTA_FISCAL"]
        ]
        
        results = []
        
        for test_path in test_paths:
            try:
                # Codificação correta: preservar underscores
                path_parts = test_path.split('/')
                encoded_parts = []
                
                for part in path_parts:
                    if part:
                        # Preservar os underscores
                        temp_part = part.replace('_', '___TEMP___')
                        # Codificar a parte
                        encoded_part = urllib.parse.quote(temp_part)
                        # Restaurar os underscores
                        encoded_part = encoded_part.replace('___TEMP___', '_')
                        encoded_parts.append(encoded_part)
                
                encoded_path = '/' + '/'.join(encoded_parts)
                
                logger.info(f"Testando caminho: {test_path}")
                logger.info(f"Codificado como: {encoded_path}")
                
                # Criar um arquivo de teste simples
                test_content = f"Teste de upload para {test_path} - {datetime.now()}".encode('utf-8')
                test_filename = f"teste_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
                
                # Tentar fazer upload
                upload_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')/Files/add(url='{test_filename}',overwrite=true)"
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                    "Accept": "application/json;odata=verbose"
                }
                
                logger.info(f"URL de upload: {upload_url}")
                
                response = await make_request(upload_url, method="POST", data=test_content, headers=headers)
                
                logger.info(f"Resposta de upload: {response.status_code}")
                success = response.status_code == 200 or response.status_code == 201
                
                results.append({
                    "path": test_path,
                    "encoded_path": encoded_path,
                    "success": success,
                    "status_code": response.status_code,
                    "filename": test_filename
                })
            
            except Exception as e:
                results.append({
                    "path": test_path,
                    "error": str(e),
                    "success": False
                })
        
        return {
            "results": results,
            "overall_success": any(r["success"] for r in results)
        }
    except Exception as e:
        logger.error(f"Erro no teste global: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

@router.post("/cancel-process")
async def cancel_process():
    """
    Cancela o processo de cópia de arquivos em andamento.
    """
    global PROCESS_CANCELLED
    try:
        logger.info("[REPOSITORY] Solicitação de cancelamento de processo recebida")
        PROCESS_CANCELLED = True
        return {"success": True, "message": "Processo de cópia cancelado"}
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao cancelar processo: {str(e)}")
        return {"success": False, "error": str(e)}

def check_if_cancelled():
    """
    Verifica se o processo atual foi cancelado.
    
    Returns:
        bool: True se o processo foi cancelado, False caso contrário
    """
    global PROCESS_CANCELLED
    return PROCESS_CANCELLED

@router.post("/reset-process")
async def reset_process():
    """
    Reinicia o estado do processo, permitindo que um novo comece.
    """
    global PROCESS_CANCELLED
    try:
        logger.info("[REPOSITORY] Reiniciando estado do processo")
        PROCESS_CANCELLED = False
        return {"success": True, "message": "Estado do processo reiniciado"}
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao reiniciar processo: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/process-status")
async def get_process_status():
    """
    Retorna o status atual do processo.
    """
    global PROCESS_CANCELLED
    try:
        status = "cancelled" if PROCESS_CANCELLED else "active"
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao obter status do processo: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/test-url-formation")
async def test_url_formation():
    """
    Endpoint para testar a formação de URLs para o SharePoint.
    Útil para diagnóstico de problemas com caminhos.
    """
    try:
        # Obter autenticação
        token, site_url = await get_sharepoint_auth()
        
        if not token:
            return {"success": False, "error": "Falha ao obter token de autenticação"}
        
        # Teste URLs de origem
        src_results = {}
        for key, original_path in ORIGINAL_PATHS.items():
            encoded_path = PATHS[key]
            api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')"
            
            src_results[key] = {
                "original_path": original_path,
                "encoded_path": encoded_path,
                "api_url": api_url
            }
        
        # Teste URLs de destino
        dest_results = {}
        for key, original_path in REPOSITORY_PATHS.items():
            encoded_path = REPOSITORY_PATHS[key]
            api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')"
            
            dest_results[key] = {
                "original_path": original_path,
                "encoded_path": encoded_path,
                "api_url": api_url
            }
        
        # Teste de codificação para um exemplo com caracteres especiais
        special_path = "/Documentos/Repositório_Faturas_Auto/Nota_Fiscal_Serviço"
        encoded_special = encode_sharepoint_path(special_path)
        
        return {
            "success": True,
            "site_url": site_url,
            "source_paths": src_results,
            "destination_paths": dest_results,
            "test_special_chars": {
                "original": special_path,
                "encoded": encoded_special
            }
        }
    except Exception as e:
        logger.error(f"[URL TEST] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

@router.get("/test-curl-exact")
async def test_curl_exact():
    """
    Implementação exata do comando curl que funcionou, com logs detalhados
    """
    try:
        # Obter autenticação
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            return {"success": False, "error": "Falha ao obter token"}
        
        # Logs para verificar o token e site_url
        logger.info(f"[CURL-EXACT] Token obtido (primeiros 20 caracteres): {token[:20]}...")
        logger.info(f"[CURL-EXACT] Site URL: {site_url}")
        
        # Usar exatamente o mesmo caminho do curl
        folder_path = "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar"
        test_filename = f"teste_curl_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        
        # Criar um arquivo de teste simples
        test_content = f"Teste exato de curl - {datetime.now()}".encode('utf-8')
        
        # Construir a URL exatamente como no curl
        url = f"https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(overwrite=true,url='{test_filename}')"
        
        logger.info(f"[CURL-EXACT] URL construída: {url}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/json;odata=verbose"
        }
        
        logger.info(f"[CURL-EXACT] Headers: {headers}")
        
        # Fazer o upload usando requests (não aiohttp, para ser o mais próximo possível do curl)
        response = requests.post(url, headers=headers, data=test_content)
        
        logger.info(f"[CURL-EXACT] Status code: {response.status_code}")
        logger.info(f"[CURL-EXACT] Resposta: {response.text[:500]}...")
        
        success = response.status_code in [200, 201]
        
        return {
            "success": success,
            "status_code": response.status_code,
            "path": folder_path,
            "filename": test_filename,
            "timestamp": str(datetime.now()),
            "response_snippet": response.text[:200] if response.text else None
        }
    except Exception as e:
        logger.error(f"[CURL-EXACT] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

async def upload_file_to_repository(token, file_content, file_name, destination_path):
    """
    Função de upload que usa diretamente a URL que sabemos que funciona.
    Esta função substitui a chamada para 'upload_file' em copy_file_to_repository.
    """
    try:
        # IMPORTANTE: Usar a URL base correta
        base_url = "https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos"
        encoded_file_name = urllib.parse.quote(file_name)
        
        # Construir URL exatamente como no teste que funcionou
        upload_url = f"{base_url}/_api/web/GetFolderByServerRelativeUrl('{destination_path}')/Files/add(overwrite=true,url='{encoded_file_name}')"
        
        logger.info(f"[UPLOAD_REPO] URL completa: {upload_url}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/json;odata=verbose"
        }
        
        # Se file_content é BytesIO, precisamos obter os bytes reais
        if isinstance(file_content, BytesIO):
            file_content.seek(0)
            content = file_content.read()
        else:
            content = file_content
        
        # Fazer o request com requests (síncrono mas dentro de async function)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(upload_url, headers=headers, data=content)
        )
        
        logger.info(f"[UPLOAD_REPO] Status: {response.status_code}")
        logger.info(f"[UPLOAD_REPO] Resposta: {response.text[:200]}...")
        
        if response.status_code in [200, 201]:
            logger.info(f"[UPLOAD_REPO] Arquivo {file_name} enviado com sucesso para {destination_path}")
            return True
        else:
            logger.error(f"[UPLOAD_REPO] Falha ao enviar arquivo {file_name}: {response.status_code}")
            logger.error(f"[UPLOAD_REPO] Resposta: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"[UPLOAD_REPO] Exceção ao fazer upload: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.get("/debug-auth")
async def debug_auth():
    """
    Endpoint para depurar a autenticação e URLs
    """
    try:
        # Carregar ambiente
        load_dotenv()
        
        # Obter variáveis de ambiente
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")[:5] + "..." if os.getenv("CLIENT_SECRET") else None
        tenant_id = os.getenv("TENANT_ID")
        resource = os.getenv("RESOURCE")
        site_url = os.getenv("SITE_URL")
        
        # Obter token via SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        auth_site_url = auth.site_url
        
        # Montar URL como no curl que funcionou
        test_folder = "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar"
        test_filename = "test.txt"
        
        # URL que funcionou no Postman 
        working_url = f"https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        # URL que seria construída com SITE_URL
        current_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        # URL que seria construída com auth.site_url
        auth_url = f"{auth_site_url}/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        return {
            "env_vars": {
                "client_id": client_id,
                "client_secret_masked": client_secret,
                "tenant_id": tenant_id,
                "resource": resource,
                "site_url": site_url,
            },
            "auth_info": {
                "token_obtained": token is not None,
                "token_first_20": token[:20] + "..." if token else None,
                "auth_site_url": auth_site_url,
            },
            "urls": {
                "working_url_from_curl": working_url,
                "current_url_from_env": current_url,
                "auth_url": auth_url,
            }
        }
    except Exception as e:
        logger.error(f"[DEBUG-AUTH] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}
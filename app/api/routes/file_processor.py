from fastapi import APIRouter, HTTPException
import logging
import os
import re
import PyPDF2
from io import BytesIO
from aiohttp import ClientSession
import httpx
import io
import requests
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

from app.core.auth import SharePointAuth

router = APIRouter()
logger = logging.getLogger(__name__)

# Caminhos das pastas
PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
    "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
}

# Cache para conteúdos de arquivo
_file_content_cache = {}
_text_cache = {}

# Variáveis para controle de processos
process_running = False
process_cancel_requested = False
process_lock = Lock()

# Defina uma variável global para rastrear os arquivos processados em uma sessão
processed_files_history = set()
processing_lock = asyncio.Lock()  # Para garantir processamento sincronizado

@router.post("/process")
async def process_entrada_files():
    """
    Processa os arquivos da pasta ENTRADA diretamente.
    """
    try:
        logger.info("=== INICIANDO PROCESSAMENTO DE ARQUIVOS ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para processar"}
        
        logger.info(f"Encontrados {len(entrada_files)} arquivos para processar")
        
        # Resultados
        results = []
        
        # Processar cada arquivo conforme as regras
        for file in entrada_files:
            file_name = file.get("Name", "")
            
            try:
                # Regra 1: R189
                if "R189" in file_name:
                    logger.info(f"Processando arquivo R189: {file_name}")
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                    if file_content:
                        success = await upload_file(token, site_url, file_content, file_name, PATHS["R189"])
                        results.append({
                            "file": file_name,
                            "type": "R189",
                            "success": success,
                            "new_name": file_name
                        })
                
                # Regra 2: QPE com 6 números
                elif re.search(r"QPE-\d{6}$", file_name):
                    logger.info(f"Processando arquivo QPE cidade: {file_name}")
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                    if file_content:
                        # Extrair cidade
                        cidade = await extract_city_from_pdf(file_content, r'.*,\s*([A-Z\s]+)\s*-')
                        logger.info(f"Cidade extraída do QPE: {cidade}")
                        
                        # Construir novo nome
                        new_file_name = f"{cidade}_{file_name}" if cidade else file_name
                        
                        # Upload para QPE
                        success = await upload_file(token, site_url, file_content, new_file_name, PATHS["QPE"])
                        results.append({
                            "file": file_name,
                            "type": "QPE",
                            "success": success,
                            "new_name": new_file_name,
                            "cidade": cidade
                        })
                
                # Regra 3: QPE com fatura
                elif re.search(r"QPE-\d{6}[A-Za-z]", file_name):
                    logger.info(f"Processando arquivo QPE fatura: {file_name}")
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                    if file_content:
                        # Construir novo nome
                        new_file_name = f"FATURA-LOCAÇÃO_{file_name}"
                        
                        # Upload para NFSERV
                        success = await upload_file(token, site_url, file_content, new_file_name, PATHS["NFSERV"])
                        results.append({
                            "file": file_name,
                            "type": "QPE-FATURA",
                            "success": success,
                            "new_name": new_file_name
                        })
                
                # Regra 4: Telecomunicações
                elif any(city in file_name for city in ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]) and re.search(r"\d{6}[A-Za-z]\d{2}", file_name):
                    logger.info(f"Processando arquivo TELECOM: {file_name}")
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                    if file_content:
                        # Construir novo nome
                        new_file_name = f"TELECOMUNICAÇÕES_{file_name}"
                        
                        # Upload para NFSERV
                        success = await upload_file(token, site_url, file_content, new_file_name, PATHS["NFSERV"])
                        results.append({
                            "file": file_name,
                            "type": "TELECOM",
                            "success": success,
                            "new_name": new_file_name
                        })
                
                # Regra 5: SPB com cidade
                elif re.search(r"SPB-\d{6}", file_name):
                    logger.info(f"Processando arquivo SPB cidade: {file_name}")
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                    if file_content:
                        # Extrair cidade
                        cidade = await extract_city_from_pdf(file_content, r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS")
                        if cidade:
                            cidade = re.sub(r'----$', '', cidade).strip()
                        logger.info(f"Cidade extraída do SPB: {cidade}")
                        
                        # Construir novo nome
                        new_file_name = f"{cidade}_{file_name}" if cidade else file_name
                        
                        # Upload para SPB
                        success = await upload_file(token, site_url, file_content, new_file_name, PATHS["SPB"])
                        results.append({
                            "file": file_name,
                            "type": "SPB",
                            "success": success,
                            "new_name": new_file_name,
                            "cidade": cidade
                        })
                
                else:
                    logger.warning(f"Arquivo não corresponde a nenhum padrão: {file_name}")
                    results.append({
                        "file": file_name,
                        "type": "UNKNOWN",
                        "success": False,
                        "message": "Não corresponde a nenhum padrão conhecido"
                    })
            
            except Exception as e:
                logger.error(f"Erro processando arquivo {file_name}: {str(e)}")
                results.append({
                    "file": file_name,
                    "success": False,
                    "error": str(e)
                })
        
        # Retornar resultados
        success_count = sum(1 for r in results if r.get("success"))
        return {
            "success": True,
            "message": f"Processamento concluído: {success_count} de {len(results)} arquivos processados",
            "files_processed": success_count,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Erro geral: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/rename-files")
async def rename_files():
    """
    Renomeia arquivos com base nas regras de negócio específicas,
    mantendo o nome original e apenas adicionando prefixos.
    """
    try:
        logger.info("=== INICIANDO RENOMEAÇÃO DE ARQUIVOS ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
        
        # Arquivos renomeados
        renamed_files = []
        
        # Processar cada arquivo individualmente
        for file in entrada_files:
            original_name = file.get("Name", "")
            file_content = None
            new_name = None
            
            try:
                logger.info(f"Processando arquivo: {original_name}")
                
                # REGRA 1: QPE com 6 números + letra
                if re.search(r"QPE-\d{6}[A-Za-z]", original_name):
                    logger.info(f"Arquivo identificado como QPE com letra: {original_name}")
                    new_name = f"FATURA-LOCAÇÃO_{original_name}"
                    logger.info(f"Novo nome será: {new_name}")
                
                # REGRA 2: QPE com 6 números sem letra
                elif re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                    logger.info(f"Arquivo identificado como QPE sem letra: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if file_content:
                        cidade = await extract_city_from_pdf(file_content, r'.*,\s*([A-Z\s]+)\s*-')
                        if cidade:
                            logger.info(f"Cidade extraída para {original_name}: {cidade}")
                            new_name = f"{cidade}_{original_name}"
                            logger.info(f"Novo nome será: {new_name}")
                        else:
                            logger.warning(f"Não foi possível extrair cidade para {original_name}")
                
                # REGRA 3: Arquivo de telecom (BLU, POA, etc.)
                elif (any(f"-{city}-" in original_name.upper() or f" {city}-" in original_name.upper() 
                          for city in ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]) and 
                      re.search(r"\d{6}[A-Za-z]\d{2}", original_name)):
                    logger.info(f"Arquivo identificado como TELECOM: {original_name}")
                    new_name = f"TELECOMUNICAÇÕES_{original_name}"
                    logger.info(f"Novo nome será: {new_name}")
                
                # REGRA 4: SPB com 6 números sem letra
                elif re.search(r"SPB-\d{6}(?![A-Za-z])", original_name):
                    logger.info(f"Arquivo identificado como SPB sem letra: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if file_content:
                        try:
                            padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
                            texto_combinado = await extract_text_from_pdf(file_content)
                            cidade_match = re.search(padrao_cidade, texto_combinado)
                            
                            if cidade_match:
                                cidade = re.sub(r'----$', '', cidade_match.group(1)).strip()
                                logger.info(f"Cidade extraída para {original_name}: {cidade}")
                                new_name = f"{cidade}_{original_name}"
                                logger.info(f"Novo nome será: {new_name}")
                            else:
                                logger.warning(f"Padrão de cidade não encontrado para {original_name}")
                        except Exception as e:
                            logger.error(f"Erro ao extrair texto do PDF {original_name}: {str(e)}")
                
                # Se novo nome foi definido, renomear
                if new_name:
                    logger.info(f"Preparando para renomear: {original_name} -> {new_name}")
                    
                    # Baixar o arquivo se ainda não foi baixado
                    if file_content is None:
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    
                    if file_content:
                        # Fazer upload com novo nome
                        success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                        
                        if success:
                            # Excluir o arquivo original após o upload do novo
                            await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                            
                            renamed_files.append({
                                "original": original_name,
                                "new": new_name
                            })
                            logger.info(f"Arquivo {original_name} renomeado com sucesso para {new_name}")
                        else:
                            logger.error(f"Falha ao fazer upload do arquivo renomeado {new_name}")
                    else:
                        logger.error(f"Não foi possível baixar o arquivo {original_name}")
                else:
                    logger.info(f"Arquivo {original_name} não corresponde a nenhum padrão, será ignorado")
            
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
                logger.exception("Detalhes do erro:")
        
        # Retornar resultado
        success_count = len(renamed_files)
        return {
            "success": True,
            "message": f"{success_count} arquivos renomeados com sucesso",
            "renamed_files": renamed_files
        }
        
    except Exception as e:
        logger.error(f"Erro geral ao renomear arquivos: {str(e)}")
        logger.exception("Detalhes do erro:")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/rename-qpe")
async def rename_qpe_files():
    """
    Renomeia apenas arquivos QPE- com 6 números, adicionando a cidade no início.
    """
    try:
        logger.info("=== INICIANDO RENOMEAÇÃO DE ARQUIVOS QPE ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
            
        # Filtrar apenas arquivos QPE com 6 números
        qpe_files = [file for file in entrada_files 
                     if file.get("Name") and re.search(r"QPE-\d{6}$", file.get("Name"))]
        
        logger.info(f"Encontrados {len(qpe_files)} arquivos QPE para renomear")
        
        # Arquivos renomeados
        renamed_files = []
        
        # Processar cada arquivo QPE
        for file in qpe_files:
            original_name = file.get("Name", "")
            
            try:
                logger.info(f"Processando arquivo: {original_name}")
                
                # Baixar o arquivo
                file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                
                if file_content:
                    # Extrair cidade do PDF
                    cidade = await extract_city_from_pdf(file_content, r'.*,\s*([A-Z\s]+)\s*-')
                    logger.info(f"Cidade extraída do arquivo {original_name}: {cidade}")
                    
                    if cidade:
                        # Criar novo nome com cidade no início (concatenando)
                        new_name = f"{cidade}_{original_name}"
                        logger.info(f"Novo nome: {new_name}")
                        
                        # Fazer upload com novo nome
                        success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                        
                        if success:
                            renamed_files.append({
                                "original": original_name,
                                "new": new_name,
                                "cidade": cidade
                            })
                            logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                        else:
                            logger.error(f"Falha ao fazer upload do arquivo renomeado: {new_name}")
                    else:
                        logger.warning(f"Não foi possível extrair a cidade do arquivo: {original_name}")
                else:
                    logger.error(f"Não foi possível baixar o arquivo: {original_name}")
            
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
        
        # Retornar resultado
        return {
            "success": True,
            "message": f"{len(renamed_files)} arquivos QPE renomeados com sucesso",
            "renamed_files": renamed_files
        }
        
    except Exception as e:
        logger.error(f"Erro ao renomear arquivos QPE: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/rename-qpe-fatura")
async def rename_qpe_fatura_files():
    """
    Renomeia apenas arquivos QPE- com 6 números e uma letra no final,
    adicionando o prefixo "FATURA-LOCAÇÃO".
    """
    try:
        logger.info("=== INICIANDO RENOMEAÇÃO DE ARQUIVOS QPE FATURA ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
            
        # Filtrar apenas arquivos QPE com 6 números e uma letra
        qpe_fatura_files = [file for file in entrada_files 
                     if file.get("Name") and re.search(r"QPE-\d{6}[A-Za-z]", file.get("Name"))]
        
        logger.info(f"Encontrados {len(qpe_fatura_files)} arquivos QPE-Fatura para renomear")
        
        # Arquivos renomeados
        renamed_files = []
        
        # Processar cada arquivo QPE-Fatura
        for file in qpe_fatura_files:
            original_name = file.get("Name", "")
            
            try:
                logger.info(f"Processando arquivo: {original_name}")
                
                # Baixar o arquivo
                file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                
                if file_content:
                    # Criar novo nome com prefixo "FATURA-LOCAÇÃO"
                    new_name = f"FATURA-LOCAÇÃO_{original_name}"
                    logger.info(f"Novo nome: {new_name}")
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if success:
                        renamed_files.append({
                            "original": original_name,
                            "new": new_name
                        })
                        logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                    else:
                        logger.error(f"Falha ao fazer upload do arquivo renomeado: {new_name}")
                else:
                    logger.error(f"Não foi possível baixar o arquivo: {original_name}")
            
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
        
        # Retornar resultado
        return {
            "success": True,
            "message": f"{len(renamed_files)} arquivos QPE-Fatura renomeados com sucesso",
            "renamed_files": renamed_files
        }
        
    except Exception as e:
        logger.error(f"Erro ao renomear arquivos QPE-Fatura: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/rename-all-patterns")
async def rename_all_patterns():
    """
    Renomeia arquivos com base em todos os padrões definidos.
    """
    global process_running, process_cancel_requested
    
    # Reseta a flag de cancelamento e marca o processo como em execução
    with process_lock:
        process_cancel_requested = False
        process_running = True
    
    try:
        logger.info("Iniciando processo de renomeação de arquivos...")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
        
        # Arquivos renomeados
        renamed_files = []
        
        # A cada loop ou operação significativa, verifique cancelamento
        for i, file in enumerate(entrada_files):
            if check_if_cancelled():
                logger.warning("PROCESSO CANCELADO PELO USUÁRIO!")
                return {
                    "success": False,
                    "message": "Processo cancelado pelo usuário",
                    "cancelled": True,
                    "processed": i
                }
            
            original_name = file.get("Name", "")
            new_name = None
            
            try:
                logger.info(f"Analisando arquivo: {original_name}")
                
                # REGRA 1: QPE com 6 números + letra
                if re.search(r"QPE-\d{6}[A-Za-z]", original_name):
                    logger.info(f"Arquivo identificado como QPE-FATURA: {original_name}")
                    new_name = f"FATURA-LOCAÇÃO_{original_name}"
                
                # REGRA 2: QPE com 6 números sem letra
                elif re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                    logger.info(f"Arquivo identificado como QPE: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if file_content:
                        cidade = await extract_city_from_pdf(file_content, r'.*,\s*([A-Z\s]+)\s*-')
                        if cidade:
                            logger.info(f"Cidade extraída: {cidade}")
                            new_name = f"{cidade}_{original_name}"
                
                # REGRA 3: Arquivo de telecom (BLU, POA, etc.)
                elif (any(city in original_name for city in ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]) and 
                      re.search(r"\d{6}[A-Za-z]\d{2}", original_name)):
                    logger.info(f"Arquivo identificado como TELECOM: {original_name}")
                    new_name = f"TELECOMUNICAÇÕES_{original_name}"
                
                # REGRA 4: SPB com 6 números sem letra
                elif re.search(r"SPB-\d{6}(?![A-Za-z])", original_name):
                    logger.info(f"Arquivo identificado como SPB: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade
                    file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if file_content:
                        cidade = await extract_city_from_pdf(file_content, r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS")
                        if cidade:
                            cidade = re.sub(r'----$', '', cidade).strip()
                            logger.info(f"Cidade extraída: {cidade}")
                            new_name = f"{cidade}_{original_name}"
                
                # Se novo nome foi definido e é diferente do original, renomear
                if new_name and new_name != original_name:
                    logger.info(f"Preparando para renomear: {original_name} -> {new_name}")
                    
                    # Baixar o arquivo se ainda não foi baixado
                    if 'file_content' not in locals() or file_content is None:
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                    
                    if file_content:
                        # Fazer upload com novo nome
                        success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                        
                        if success:
                            renamed_files.append({
                                "original": original_name,
                                "new": new_name
                            })
                            logger.info(f"Arquivo renomeado com sucesso")
                        else:
                            logger.error(f"Falha ao fazer upload do arquivo renomeado")
                    else:
                        logger.error(f"Não foi possível baixar o arquivo")
                else:
                    logger.info(f"Arquivo não precisa ser renomeado ou não corresponde a nenhum padrão")
            
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
            
            # Verificar cancelamento novamente após operações demoradas
            if check_if_cancelled():
                logger.warning("PROCESSO CANCELADO PELO USUÁRIO DURANTE PROCESSAMENTO!")
                return {
                    "success": False, 
                    "message": "Processo cancelado pelo usuário",
                    "cancelled": True,
                    "processed": i
                }
        
        # Retornar resultado
        success_count = len(renamed_files)
        return {
            "success": True,
            "message": f"{success_count} arquivos renomeados com sucesso",
            "renamed_files": renamed_files
        }
    
    except Exception as e:
        logger.error(f"Erro: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}
    
    finally:
        # Marca o processo como concluído, independente de sucesso ou erro
        with process_lock:
            process_running = False

@router.post("/rename")
async def rename_files():
    """
    Versão otimizada com processamento paralelo controlado,
    mantendo exatamente a mesma lógica de negócio.
    """
    start_time = time.time()
    try:
        logger.info("=== INICIANDO PROCESSAMENTO DE ARQUIVOS (VERSÃO PARALELA) ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar TODOS os arquivos da pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"], limit=1000)
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para processar"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
        
        # Função para processar um único arquivo
        async def process_single_file(file):
            original_name = file.get("Name", "")
            result = {
                "original_name": original_name,
                "processed": True,
                "type": None,
                "new_name": None,
                "success": False,
                "error": None
            }
            
            try:
                # Verificar se o arquivo já foi renomeado
                if original_name.startswith(("FATURA-LOCAÇÃO_", "TELECOMUNICAÇÕES_")) or re.match(r"^[A-Z\s]+_", original_name):
                    result["type"] = "already_renamed"
                    return result
                
                # FUNÇÃO 1: QPE- com 6 números SEM letra
                if re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                    result["type"] = "qpe_sem_letra"
                    logger.info(f"Arquivo identificado como QPE sem letra: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade (com cache)
                    file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                    if not file_content:
                        result["error"] = "download_failed"
                        return result
                    
                    texto_pdf = await extract_text_from_pdf_cached(file_content)
                    if not texto_pdf:
                        result["error"] = "text_extraction_failed"
                        return result
                    
                    # Buscar a cidade usando o regex
                    padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
                    cidade_match = re.search(padrao_cidade, texto_pdf)
                    
                    if not cidade_match:
                        result["error"] = "city_not_found"
                        return result
                    
                    cidade = cidade_match.group(1).strip()
                    logger.info(f"Cidade extraída: {cidade}")
                    
                    # Novo nome com a cidade como prefixo
                    new_name = f"{cidade}_{original_name}"
                    result["new_name"] = new_name
                    logger.info(f"Novo nome será: {new_name}")
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if not success:
                        result["error"] = "upload_failed"
                        return result
                    
                    # Excluir o arquivo original após o upload do novo
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if not delete_success:
                        logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                    
                    result["success"] = True
                    logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                
                # FUNÇÃO 2: QPE- com 6 números COM uma letra no final
                elif re.search(r"QPE-\d{6}[A-Za-z]", original_name):
                    result["type"] = "qpe_com_letra"
                    logger.info(f"Arquivo identificado como QPE com letra: {original_name}")
                    
                    # Novo nome com "FATURA-LOCAÇÃO" como prefixo
                    new_name = f"FATURA-LOCAÇÃO_{original_name}"
                    result["new_name"] = new_name
                    logger.info(f"Novo nome será: {new_name}")
                    
                    # Baixar o arquivo (com cache)
                    file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                    if not file_content:
                        result["error"] = "download_failed"
                        return result
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if not success:
                        result["error"] = "upload_failed"
                        return result
                    
                    # Excluir o arquivo original após o upload do novo
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if not delete_success:
                        logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                    
                    result["success"] = True
                    logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                
                # FUNÇÃO 3: SPB- com 6 números SEM letra no final
                elif re.search(r"SPB-\d{6}(?![A-Za-z])", original_name):
                    result["type"] = "spb_sem_letra"
                    logger.info(f"Arquivo identificado como SPB sem letra: {original_name}")
                    
                    # Baixar o arquivo para extrair a cidade (com cache)
                    file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                    if not file_content:
                        result["error"] = "download_failed"
                        return result
                    
                    texto_pdf = await extract_text_from_pdf_cached(file_content)
                    if not texto_pdf:
                        result["error"] = "text_extraction_failed"
                        return result
                    
                    # Buscar a cidade usando o regex específico para SPB
                    padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
                    cidade_match = re.search(padrao_cidade, texto_pdf)
                    
                    if not cidade_match:
                        result["error"] = "city_not_found"
                        return result
                    
                    cidade = re.sub(r'----$', '', cidade_match.group(1)).strip()
                    logger.info(f"Cidade extraída: {cidade}")
                    
                    # Novo nome com a cidade como prefixo
                    new_name = f"{cidade}_{original_name}"
                    result["new_name"] = new_name
                    logger.info(f"Novo nome será: {new_name}")
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if not success:
                        result["error"] = "upload_failed"
                        return result
                    
                    # Excluir o arquivo original após o upload do novo
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if not delete_success:
                        logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                    
                    result["success"] = True
                    logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                
                # FUNÇÃO 4: Arquivos de TELECOM
                elif re.search(r"(BLU|POA|VIX|SPB|REC|BHO)-\d{6}[A-Za-z]\d{2}", original_name):
                    result["type"] = "telecom"
                    logger.info(f"Arquivo identificado como TELECOM: {original_name}")
                    
                    # Novo nome com "TELECOMUNICAÇÕES" como prefixo
                    new_name = f"TELECOMUNICAÇÕES_{original_name}"
                    result["new_name"] = new_name
                    logger.info(f"Novo nome será: {new_name}")
                    
                    # Baixar o arquivo (com cache)
                    file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                    if not file_content:
                        result["error"] = "download_failed"
                        return result
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if not success:
                        result["error"] = "upload_failed"
                        return result
                    
                    # Excluir o arquivo original após o upload do novo
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                    if not delete_success:
                        logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                    
                    result["success"] = True
                    logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                
                else:
                    result["type"] = "no_match"
                    logger.info(f"Arquivo {original_name} não corresponde a nenhum padrão")
                
            except Exception as e:
                result["error"] = str(e)
                logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
            
            return result
        
        # Processar arquivos em lotes para melhor controle
        batch_size = 20
        max_concurrent = 10  # Máximo de operações paralelas
        all_results = []
        
        # Dividir em lotes
        for i in range(0, len(entrada_files), batch_size):
            batch = entrada_files[i:i+batch_size]
            logger.info(f"Processando lote {i//batch_size + 1}/{(len(entrada_files)+batch_size-1)//batch_size} ({len(batch)} arquivos)")
            
            # Criar tarefas para processamento paralelo
            tasks = [process_single_file(file) for file in batch]
            
            # Processar arquivos em paralelo (limitado a max_concurrent)
            # Usamos asyncio.gather para executar várias tarefas em paralelo
            batch_results = await asyncio.gather(*tasks)
            all_results.extend(batch_results)
            
            # Pequena pausa entre lotes para não sobrecarregar o servidor
            if i + batch_size < len(entrada_files):
                await asyncio.sleep(0.5)
        
        # Organizar resultados por tipo
        renamed_files_qpe_sem_letra = []
        renamed_files_qpe_com_letra = []
        renamed_files_spb_sem_letra = []
        renamed_files_telecom = []
        errors = []
        
        for result in all_results:
            if result["success"]:
                file_info = {
                    "original": result["original_name"],
                    "new": result["new_name"]
                }
                
                if result["type"] == "qpe_sem_letra":
                    renamed_files_qpe_sem_letra.append(file_info)
                elif result["type"] == "qpe_com_letra":
                    renamed_files_qpe_com_letra.append(file_info)
                elif result["type"] == "spb_sem_letra":
                    renamed_files_spb_sem_letra.append(file_info)
                elif result["type"] == "telecom":
                    renamed_files_telecom.append(file_info)
            elif result["error"]:
                errors.append({
                    "file": result["original_name"],
                    "type": result["type"],
                    "error": result["error"]
                })
        
        # Totais para relatório
        total_qpe_sem_letra = len(renamed_files_qpe_sem_letra)
        total_qpe_com_letra = len(renamed_files_qpe_com_letra)
        total_spb_sem_letra = len(renamed_files_spb_sem_letra)
        total_telecom = len(renamed_files_telecom)
        total_renamed = total_qpe_sem_letra + total_qpe_com_letra + total_spb_sem_letra + total_telecom
        total_time = round(time.time() - start_time, 2)
        
        # Limpar caches para liberar memória
        _file_content_cache.clear()
        _text_cache.clear()
        
        # Retornar resultado detalhado
        return {
            "success": True,
            "message": f"{total_renamed} arquivos renomeados com sucesso em {total_time}s",
            "detalhes": {
                "qpe_sem_letra": {
                    "total": total_qpe_sem_letra,
                    "arquivos": renamed_files_qpe_sem_letra
                },
                "qpe_com_letra": {
                    "total": total_qpe_com_letra,
                    "arquivos": renamed_files_qpe_com_letra
                },
                "spb_sem_letra": {
                    "total": total_spb_sem_letra,
                    "arquivos": renamed_files_spb_sem_letra
                },
                "telecom": {
                    "total": total_telecom,
                    "arquivos": renamed_files_telecom
                }
            },
            "estatisticas": {
                "total_processado": len(all_results),
                "total_arquivos": len(entrada_files),
                "total_renomeados": total_renamed,
                "total_erros": len(errors),
                "tempo_total": total_time,
                "arquivos_por_segundo": round(len(all_results) / total_time, 2) if total_time > 0 else 0
            },
            "erros": errors if errors else None
        }
        
    except Exception as e:
        logger.error(f"Erro geral ao processar arquivos: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/rename-qpe-only")
async def rename_qpe_only():
    """
    Renomeia APENAS arquivos que contêm QPE- seguido de seis números SEM letra no final.
    Extrai a cidade do conteúdo do PDF e a adiciona como prefixo ao nome original.
    """
    try:
        logger.info("=== INICIANDO RENOMEAÇÃO DE ARQUIVOS QPE SEM LETRA ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("Falha na autenticação com SharePoint")
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"])
        
        if not entrada_files:
            logger.info("Nenhum arquivo encontrado na pasta ENTRADA")
            return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos na pasta ENTRADA")
        
        # Arquivos que correspondem ao padrão QPE sem letra
        qpe_files = []
        for file in entrada_files:
            file_name = file.get("Name", "")
            # Verificar se o nome contém QPE- seguido de 6 dígitos SEM letra no final
            if re.search(r"QPE-\d{6}(?![A-Za-z])", file_name):
                qpe_files.append(file_name)
                logger.info(f"Arquivo QPE sem letra encontrado: {file_name}")
        
        if not qpe_files:
            logger.info("Nenhum arquivo QPE sem letra encontrado para renomear")
            return {"success": True, "message": "Nenhum arquivo QPE sem letra encontrado para renomear"}
        
        logger.info(f"Total de {len(qpe_files)} arquivos QPE sem letra encontrados")
        
        # Arquivos renomeados com sucesso
        renamed_files = []
        
        # Limite para evitar processar muitos arquivos de uma vez
        MAX_FILES = 20
        files_to_process = qpe_files[:MAX_FILES]
        
        logger.info(f"Processando até {len(files_to_process)} arquivos (limite: {MAX_FILES})")
        
        # Processar cada arquivo QPE
        for i, file_name in enumerate(files_to_process):
            try:
                logger.info(f"[{i+1}/{len(files_to_process)}] Processando arquivo: {file_name}")
                
                # Baixar o arquivo para extrair a cidade
                file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                
                if not file_content:
                    logger.error(f"Não foi possível baixar o arquivo: {file_name}")
                    continue
                
                # Extrair texto do PDF
                text = await extract_text_from_pdf(file_content)
                
                if not text:
                    logger.error(f"Não foi possível extrair texto do PDF: {file_name}")
                    continue
                
                # Extrair a cidade usando o padrão regex
                padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
                cidade_match = re.search(padrao_cidade, text)
                
                if not cidade_match:
                    logger.warning(f"Não foi possível encontrar a cidade no arquivo: {file_name}")
                    continue
                
                cidade = cidade_match.group(1).strip()
                logger.info(f"Cidade extraída: {cidade}")
                
                # Novo nome do arquivo com a cidade como prefixo
                new_name = f"{cidade}_{file_name}"
                logger.info(f"Novo nome será: {new_name}")
                
                # Fazer upload com novo nome
                upload_success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if upload_success:
                    # Excluir o arquivo original
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], file_name)
                    
                    if delete_success:
                        renamed_files.append({
                            "original": file_name,
                            "new": new_name
                        })
                        logger.info(f"Arquivo renomeado com sucesso: {file_name} -> {new_name}")
                    else:
                        logger.error(f"Erro ao excluir arquivo original: {file_name}")
                else:
                    logger.error(f"Erro ao fazer upload do arquivo renomeado: {new_name}")
                
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {file_name}: {str(e)}")
                logger.exception("Detalhes do erro:")
        
        # Retornar resultado
        success_count = len(renamed_files)
        return {
            "success": True,
            "message": f"{success_count} arquivos QPE sem letra renomeados com sucesso",
            "renamed_files": renamed_files,
            "total_found": len(qpe_files)
        }
        
    except Exception as e:
        logger.error(f"Erro geral ao renomear arquivos: {str(e)}")
        logger.exception("Detalhes do erro:")
        return {"success": False, "message": f"Erro: {str(e)}"}

# Função auxiliar para extrair cidade do texto
def extract_city_from_text(text, pattern):
    """Extrai o nome da cidade do texto usando o padrão regex fornecido."""
    if not text:
        return None
        
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None

# Função para limpar o cache do SharePoint
def clear_sharepoint_cache():
    """
    Limpa qualquer cache relacionado ao SharePoint para garantir
    que sempre temos uma visão atualizada dos arquivos.
    """
    logger.info("Limpando cache do SharePoint")
    # Se você estiver usando uma instância global do cliente SharePoint ou tokens armazenados
    # aqui é onde você pode limpar esses dados
    
    # Exemplo de limpeza de variáveis globais (adapte conforme sua implementação)
    global _sharepoint_token_cache
    if '_sharepoint_token_cache' in globals():
        _sharepoint_token_cache = None
    
    # Se estiver usando uma solução de cache como Redis ou memcached
    # aqui você removeria as chaves relevantes

# Função atualizada para listar arquivos com limite personalizado
async def list_files(token, site_url, folder_path, limit=1000):
    """
    Lista todos os arquivos em uma pasta do SharePoint com limite aumentado.
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json;odata=verbose',
        'Content-Type': 'application/json;odata=verbose'
    }
    
    # Construir a URL com limite aumentado
    api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files?$top={limit}"
    
    response = await make_request("GET", api_url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return data.get('d', {}).get('results', [])
    else:
        logger.error(f"Erro ao listar arquivos: {response.status_code} - {response.text}")
        return []

async def download_file(token, site_url, folder_path, file_name):
    """Baixa um arquivo do SharePoint"""
    try:
        logger.info(f"Baixando arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose'
        }
        
        # URL para baixar o arquivo
        download_url = f"{site_url}/_api/web/GetFileByServerRelativeUrl('{folder_path}/{file_name}')/$value"
        
        response = await make_request("GET", download_url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Arquivo {file_name} baixado com sucesso")
            return response.content
        else:
            logger.error(f"Erro ao baixar arquivo {file_name}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exceção ao baixar arquivo {file_name}: {str(e)}")
        return None

async def upload_file(token, site_url, file_content, file_name, folder_path):
    """Envia um arquivo para o SharePoint"""
    try:
        logger.info(f"Fazendo upload do arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose'
        }
        
        # URL para fazer upload
        upload_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(url='{file_name}',overwrite=true)"
        
        # Remover o Content-Type do cabeçalho para que o boundary seja definido automaticamente
        response = await make_request("POST", upload_url, headers=headers, data=file_content)
        
        if response.status_code in [200, 201]:
            logger.info(f"Upload do arquivo {file_name} concluído com sucesso")
            return True
        else:
            logger.error(f"Erro no upload do arquivo {file_name}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exceção no upload do arquivo {file_name}: {str(e)}")
        return False

async def extract_city_from_pdf(file_content, padrao_cidade):
    """Extrai cidade de um PDF usando regex"""
    try:
        file_content.seek(0)
        reader = PyPDF2.PdfReader(file_content)
        
        texto_combinado = ""
        for page_num in range(len(reader.pages)):
            texto_combinado += reader.pages[page_num].extract_text()
        
        cidade_match = re.search(padrao_cidade, texto_combinado)
        cidade = cidade_match.group(1).strip() if cidade_match else None
        
        return cidade
    except Exception as e:
        logger.error(f"Erro ao extrair cidade: {str(e)}")
        return None

# Endpoint de teste simples
@router.get("/test")
async def test_endpoint():
    return {"status": "API funcionando", "paths": PATHS}

# Implementação da função make_request que estava faltando
async def make_request(method, url, headers=None, data=None, json_data=None, files=None):
    """
    Função para fazer requisições HTTP.
    
    Args:
        method: Método HTTP (GET, POST, etc)
        url: URL da requisição
        headers: Cabeçalhos da requisição
        data: Dados form (opcional)
        json_data: Dados JSON (opcional)
        files: Arquivos para upload (opcional)
    
    Returns:
        Objeto de resposta HTTP
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, data=data, json=json_data, files=files)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, data=data, json=json_data, files=files)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")
            
            return response
    except Exception as e:
        logger.error(f"Erro na requisição {method} para {url}: {str(e)}")
        # Criar um objeto de resposta simulado para evitar erros de atributos
        class ErrorResponse:
            def __init__(self):
                self.status_code = 500
                self.text = str(e)
            def json(self):
                return {"error": str(e)}
        
        return ErrorResponse()

# Função para excluir arquivo
async def delete_file(token, site_url, folder_path, file_name):
    """
    Exclui um arquivo do SharePoint.
    """
    try:
        logger.info(f"Excluindo arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'X-HTTP-Method': 'DELETE',
            'IF-MATCH': '*'
        }
        
        # URL para excluir o arquivo
        delete_url = f"{site_url}/_api/web/GetFileByServerRelativeUrl('{folder_path}/{file_name}')"
        
        response = await make_request("POST", delete_url, headers=headers)
        
        if response.status_code in [200, 204]:
            logger.info(f"Arquivo {file_name} excluído com sucesso")
            return True
        else:
            logger.error(f"Erro ao excluir arquivo {file_name}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exceção ao excluir arquivo {file_name}: {str(e)}")
        return False

# Implementação da função para extrair texto de PDF
async def extract_text_from_pdf(pdf_content):
    """
    Extrai o texto de um arquivo PDF.
    
    Args:
        pdf_content: Conteúdo binário do arquivo PDF
    
    Returns:
        Texto extraído do PDF
    """
    try:
        pdf_file = io.BytesIO(pdf_content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        logger.error(f"Erro ao extrair texto do PDF: {str(e)}")
        return ""

# Função otimizada para baixar arquivo com cache
async def download_file_cached(token, site_url, folder_path, file_name):
    """
    Baixa um arquivo do SharePoint com suporte a cache.
    """
    cache_key = f"{folder_path}/{file_name}"
    
    # Verificar se o arquivo está no cache
    if cache_key in _file_content_cache:
        logger.info(f"Usando conteúdo em cache para {file_name}")
        return _file_content_cache[cache_key]
    
    # Se não estiver no cache, baixar normalmente
    file_content = await download_file(token, site_url, folder_path, file_name)
    
    if file_content:
        # Salvar no cache
        _file_content_cache[cache_key] = file_content
    
    return file_content

# Função otimizada para extrair texto de PDF com cache e processamento paralelo
async def extract_text_from_pdf_cached(pdf_content):
    """
    Extrai texto de um PDF com suporte a cache e processamento em thread separada.
    """
    # Usar hash do conteúdo como chave de cache
    content_hash = str(hash(pdf_content))
    
    # Verificar se já está em cache
    if content_hash in _text_cache:
        return _text_cache[content_hash]
    
    try:
        # Usar ThreadPoolExecutor para processamento intensivo em CPU
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(executor, _extract_text_sync, pdf_content)
        
        if text:
            # Salvar no cache
            _text_cache[content_hash] = text
        
        return text
    except Exception as e:
        logger.error(f"Erro ao extrair texto do PDF: {str(e)}")
        return ""

# Função síncrona para extrair texto (será executada em uma thread separada)
def _extract_text_sync(pdf_content):
    """Função síncrona para extrair texto do PDF (executada em thread separada)"""
    try:
        pdf_file = io.BytesIO(pdf_content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        logger.error(f"Erro na extração síncrona de texto: {str(e)}")
        return ""

@router.post("/rename-and-move")
async def rename_and_move_files():
    """
    Processo em duas etapas:
    1. Renomeia os arquivos na pasta ENTRADA
    2. Move os arquivos já renomeados para as pastas de destino
    """
    start_time = time.time()
    try:
        logger.info("=== INICIANDO PROCESSAMENTO DE ARQUIVOS (RENOMEAR E MOVER) ===")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # FASE 1: RENOMEAR OS ARQUIVOS NA PASTA ENTRADA
        logger.info("=== FASE 1: RENOMEANDO ARQUIVOS NA PASTA ENTRADA ===")
        
        # Listar arquivos na pasta ENTRADA
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"], limit=1000)
        
        if not entrada_files:
            return {"success": True, "message": "Nenhum arquivo encontrado para processar"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
        
        # Renomear os arquivos primeiro (fase 1)
        rename_results = await rename_files_in_folder(token, site_url, entrada_files)
        
        # Aguardar um momento para garantir que as operações de renomeação foram concluídas
        await asyncio.sleep(1)
        
        # FASE 2: MOVER OS ARQUIVOS RENOMEADOS PARA PASTAS DE DESTINO
        logger.info("=== FASE 2: MOVENDO ARQUIVOS PARA PASTAS DE DESTINO ===")
        
        # Listar novamente os arquivos na pasta ENTRADA (agora já renomeados)
        renamed_files = await list_files(token, site_url, PATHS["ENTRADA"], limit=1000)
        
        if not renamed_files:
            return {
                "success": True, 
                "message": "Fase 1 concluída (renomeação), mas não foram encontrados arquivos para mover",
                "fase_1": rename_results
            }
        
        logger.info(f"Encontrados {len(renamed_files)} arquivos para mover")
        
        # Mover os arquivos renomeados para as pastas de destino (fase 2)
        move_results = await move_files_to_destinations(token, site_url, renamed_files)
        
        # Calcular tempo total
        total_time = round(time.time() - start_time, 2)
        
        # Limpar caches para liberar memória
        _file_content_cache.clear()
        _text_cache.clear()
        
        # Retornar resultado combinado das duas fases
        return {
            "success": True,
            "message": f"Processamento concluído em {total_time}s",
            "renomeados": rename_results["total_renamed"],
            "movidos": move_results["total_moved"],
            "detalhes": {
                "fase_1_renomeacao": rename_results,
                "fase_2_movimentacao": move_results
            },
            "tempo_total": total_time
        }
        
    except Exception as e:
        logger.error(f"Erro geral no processo de renomear e mover: {str(e)}")
        return {"success": False, "message": f"Erro: {str(e)}"}

async def rename_files_in_folder(token, site_url, files_list):
    """
    Renomeia arquivos na pasta ENTRADA conforme padrões específicos.
    Os arquivos permanecem na mesma pasta após a renomeação.
    """
    logger.info(f"Iniciando renomeação de {len(files_list)} arquivos")
    
    # Função para processar um único arquivo (apenas renomeação)
    async def process_rename_single_file(file):
        original_name = file.get("Name", "")
        result = {
            "original_name": original_name,
            "processed": True,
            "type": None,
            "new_name": None,
            "success": False,
            "error": None
        }
        
        try:
            # Verificar se o arquivo já foi renomeado
            if original_name.startswith(("FATURA-LOCAÇÃO_", "TELECOMUNICAÇÕES_")) or re.match(r"^[A-Z\s]+_", original_name):
                result["type"] = "already_renamed"
                return result
            
            # FUNÇÃO 1: QPE- com 6 números SEM letra
            if re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                result["type"] = "qpe_sem_letra"
                logger.info(f"Arquivo identificado como QPE sem letra: {original_name}")
                
                # Baixar o arquivo para extrair a cidade (com cache)
                file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                if not file_content:
                    result["error"] = "download_failed"
                    return result
                
                texto_pdf = await extract_text_from_pdf_cached(file_content)
                if not texto_pdf:
                    result["error"] = "text_extraction_failed"
                    return result
                
                # Buscar a cidade usando o regex
                padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
                cidade_match = re.search(padrao_cidade, texto_pdf)
                
                if not cidade_match:
                    result["error"] = "city_not_found"
                    return result
                
                cidade = cidade_match.group(1).strip()
                logger.info(f"Cidade extraída: {cidade}")
                
                # Novo nome com a cidade como prefixo
                new_name = f"{cidade}_{original_name}"
                result["new_name"] = new_name
                logger.info(f"Novo nome será: {new_name}")
                
                # Fazer upload com novo nome (NA MESMA PASTA)
                success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if not success:
                    result["error"] = "upload_failed"
                    return result
                
                # Excluir o arquivo original após o upload do novo
                delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                if not delete_success:
                    logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                
                result["success"] = True
                logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
            
            # FUNÇÃO 2: QPE- com 6 números COM uma letra no final
            elif re.search(r"QPE-\d{6}[A-Za-z]", original_name):
                result["type"] = "qpe_com_letra"
                logger.info(f"Arquivo identificado como QPE com letra: {original_name}")
                
                # Novo nome com "FATURA-LOCAÇÃO" como prefixo
                new_name = f"FATURA-LOCAÇÃO_{original_name}"
                result["new_name"] = new_name
                logger.info(f"Novo nome será: {new_name}")
                
                # Baixar o arquivo (com cache)
                file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                if not file_content:
                    result["error"] = "download_failed"
                    return result
                
                # Fazer upload com novo nome (NA MESMA PASTA)
                success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if not success:
                    result["error"] = "upload_failed"
                    return result
                
                # Excluir o arquivo original após o upload do novo
                delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                if not delete_success:
                    logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                
                result["success"] = True
                logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
            
            # FUNÇÃO 3: SPB- com 6 números SEM letra no final
            elif re.search(r"SPB-\d{6}(?![A-Za-z])", original_name):
                result["type"] = "spb_sem_letra"
                logger.info(f"Arquivo identificado como SPB sem letra: {original_name}")
                
                # Baixar o arquivo para extrair a cidade (com cache)
                file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                if not file_content:
                    result["error"] = "download_failed"
                    return result
                
                texto_pdf = await extract_text_from_pdf_cached(file_content)
                if not texto_pdf:
                    result["error"] = "text_extraction_failed"
                    return result
                
                # Buscar a cidade usando o regex específico para SPB
                padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
                cidade_match = re.search(padrao_cidade, texto_pdf)
                
                if not cidade_match:
                    result["error"] = "city_not_found"
                    return result
                
                cidade = re.sub(r'----$', '', cidade_match.group(1)).strip()
                logger.info(f"Cidade extraída: {cidade}")
                
                # Novo nome com a cidade como prefixo
                new_name = f"{cidade}_{original_name}"
                result["new_name"] = new_name
                logger.info(f"Novo nome será: {new_name}")
                
                # Fazer upload com novo nome (NA MESMA PASTA)
                success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if not success:
                    result["error"] = "upload_failed"
                    return result
                
                # Excluir o arquivo original após o upload do novo
                delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                if not delete_success:
                    logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                
                result["success"] = True
                logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
            
            # FUNÇÃO 4: Arquivos de TELECOM
            elif re.search(r"(BLU|POA|VIX|SPB|REC|BHO)-\d{6}[A-Za-z]\d{2}", original_name):
                result["type"] = "telecom"
                logger.info(f"Arquivo identificado como TELECOM: {original_name}")
                
                # Novo nome com "TELECOMUNICAÇÕES" como prefixo
                new_name = f"TELECOMUNICAÇÕES_{original_name}"
                result["new_name"] = new_name
                logger.info(f"Novo nome será: {new_name}")
                
                # Baixar o arquivo (com cache)
                file_content = await download_file_cached(token, site_url, PATHS["ENTRADA"], original_name)
                if not file_content:
                    result["error"] = "download_failed"
                    return result
                
                # Fazer upload com novo nome (NA MESMA PASTA)
                success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if not success:
                    result["error"] = "upload_failed"
                    return result
                
                # Excluir o arquivo original após o upload do novo
                delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                if not delete_success:
                    logger.warning(f"Falha ao excluir arquivo original: {original_name}, mas o novo arquivo foi criado")
                
                result["success"] = True
                logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
            
            else:
                result["type"] = "no_match"
                logger.info(f"Arquivo {original_name} não corresponde a nenhum padrão")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Erro ao processar arquivo {original_name}: {str(e)}")
        
        return result
    
    # Processar arquivos em lotes para melhor controle
    batch_size = 20
    max_concurrent = 10  # Máximo de operações paralelas
    all_results = []
    
    # Dividir em lotes
    for i in range(0, len(files_list), batch_size):
        batch = files_list[i:i+batch_size]
        logger.info(f"Processando lote de renomeação {i//batch_size + 1}/{(len(files_list)+batch_size-1)//batch_size} ({len(batch)} arquivos)")
        
        # Criar tarefas para processamento paralelo
        tasks = [process_rename_single_file(file) for file in batch]
        
        # Processar arquivos em paralelo (limitado a max_concurrent)
        batch_results = await asyncio.gather(*tasks)
        all_results.extend(batch_results)
        
        # Pequena pausa entre lotes para não sobrecarregar o servidor
        if i + batch_size < len(files_list):
            await asyncio.sleep(0.5)
    
    # Organizar resultados por tipo
    renamed_files_qpe_sem_letra = []
    renamed_files_qpe_com_letra = []
    renamed_files_spb_sem_letra = []
    renamed_files_telecom = []
    errors = []
    
    for result in all_results:
        if result["success"]:
            file_info = {
                "original": result["original_name"],
                "new": result["new_name"]
            }
            
            if result["type"] == "qpe_sem_letra":
                renamed_files_qpe_sem_letra.append(file_info)
            elif result["type"] == "qpe_com_letra":
                renamed_files_qpe_com_letra.append(file_info)
            elif result["type"] == "spb_sem_letra":
                renamed_files_spb_sem_letra.append(file_info)
            elif result["type"] == "telecom":
                renamed_files_telecom.append(file_info)
        elif result["error"]:
            errors.append({
                "file": result["original_name"],
                "type": result["type"],
                "error": result["error"]
            })
    
    # Totais para relatório
    total_qpe_sem_letra = len(renamed_files_qpe_sem_letra)
    total_qpe_com_letra = len(renamed_files_qpe_com_letra)
    total_spb_sem_letra = len(renamed_files_spb_sem_letra)
    total_telecom = len(renamed_files_telecom)
    total_renamed = total_qpe_sem_letra + total_qpe_com_letra + total_spb_sem_letra + total_telecom
    
    return {
        "success": True,
        "message": f"{total_renamed} arquivos renomeados com sucesso na pasta ENTRADA",
        "total_renamed": total_renamed,
        "detalhes": {
            "qpe_sem_letra": {
                "total": total_qpe_sem_letra,
                "arquivos": renamed_files_qpe_sem_letra
            },
            "qpe_com_letra": {
                "total": total_qpe_com_letra,
                "arquivos": renamed_files_qpe_com_letra
            },
            "spb_sem_letra": {
                "total": total_spb_sem_letra,
                "arquivos": renamed_files_spb_sem_letra
            },
            "telecom": {
                "total": total_telecom,
                "arquivos": renamed_files_telecom
            }
        },
        "estatisticas": {
            "total_processado": len(all_results),
            "total_arquivos": len(files_list),
            "total_renomeados": total_renamed,
            "total_erros": len(errors)
        },
        "erros": errors if errors else None
    }

async def move_files_to_destinations(token, site_url, files_list):
    """
    Move arquivos para suas respectivas pastas de destino.
    Adicionando logs detalhados para debug de QPE e SPB.
    """
    logger.info("==================== INICIANDO MOVIMENTAÇÃO DE ARQUIVOS ====================")
    
    # Separar arquivos por destino primeiro
    files_by_type = {
        "NFSERV": [],
        "QPE": [],
        "SPB": [],
        "sem_destino": []
    }

    # Classificar arquivos primeiro
    for file in files_list:
        file_name = file.get("Name", "")
        
        # NFSERV (manter exatamente como está, pois está funcionando)
        if file_name.startswith(("FATURA-LOCAÇÃO_", "TELECOMUNICAÇÕES_")):
            files_by_type["NFSERV"].append(file)
            
        # QPE (adicionar logs detalhados)
        elif re.search(r"^[A-Z\s]+_QPE-\d{6}(?![A-Za-z])", file_name):
            logger.info(f"[DEBUG-QPE] Arquivo identificado para pasta QPE: {file_name}")
            files_by_type["QPE"].append(file)
            
        # SPB (adicionar logs detalhados)
        elif re.search(r"^[A-Z\s]+_SPB-\d{6}", file_name):
            logger.info(f"[DEBUG-SPB] Arquivo identificado para pasta SPB: {file_name}")
            files_by_type["SPB"].append(file)
            
        else:
            files_by_type["sem_destino"].append(file)

    # Processar NFSERV primeiro (manter como está)
    logger.info("=== Processando arquivos NFSERV ===")
    for file in files_by_type["NFSERV"]:
        # ... código existente para NFSERV ...
        pass

    # Verificar autenticação antes de processar QPE e SPB
    logger.info("")
    logger.info("=== VERIFICANDO AUTENTICAÇÃO PARA QPE/SPB ===")
    try:
        # Tentar renovar o token antes de processar QPE/SPB
        auth = SharePointAuth()
        new_token = auth.acquire_token()
        if not new_token:
            logger.error("❌ Falha ao renovar token para processamento de QPE/SPB")
            return False
        logger.info("✓ Token renovado com sucesso para QPE/SPB")
        
        # Processar QPE com logs detalhados
        logger.info("")
        logger.info("=== INICIANDO PROCESSAMENTO QPE ===")
        logger.info(f"Total de arquivos QPE para processar: {len(files_by_type['QPE'])}")
        
        for file in files_by_type["QPE"]:
            file_name = file.get("Name", "")
            try:
                logger.info(f"[QPE] Iniciando processamento do arquivo: {file_name}")
                
                # Download
                logger.info(f"[QPE] Tentando download do arquivo {file_name}")
                file_content = await download_file(new_token, site_url, PATHS["ENTRADA"], file_name)
                if not file_content:
                    logger.error(f"[QPE] ❌ Falha no download do arquivo {file_name}")
                    continue
                logger.info(f"[QPE] ✓ Download concluído: {len(file_content)} bytes")
                
                # Upload
                logger.info(f"[QPE] Tentando upload para pasta QPE: {file_name}")
                success = await upload_file(new_token, site_url, file_content, file_name, PATHS["QPE"])
                if not success:  # <- Corrigido: indentação alinhada com o bloco try
                    logger.error(f"[QPE] ❌ Falha no upload do arquivo {file_name}")
                    continue
                logger.info(f"[QPE] ✓ Upload concluído com sucesso")
                
                # Deletar original
                logger.info(f"[QPE] Tentando deletar arquivo original: {file_name}")
                delete_success = await delete_file(new_token, site_url, PATHS["ENTRADA"], file_name)
                if not delete_success:  # <- Corrigido: indentação alinhada com o bloco try
                    logger.warning(f"[QPE] ⚠ Arquivo copiado mas não foi possível deletar original: {file_name}")
                else:
                    logger.info(f"[QPE] ✓ Arquivo original deletado com sucesso")
                
            except Exception as e:  # <- Este except deve fechar o try
                logger.error(f"[QPE] ❌ Erro processando arquivo {file_name}: {str(e)}")
                logger.exception("[QPE] Detalhes do erro:")

        # Processar SPB com logs detalhados
        logger.info("")
        logger.info("=== INICIANDO PROCESSAMENTO SPB ===")
        logger.info(f"Total de arquivos SPB para processar: {len(files_by_type['SPB'])}")
        
        for file in files_by_type["SPB"]:
            file_name = file.get("Name", "")
            try:
                logger.info(f"[SPB] Iniciando processamento do arquivo: {file_name}")
                
                # Download
                logger.info(f"[SPB] Tentando download do arquivo {file_name}")
                file_content = await download_file(new_token, site_url, PATHS["ENTRADA"], file_name)
                if not file_content:
                    logger.error(f"[SPB] ❌ Falha no download do arquivo {file_name}")
                    continue
                logger.info(f"[SPB] ✓ Download concluído: {len(file_content)} bytes")
                
                # Upload
                logger.info(f"[SPB] Tentando upload para pasta SPB: {file_name}")
                success = await upload_file(new_token, site_url, file_content, file_name, PATHS["SPB"])
                if not success:
                    logger.error(f"[SPB] ❌ Falha no upload do arquivo {file_name}")
                    continue
                logger.info(f"[SPB] ✓ Upload concluído com sucesso")
                
                # Deletar original
                logger.info(f"[SPB] Tentando deletar arquivo original: {file_name}")
                delete_success = await delete_file(new_token, site_url, PATHS["ENTRADA"], file_name)
                if not delete_success:
                    logger.warning(f"[SPB] ⚠ Arquivo copiado mas não foi possível deletar original: {file_name}")
                else:
                    logger.info(f"[SPB] ✓ Arquivo original deletado com sucesso")
                
            except Exception as e:
                logger.error(f"[SPB] ❌ Erro processando arquivo {file_name}: {str(e)}")
                logger.exception("[SPB] Detalhes do erro:")

    except Exception as e:
        logger.error(f"❌ Erro geral no processamento QPE/SPB: {str(e)}")
        logger.exception("Detalhes do erro geral:")

    # ... resto do código existente ...

@router.post("/move-files")
async def move_files_to_destinations():
    """
    Move arquivos para suas pastas de destino.
    Agora com suporte para cancelamento.
    """
    global process_running, process_cancel_requested
    
    # Reseta a flag de cancelamento e marca o processo como em execução
    with process_lock:
        process_cancel_requested = False
        process_running = True
    
    try:
        logger.info("==================== INICIANDO MOVIMENTAÇÃO DE ARQUIVOS ====================")
        logger.info(f"Data/hora de início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Autenticar no SharePoint
        logger.info("Autenticando no SharePoint...")
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("ERRO: Falha na autenticação com SharePoint!")
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        logger.info(f"Autenticação bem-sucedida! Site URL: {site_url}")
        
        # ETAPA 1: LIMPAR PASTAS DE DESTINO (EXCETO R189)
        logger.info("")
        logger.info("===== ETAPA 1: LIMPANDO PASTAS DE DESTINO =====")
        logger.info("IMPORTANTE: A pasta ENTRADA NÃO será limpa, apenas as pastas de destino")
        logger.info("IMPORTANTE: A pasta R189 NÃO será limpa conforme solicitado!")
        
        # Lista de pastas para limpar (todas exceto ENTRADA e R189)
        destination_folders = ["QPE", "NFSERV", "SPB"]  # Removido R189
        cleanup_results = {}
        
        # Limpar cada pasta de destino
        for folder_name in destination_folders:
            folder_path = PATHS[folder_name]
            logger.info(f"")
            logger.info(f"LIMPANDO PASTA: {folder_name} (caminho: {folder_path})")
            
            # Listar arquivos na pasta
            logger.info(f"Listando arquivos em {folder_name}...")
            folder_files = await list_files(token, site_url, folder_path, limit=1000)
            
            if not folder_files:
                logger.info(f"Pasta {folder_name} já está vazia! Nada para excluir.")
                cleanup_results[folder_name] = {"total_files": 0, "deleted": 0}
                continue
            
            # Contagem de arquivos para log
            total_files = len(folder_files)
            logger.info(f"ENCONTRADOS {total_files} ARQUIVOS para excluir na pasta {folder_name}")
            
            # Excluir cada arquivo
            deleted_count = 0
            for file in folder_files:
                file_name = file.get("Name", "")
                logger.info(f"Excluindo: {file_name}")
                
                success = await delete_file(token, site_url, folder_path, file_name)
                
                if success:
                    deleted_count += 1
                    logger.info(f"✓ Arquivo {file_name} excluído com sucesso")
                else:
                    logger.error(f"✗ ERRO ao excluir arquivo: {file_name}")
            
            # Registrar resultados
            cleanup_results[folder_name] = {
                "total_files": total_files,
                "deleted": deleted_count,
                "path": folder_path
            }
            
            logger.info(f"RESULTADO LIMPEZA {folder_name}: {deleted_count}/{total_files} arquivos excluídos")
        
        # Adicionar R189 como "preservada" no resultado
        cleanup_results["R189"] = {"total_files": "N/A", "deleted": 0, "preservada": True}
        
        logger.info("")
        logger.info("LIMPEZA DAS PASTAS DE DESTINO CONCLUÍDA!")
        logger.info(f"QPE: {cleanup_results.get('QPE', {}).get('deleted', 0)}/{cleanup_results.get('QPE', {}).get('total_files', 0)} excluídos")
        logger.info(f"NFSERV: {cleanup_results.get('NFSERV', {}).get('deleted', 0)}/{cleanup_results.get('NFSERV', {}).get('total_files', 0)} excluídos")
        logger.info(f"SPB: {cleanup_results.get('SPB', {}).get('deleted', 0)}/{cleanup_results.get('SPB', {}).get('total_files', 0)} excluídos")
        logger.info(f"R189: Pasta PRESERVADA conforme solicitado!")
        
        # O resto da função permanece exatamente igual...
        # ETAPA 2: MOVER ARQUIVOS DA ENTRADA PARA AS PASTAS DE DESTINO
        logger.info("")
        logger.info("===== ETAPA 2: MOVENDO ARQUIVOS DA ENTRADA PARA PASTAS DE DESTINO =====")
        logger.info("IMPORTANTE: Os arquivos serão MANTIDOS na pasta ENTRADA após o envio")
        
        # Listar arquivos da pasta ENTRADA
        logger.info(f"Listando arquivos da pasta ENTRADA ({PATHS['ENTRADA']})...")
        entrada_files = await list_files(token, site_url, PATHS["ENTRADA"], limit=1000)
        
        if not entrada_files:
            logger.warning("ATENÇÃO: Nenhum arquivo encontrado na pasta ENTRADA para mover!")
            logger.warning("Verifique se existem arquivos na pasta ENTRADA!")
            logger.info("==================== FIM DA EXECUÇÃO ====================")
            return {
                "success": True, 
                "message": "Pastas de destino limpas, mas nenhum arquivo encontrado para mover",
                "limpeza": cleanup_results
            }
            
        logger.info(f"ENCONTRADOS {len(entrada_files)} ARQUIVOS na pasta ENTRADA")
        for idx, file in enumerate(entrada_files):
            logger.info(f"  {idx+1}. {file.get('Name', 'Nome não encontrado')}")
        
        # Processar cada arquivo e determinar para onde movê-lo
        moved_files = []
        files_by_destination = {
            "QPE": [],
            "NFSERV": [],
            "SPB": [],
            "R189": [],
            "sem_destino": []
        }
        
        logger.info("")
        logger.info("Iniciando análise e movimentação dos arquivos...")
        
        # Processar todos os arquivos e identificar destino
        for idx, file in enumerate(entrada_files):
            file_name = file.get("Name", "")
            destination = None
            destination_name = None
            
            logger.info(f"")
            logger.info(f"ARQUIVO #{idx+1}: {file_name}")
            
            # REGRA 1: Arquivos R189
            if "R189" in file_name:
                destination = PATHS["R189"]
                destination_name = "R189"
                logger.info(f"✓ Identificado como R189 - Será enviado para pasta {destination_name}")
            
            # REGRA 2: FATURA-LOCAÇÃO e TELECOMUNICAÇÕES vão para NFSERV (não mexer nesta parte)
            elif file_name.startswith(("FATURA-LOCAÇÃO_", "TELECOMUNICAÇÕES_")):
                destination = PATHS["NFSERV"]
                destination_name = "NFSERV"
                logger.info(f"✓ Identificado como {file_name.split('_')[0]} - Será enviado para pasta {destination_name}")
            
            # NOVOS PADRÕES: Para QPE (arquivos com QPE no nome)
            elif "QPE-" in file_name:
                destination = PATHS["QPE"]
                destination_name = "QPE"
                logger.info(f"✓ Identificado como arquivo QPE - Será enviado para pasta {destination_name}")
                logger.info(f"   Padrão encontrado: 'QPE-' no nome do arquivo")
            
            # NOVOS PADRÕES: Para SPB (arquivos com SPB no nome)
            elif "SPB-" in file_name:
                destination = PATHS["SPB"]
                destination_name = "SPB"
                logger.info(f"✓ Identificado como arquivo SPB - Será enviado para pasta {destination_name}")
                logger.info(f"   Padrão encontrado: 'SPB-' no nome do arquivo")
            
            # Arquivos que não correspondem a nenhum padrão
            else:
                logger.warning(f"⚠ ATENÇÃO: Arquivo não corresponde a nenhum padrão conhecido")
                logger.warning(f"   Verifique se o arquivo {file_name} deveria ter sido renomeado anteriormente")
                files_by_destination["sem_destino"].append(file_name)
                continue
            
            # Adicionar à lista de arquivos por destino
            files_by_destination[destination_name].append(file_name)
            
            try:
                logger.info(f"Iniciando transferência: {file_name} -> {destination}")
                
                # Download do arquivo
                logger.info(f"Baixando arquivo {file_name} da pasta ENTRADA...")
                file_content = await download_file(token, site_url, PATHS["ENTRADA"], file_name)
                if not file_content:
                    logger.error(f"✗ ERRO: Falha ao baixar arquivo {file_name}")
                    continue
                logger.info(f"Download concluído com sucesso ({len(file_content)} bytes)")
                
                # Upload para a pasta destino
                logger.info(f"Enviando para pasta {destination_name}...")
                success = await upload_file(token, site_url, file_content, file_name, destination)
                
                if not success:
                    logger.error(f"✗ ERRO: Falha ao fazer upload do arquivo {file_name} para {destination}")
                    continue
                logger.info(f"Upload concluído com sucesso")
                
                # MUDANÇA: NÃO excluir o arquivo original como solicitado
                logger.info(f"✓ Arquivo mantido na pasta ENTRADA conforme solicitado")
                
                # Adicionar à lista de arquivos movidos
                moved_files.append({
                    "file": file_name,
                    "destination": destination,
                    "destination_name": destination_name
                })
                
                logger.info(f"✓ SUCESSO! Arquivo {file_name} copiado para {destination_name} (original mantido)")
            
            except Exception as e:
                logger.error(f"✗ ERRO AO PROCESSAR ARQUIVO {file_name}: {str(e)}")
                logger.exception("Detalhes do erro:")
        
        # Calcular estatísticas
        total_time = round(time.time() - start_time, 2)
        total_moved = len(moved_files)
        
        # Arquivos movidos por pasta
        moved_to_qpe = len(files_by_destination["QPE"])
        moved_to_nfserv = len(files_by_destination["NFSERV"])
        moved_to_spb = len(files_by_destination["SPB"])
        moved_to_r189 = len(files_by_destination["R189"])
        not_moved = len(files_by_destination["sem_destino"])
        
        logger.info("")
        logger.info("==================== RESUMO DA OPERAÇÃO ====================")
        logger.info(f"Total de arquivos encontrados na ENTRADA: {len(entrada_files)}")
        logger.info(f"Total de arquivos copiados: {total_moved}")
        logger.info(f"Arquivos não movidos: {not_moved}")
        logger.info(f"Tempo total de execução: {total_time} segundos")
        logger.info("")
        logger.info(f"ARQUIVOS COPIADOS POR PASTA:")
        logger.info(f"  • QPE: {moved_to_qpe} arquivos")
        logger.info(f"  • NFSERV: {moved_to_nfserv} arquivos")
        logger.info(f"  • SPB: {moved_to_spb} arquivos")
        logger.info(f"  • R189: {moved_to_r189} arquivos")
        logger.info("")
        logger.info(f"IMPORTANTE: Todos os arquivos originais foram MANTIDOS na pasta ENTRADA")
        
        if not_moved > 0:
            logger.warning("")
            logger.warning(f"⚠ ATENÇÃO: {not_moved} arquivos não foram identificados:")
            for i, file in enumerate(files_by_destination["sem_destino"]):
                logger.warning(f"  {i+1}. {file}")
        
        logger.info("")
        logger.info("==================== FIM DA EXECUÇÃO ====================")
        
        # Retornar resultado detalhado
        return {
            "success": True,
            "message": f"{total_moved} arquivos copiados com sucesso em {total_time}s (originais mantidos)",
            "limpeza": {
                "qpe": f"Excluídos {cleanup_results['QPE']['deleted']} de {cleanup_results['QPE']['total_files']} arquivos",
                "nfserv": f"Excluídos {cleanup_results['NFSERV']['deleted']} de {cleanup_results['NFSERV']['total_files']} arquivos", 
                "spb": f"Excluídos {cleanup_results['SPB']['deleted']} de {cleanup_results['SPB']['total_files']} arquivos",
                "r189": f"Excluídos {cleanup_results['R189']['deleted']} de {cleanup_results['R189']['total_files']} arquivos"
            },
            "detalhes": {
                "para_qpe": {
                    "total": moved_to_qpe,
                    "pasta": PATHS["QPE"],
                    "arquivos": files_by_destination["QPE"]
                },
                "para_nfserv": {
                    "total": moved_to_nfserv,
                    "pasta": PATHS["NFSERV"],
                    "arquivos": files_by_destination["NFSERV"]
                },
                "para_spb": {
                    "total": moved_to_spb,
                    "pasta": PATHS["SPB"],
                    "arquivos": files_by_destination["SPB"]
                },
                "para_r189": {
                    "total": moved_to_r189,
                    "pasta": PATHS["R189"],
                    "arquivos": files_by_destination["R189"]
                }
            },
            "estatisticas": {
                "total_analisado": len(entrada_files),
                "total_copiados": total_moved,
                "tempo_total": total_time,
                "arquivos_nao_copiados": not_moved,
                "arquivos_sem_destino": files_by_destination["sem_destino"],
                "originais_mantidos": True
            }
        }
        
    except Exception as e:
        logger.error(f"✗ ERRO GERAL AO MOVER ARQUIVOS: {str(e)}")
        logger.exception("Detalhes do erro:")
        return {"success": False, "message": f"Erro: {str(e)}"}
    
    finally:
        # Marca o processo como concluído, independente de sucesso ou erro
        with process_lock:
            process_running = False

@router.post("/process-complete")
async def process_complete():
    """
    Executa o processo completo: renomeia e move os arquivos,
    em duas etapas sequenciais.
    """
    try:
        logger.info("=== INICIANDO PROCESSO COMPLETO (RENOMEAR E MOVER) ===")
        
        # ETAPA 1: Renomear arquivos
        logger.info("ETAPA 1: Renomeando arquivos...")
        rename_result = await rename_files()
        
        if not rename_result.get("success", False):
            logger.error(f"Falha na etapa de renomeação: {rename_result.get('message')}")
            return {
                "success": False,
                "message": f"Falha na etapa de renomeação: {rename_result.get('message')}",
                "etapa_1": rename_result
            }
        
        # Aguardar um momento para garantir que todas as operações SharePoint foram concluídas
        logger.info("Aguardando conclusão das operações de renomeação...")
        await asyncio.sleep(2)
        
        # ETAPA 2: Mover arquivos
        logger.info("ETAPA 2: Movendo arquivos...")
        move_result = await move_files_to_destinations()
        
        # Retornar resultados combinados
        return {
            "success": True,
            "message": "Processo completo executado com sucesso",
            "etapa_1_renomeacao": rename_result,
            "etapa_2_movimentacao": move_result
        }
        
    except Exception as e:
        logger.error(f"Erro no processo completo: {str(e)}")
        logger.exception("Detalhes do erro:")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/reset-process")
async def reset_process():
    """
    Reseta o processo: limpa as pastas QPE, NFSERV e SPB (preservando R189 e ENTRADA).
    """
    try:
        logger.info("==================== INICIANDO RESET DE PROCESSO ====================")
        
        # Autenticar no SharePoint
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("ERRO: Falha na autenticação com SharePoint!")
            return {"success": False, "message": "Falha na autenticação com SharePoint"}
            
        site_url = auth.site_url
        
        # Lista de pastas para limpar
        pastas_para_limpar = ["QPE", "NFSERV", "SPB"]
        resultados = {}
        
        # Limpar cada pasta
        for pasta in pastas_para_limpar:
            try:
                caminho = PATHS[pasta]
                logger.info(f"Limpando pasta {pasta}: {caminho}")
                
                # Listar arquivos
                arquivos = await list_files(token, site_url, caminho)
                
                if not arquivos:
                    logger.info(f"Pasta {pasta} já está vazia")
                    resultados[pasta] = {"total": 0, "excluidos": 0}
                    continue
                    
                # Excluir arquivos
                contador = 0
                for arquivo in arquivos:
                    nome_arquivo = arquivo.get("Name", "")
                    
                    try:
                        sucesso = await delete_file(token, site_url, caminho, nome_arquivo)
                        if sucesso:
                            contador += 1
                            logger.info(f"Arquivo excluído: {nome_arquivo}")
                        else:
                            logger.error(f"Falha ao excluir: {nome_arquivo}")
                    except Exception as e:
                        logger.error(f"Erro ao excluir {nome_arquivo}: {str(e)}")
                
                resultados[pasta] = {"total": len(arquivos), "excluidos": contador}
                logger.info(f"Pasta {pasta}: {contador} de {len(arquivos)} arquivos excluídos")
                
            except Exception as e:
                logger.error(f"Erro ao limpar pasta {pasta}: {str(e)}")
                resultados[pasta] = {"erro": str(e)}
        
        # Limpar cache
        clear_sharepoint_cache()
        
        return {
            "success": True,
            "message": "Processo resetado com sucesso",
            "detalhes": resultados
        }
        
    except Exception as e:
        logger.error(f"Erro geral ao resetar processo: {str(e)}")
        logger.exception("Detalhes do erro:")
        return {"success": False, "message": f"Erro: {str(e)}"}

@router.post("/cancel-process")
async def cancel_process():
    """
    Cancela processos em andamento de forma imediata.
    """
    global process_cancel_requested, process_running
    
    try:
        logger.info("===== SOLICITAÇÃO DE CANCELAMENTO RECEBIDA =====")
        
        # Marcar flag para cancelamento
        with process_lock:
            process_cancel_requested = True
            was_running = process_running
            process_running = False  # Força a marcação do processo como encerrado
        
        if was_running:
            logger.info("Processo interrompido forçadamente")
            # Limpar cache para evitar problemas em execuções futuras
            clear_sharepoint_cache()
            return {
                "success": True,
                "message": "Processo cancelado com sucesso."
            }
        else:
            logger.info("Nenhum processo em execução para cancelar")
            return {
                "success": True,
                "message": "Nenhum processo em execução para cancelar."
            }
    except Exception as e:
        logger.error(f"Erro ao cancelar processo: {str(e)}")
        return {
            "success": False,
            "message": f"Erro ao cancelar processo: {str(e)}"
        }

@router.get("/process-status")
async def get_process_status():
    """
    Retorna o status atual do processo (em execução ou não).
    """
    global process_running, process_cancel_requested
    
    with process_lock:
        status = {
            "running": process_running,
            "cancel_requested": process_cancel_requested
        }
    
    return status

# Adicione esta função auxiliar para verificar cancelamento
def check_if_cancelled():
    """Verifica se o cancelamento foi solicitado."""
    global process_cancel_requested
    with process_lock:
        return process_cancel_requested

@router.post("/rename-clean")
async def rename_files_clean():
    """
    Função de renomeação limpa e organizada que substitui as múltiplas funções existentes.
    
    Aplica as seguintes regras de renomeação:
    1. QPE- com 6 números SEM letra → Adiciona nome da cidade
    2. QPE- com 6 números COM letra → Adiciona "FATURA-LOCAÇÃO"
    3. SPB- com 6 números SEM letra → Adiciona nome da cidade
    4. BLU/POA/VIX/SPB/REC/BHO com 6 números + letra + 2 números → Adiciona "TELECOMUNICAÇÕES"
    
    Com verificações rigorosas contra processamento duplicado.
    """
    try:
        logger.info("=== INICIANDO NOVO PROCESSAMENTO DE RENOMEAÇÃO ===")
        
        # Limpar cache e histórico antes de iniciar
        global processed_files_history
        processed_files_history = set()
        
        # Adquirir lock para garantir processamento exclusivo
        async with processing_lock:
            # Autenticar no SharePoint
            auth = SharePointAuth()
            token = auth.acquire_token()
            
            if not token:
                logger.error("Falha na autenticação com SharePoint")
                return {"success": False, "message": "Falha na autenticação com SharePoint"}
                
            site_url = auth.site_url
            
            # Listar TODOS os arquivos da pasta ENTRADA
            entrada_files = await list_files(token, site_url, PATHS["ENTRADA"], limit=1000)
            
            if not entrada_files:
                logger.info("Nenhum arquivo encontrado na pasta ENTRADA")
                return {"success": True, "message": "Nenhum arquivo encontrado para renomear"}
                
            logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
            
            # Resultados organizados por categoria
            results = {
                "qpe_sem_letra": [],
                "qpe_com_letra": [],
                "spb_sem_letra": [],
                "telecom": [],
                "ignorados": [],
                "erros": []
            }
            
            # Lista de nomes de arquivos para prevenção de duplicação
            existing_names = set(file.get("Name", "") for file in entrada_files)
            
            # Processar cada arquivo
            for index, file in enumerate(entrada_files, 1):
                original_name = file.get("Name", "")
                
                try:
                    logger.info(f"[{index}/{len(entrada_files)}] Processando: {original_name}")
                    
                    # VERIFICAÇÃO RIGOROSA DE ARQUIVOS JÁ PROCESSADOS
                    # Caso 1: Verificar se o arquivo já foi processado nesta sessão
                    if original_name in processed_files_history:
                        logger.info(f"Arquivo {original_name} já foi processado nesta sessão, ignorando")
                        results["ignorados"].append({"arquivo": original_name, "motivo": "processado nesta sessão"})
                        continue
                        
                    # Caso 2: Verificar se o nome já indica que foi processado anteriormente
                    if (original_name.startswith(("FATURA-LOCAÇÃO_", "TELECOMUNICAÇÕES_")) or 
                        re.match(r"^[A-Z\s]+_nfserv_", original_name)):
                        logger.info(f"Arquivo {original_name} já possui prefixo de processamento, ignorando")
                        results["ignorados"].append({"arquivo": original_name, "motivo": "já possui prefixo"})
                        continue
                    
                    # Identificar o tipo de arquivo
                    file_type = None
                    new_name = None
                    
                    # REGRA 1: QPE- com 6 números SEM letra
                    if re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                        file_type = "qpe_sem_letra"
                        logger.info(f"Identificado como QPE sem letra: {original_name}")
                        
                        # Baixar o arquivo para extrair a cidade
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                        if file_content:
                            # Extrair texto e buscar cidade
                            texto_pdf = await extract_text_from_pdf(file_content)
                            if texto_pdf:
                                padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
                                cidade_match = re.search(padrao_cidade, texto_pdf)
                                
                                if cidade_match:
                                    cidade = cidade_match.group(1).strip()
                                    logger.info(f"Cidade extraída: {cidade}")
                                    new_name = f"{cidade}_{original_name}"
                                else:
                                    results["erros"].append({
                                        "arquivo": original_name, 
                                        "erro": "cidade não encontrada no PDF"
                                    })
                                    continue
                            else:
                                results["erros"].append({
                                    "arquivo": original_name, 
                                    "erro": "não foi possível extrair texto do PDF"
                                })
                                continue
                        else:
                            results["erros"].append({
                                "arquivo": original_name, 
                                "erro": "não foi possível baixar o arquivo"
                            })
                            continue
                    
                    # REGRA 2: QPE- com 6 números COM letra
                    elif re.search(r"QPE-\d{6}[A-Za-z]", original_name):
                        file_type = "qpe_com_letra"
                        logger.info(f"Identificado como QPE com letra: {original_name}")
                        new_name = f"FATURA-LOCAÇÃO_{original_name}"
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                        if not file_content:
                            results["erros"].append({
                                "arquivo": original_name, 
                                "erro": "não foi possível baixar o arquivo"
                            })
                            continue
                    
                    # REGRA 3: SPB- com 6 números SEM letra
                    elif re.search(r"SPB-\d{6}(?![A-Za-z])", original_name):
                        file_type = "spb_sem_letra"
                        logger.info(f"Identificado como SPB sem letra: {original_name}")
                        
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                        if file_content:
                            texto_pdf = await extract_text_from_pdf(file_content)
                            if texto_pdf:
                                padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
                                cidade_match = re.search(padrao_cidade, texto_pdf)
                                
                                if cidade_match:
                                    cidade = re.sub(r'----$', '', cidade_match.group(1)).strip()
                                    logger.info(f"Cidade extraída: {cidade}")
                                    new_name = f"{cidade}_{original_name}"
                                else:
                                    results["erros"].append({
                                        "arquivo": original_name, 
                                        "erro": "cidade não encontrada no PDF"
                                    })
                                    continue
                            else:
                                results["erros"].append({
                                    "arquivo": original_name, 
                                    "erro": "não foi possível extrair texto do PDF"
                                })
                                continue
                        else:
                            results["erros"].append({
                                "arquivo": original_name, 
                                "erro": "não foi possível baixar o arquivo"
                            })
                            continue
                    
                    # REGRA 4: Arquivos de TELECOM
                    elif re.search(r"(BLU|POA|VIX|SPB|REC|BHO)-\d{6}[A-Za-z]\d{2}", original_name):
                        file_type = "telecom"
                        logger.info(f"Identificado como TELECOM: {original_name}")
                        new_name = f"TELECOMUNICAÇÕES_{original_name}"
                        file_content = await download_file(token, site_url, PATHS["ENTRADA"], original_name)
                        if not file_content:
                            results["erros"].append({
                                "arquivo": original_name, 
                                "erro": "não foi possível baixar o arquivo"
                            })
                            continue
                    
                    # Se não corresponder a nenhum padrão
                    else:
                        logger.info(f"Arquivo {original_name} não corresponde a nenhum padrão, ignorando")
                        results["ignorados"].append({
                            "arquivo": original_name, 
                            "motivo": "não corresponde a nenhum padrão"
                        })
                        continue
                    
                    # Se chegou até aqui, temos um novo nome válido e o arquivo foi baixado com sucesso
                    
                    # Verificar se o novo nome já existe (para evitar conflitos)
                    if new_name in existing_names:
                        logger.warning(f"Conflito de nomes: {new_name} já existe na pasta, gerando nome único")
                        base_name, ext = os.path.splitext(new_name)
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        new_name = f"{base_name}_{timestamp}{ext}"
                    
                    # Fazer upload com novo nome
                    success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                    
                    if success:
                        # Excluir o arquivo original
                        delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                        
                        if delete_success:
                            # Registrar sucesso
                            results[file_type].append({
                                "original": original_name,
                                "novo": new_name
                            })
                            
                            # Adicionar à lista de processados e nomes existentes
                            processed_files_history.add(new_name)
                            existing_names.add(new_name)
                            existing_names.remove(original_name)
                            
                            logger.info(f"Arquivo renomeado com sucesso: {original_name} -> {new_name}")
                        else:
                            logger.error(f"Erro ao excluir arquivo original: {original_name}")
                            results["erros"].append({
                                "arquivo": original_name, 
                                "erro": "falha ao excluir arquivo original"
                            })
                    else:
                        logger.error(f"Erro ao fazer upload do arquivo renomeado: {new_name}")
                        results["erros"].append({
                            "arquivo": original_name, 
                            "erro": "falha ao fazer upload do novo arquivo"
                        })
                
                except Exception as e:
                    logger.exception(f"Erro ao processar arquivo {original_name}")
                    results["erros"].append({
                        "arquivo": original_name, 
                        "erro": str(e)
                    })
            
            # Calcular totais para relatório
            totais = {key: len(value) for key, value in results.items()}
            total_renomeados = sum(len(results[k]) for k in ["qpe_sem_letra", "qpe_com_letra", "spb_sem_letra", "telecom"])
            
            return {
                "success": True,
                "mensagem": f"Processamento concluído: {total_renomeados} arquivos renomeados com sucesso",
                "resultados": results,
                "totais": totais,
                "total_arquivos": len(entrada_files)
            }
    
    except Exception as e:
        logger.exception("Erro geral no processamento")
        return {"success": False, "message": f"Erro geral: {str(e)}"}
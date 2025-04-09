import os
import re
import io
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.core.auth import SharePointAuth
import PyPDF2

router = APIRouter()
logger = logging.getLogger(__name__)

# Caminhos no SharePoint
PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB"
}

# Variável global para rastrear arquivos processados
processed_files_history = set()
processing_lock = asyncio.Lock()

# Funções auxiliares essenciais

async def make_request(method, url, headers=None, data=None, json_data=None, files=None):
    """Função para fazer requisições HTTP."""
    try:
        import httpx  # Importação local para evitar problemas se httpx não estiver disponível
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
        class ErrorResponse:
            def __init__(self):
                self.status_code = 500
                self.text = str(e)
            def json(self):
                return {"error": str(e)}
        
        return ErrorResponse()

async def list_files(token, site_url, folder_path, limit=1000):
    """Lista arquivos em uma pasta do SharePoint."""
    try:
        logger.info(f"Listando arquivos da pasta: {folder_path}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/json;odata=verbose'
        }
        
        api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
        api_url += f"?$top={limit}"
        
        logger.info(f"Fazendo requisição para: {api_url}")
        response = await make_request("GET", api_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            files = data.get('d', {}).get('results', [])
            logger.info(f"Encontrados {len(files)} arquivos na pasta {folder_path}")
            return files
        else:
            logger.error(f"Erro ao listar arquivos: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Exceção ao listar arquivos: {str(e)}")
        return []

async def download_file(token, site_url, folder_path, file_name):
    """Baixa um arquivo do SharePoint."""
    try:
        logger.info(f"Baixando arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose'
        }
        
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
    """Faz upload de um arquivo para o SharePoint."""
    try:
        logger.info(f"Fazendo upload do arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose'
        }
        
        upload_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(url='{file_name}',overwrite=true)"
        
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

async def delete_file(token, site_url, folder_path, file_name):
    """Exclui um arquivo do SharePoint."""
    try:
        logger.info(f"Excluindo arquivo: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'X-HTTP-Method': 'DELETE',
            'IF-MATCH': '*'
        }
        
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

async def extract_text_from_pdf(pdf_content):
    """Extrai texto de um arquivo PDF."""
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

async def check_folder_exists(token, site_url, folder_path):
    """Verifica se uma pasta existe no SharePoint."""
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/json;odata=verbose'
        }
        
        api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')"
        
        response = await make_request("GET", api_url, headers=headers)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao verificar existência da pasta {folder_path}: {str(e)}")
        return False

async def create_folder(token, site_url, folder_path):
    """Cria uma pasta no SharePoint."""
    try:
        # Extrair o caminho pai e o nome da nova pasta
        path_parts = folder_path.split('/')
        parent_path = '/'.join(path_parts[:-1])
        new_folder_name = path_parts[-1]
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/json;odata=verbose'
        }
        
        api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{parent_path}')/Folders/add('{new_folder_name}')"
        
        response = await make_request("POST", api_url, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Erro ao criar pasta {folder_path}: {str(e)}")
        return False

# Endpoint de teste simples
@router.get("/test")
async def test_endpoint():
    """Endpoint de teste para verificar se a API está funcionando."""
    return {"status": "ok", "message": "API de processamento de arquivos está funcionando"}

# Endpoint principal para renomear e mover arquivos
@router.post("/rename-clean")
async def rename_files_clean():
    """
    Função limpa que renomeia E move os arquivos de acordo com as regras de negócio.
    
    Regras de renomeação:
    1. QPE- com 6 números SEM letra → Adiciona nome da cidade
    2. QPE- com 6 números COM letra → Adiciona "FATURA-LOCAÇÃO"
    3. SPB- com 6 números SEM letra → Adiciona nome da cidade
    4. BLU/POA/VIX/SPB/REC/BHO com 6 números + letra + 2 números → Adiciona "TELECOMUNICAÇÕES"
    
    Regras de movimentação:
    - Arquivos com padrão QPE-XXXXXX (sem letra) vão para a pasta /QPE
    - Arquivos com padrão QPE-XXXXXXY (com letra) vão para a pasta /NFSERV
    - Arquivos com padrão (BLU|POA|VIX|SPB|REC|BHO) + XXXXXXYZ vão para a pasta /NFSERV
    - Arquivos com padrão SPB-XXXXXX (sem letra) vão para a pasta /SPB
    """
    try:
        logger.info("=== INICIANDO PROCESSAMENTO COMPLETO: RENOMEAR E MOVER ===")
        
        # Limpar cache e histórico antes de iniciar
        global processed_files_history
        processed_files_history.clear()
        
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
            return {"success": True, "message": "Nenhum arquivo encontrado para processar"}
            
        logger.info(f"Encontrados {len(entrada_files)} arquivos para analisar")
        
        # Resultados organizados por categoria
        results = {
            "qpe_sem_letra": [],
            "qpe_com_letra": [],
            "spb_sem_letra": [],
            "telecom": [],
            "ignorados": [],
            "erros": [],
            "movidos": []
        }
        
        # Lista de nomes de arquivos para prevenção de duplicação
        existing_names = set(file.get("Name", "") for file in entrada_files)
        renamed_files = []  # Para armazenar informações sobre arquivos renomeados
        
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
                destination_folder = None
                
                # REGRA 1: QPE- com 6 números SEM letra
                if re.search(r"QPE-\d{6}(?![A-Za-z])", original_name):
                    file_type = "qpe_sem_letra"
                    logger.info(f"Identificado como QPE sem letra: {original_name}")
                    destination_folder = PATHS.get("QPE", "/teams/BR-TI-TIN/AutomaoFinanas/QPE")
                    
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
                                logger.info(f"Novo nome será: {new_name}")
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
                    destination_folder = PATHS.get("NFSERV", "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV")
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
                    destination_folder = PATHS.get("SPB", "/teams/BR-TI-TIN/AutomaoFinanas/SPB")
                    
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
                                logger.info(f"Novo nome será: {new_name}")
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
                    destination_folder = PATHS.get("NFSERV", "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV")
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
                
                # FASE 1: RENOMEAR O ARQUIVO NA PASTA ENTRADA
                logger.info(f"Renomeando arquivo: {original_name} -> {new_name}")
                upload_success = await upload_file(token, site_url, file_content, new_name, PATHS["ENTRADA"])
                
                if upload_success:
                    # Excluir o arquivo original
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], original_name)
                    
                    if delete_success:
                        # Registrar sucesso na renomeação
                        results[file_type].append({
                            "original": original_name,
                            "novo": new_name
                        })
                        
                        # Armazenar informações para mover depois
                        renamed_files.append({
                            "name": new_name,
                            "type": file_type,
                            "destination": destination_folder,
                            "content": file_content
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
        
        # FASE 2: MOVER OS ARQUIVOS RENOMEADOS PARA AS PASTAS CORRETAS
        logger.info(f"=== FASE 2: MOVENDO {len(renamed_files)} ARQUIVOS PARA DESTINOS ===")
        
        # Verificar existência das pastas de destino e criar se necessário
        for file_info in renamed_files:
            destination = file_info["destination"]
            try:
                # Verificar se a pasta existe e criar se necessário
                folder_exists = await check_folder_exists(token, site_url, destination)
                if not folder_exists:
                    logger.info(f"Criando pasta de destino: {destination}")
                    success = await create_folder(token, site_url, destination)
                    if not success:
                        logger.error(f"Falha ao criar pasta {destination}")
                        results["erros"].append({
                            "arquivo": file_info["name"],
                            "erro": f"falha ao criar pasta de destino {destination}"
                        })
                        continue
                
                # Mover o arquivo
                file_name = file_info["name"]
                file_content = file_info["content"]
                
                # Fazer upload na pasta de destino
                success = await upload_file(token, site_url, file_content, file_name, destination)
                
                if success:
                    # Excluir da pasta de entrada
                    delete_success = await delete_file(token, site_url, PATHS["ENTRADA"], file_name)
                    
                    if delete_success:
                        results["movidos"].append({
                            "arquivo": file_name,
                            "destino": destination
                        })
                        logger.info(f"Arquivo movido com sucesso: {file_name} -> {destination}")
                    else:
                        logger.error(f"Erro ao excluir arquivo da pasta de entrada após mover: {file_name}")
                        results["erros"].append({
                            "arquivo": file_name,
                            "erro": "falha ao excluir da pasta de entrada após mover"
                        })
                else:
                    logger.error(f"Erro ao fazer upload do arquivo no destino: {file_name} -> {destination}")
                    results["erros"].append({
                        "arquivo": file_name,
                        "erro": f"falha ao fazer upload no destino {destination}"
                    })
            
            except Exception as e:
                logger.exception(f"Erro ao mover arquivo {file_info['name']}")
                results["erros"].append({
                    "arquivo": file_info["name"],
                    "erro": f"erro ao mover: {str(e)}"
                })
        
        # Calcular totais para relatório
        totais = {key: len(value) for key, value in results.items()}
        total_renomeados = sum(len(results[k]) for k in ["qpe_sem_letra", "qpe_com_letra", "spb_sem_letra", "telecom"])
        total_movidos = len(results["movidos"])
        
        return {
            "success": True,
            "mensagem": f"Processamento concluído: {total_renomeados} arquivos renomeados, {total_movidos} arquivos movidos",
            "resultados": results,
            "totais": totais,
            "total_arquivos": len(entrada_files)
        }

    except Exception as e:
        logger.exception("Erro geral no processamento")
        return {"success": False, "message": f"Erro geral: {str(e)}"}

# Manter um endpoint compatível com o frontend atual
@router.post("/process")
async def process_entrada_files():
    """
    Endpoint de compatibilidade que chama o /rename-clean.
    Mantido para compatibilidade com o frontend existente.
    """
    return await rename_files_clean()

# Manter endpoint para status de processamento
@router.get("/process-status")
async def get_process_status():
    """
    Retorna informações sobre o status do último processamento.
    """
    return {
        "status": "completed",
        "message": "Processamento concluído com sucesso",
        "processingType": "rename-and-move"
    }

# Manter endpoint para verificar se o serviço está ativo
@router.get("/entrada-status")
async def get_entrada_status():
    """
    Retorna o status do processamento de arquivos da pasta ENTRADA.
    """
    return {
        "status": "ready",
        "message": "Pronto para processar arquivos",
        "last_processed": len(processed_files_history)
    }

# Manter um endpoint de reset para limpar possíveis estados presos
@router.post("/reset-status")
async def reset_status():
    """
    Reseta o status de processamento e limpa o histórico.
    """
    global processed_files_history
    processed_files_history.clear()
    
    return {
        "success": True,
        "message": "Status resetado com sucesso"
    }
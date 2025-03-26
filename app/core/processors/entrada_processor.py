import os
import re
import logging
import json
import sys
import traceback
from datetime import datetime
from io import BytesIO
import PyPDF2
from typing import Dict, List, Any, Optional

from app.core.sharepoint import SharePointClient
from app.core.auth import SharePointAuth

# Configurar logging mais detalhado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("entrada_processor.log")
    ]
)
logger = logging.getLogger(__name__)

class EntradaProcessor:
    """
    Classe responsável por processar arquivos da pasta ENTRADA
    e distribuí-los para as pastas apropriadas.
    """
    
    def __init__(self):
        logger.info("Inicializando EntradaProcessor")
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        
        # Pastas do SharePoint
        self.PATHS = {
            "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
            "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
            "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
            "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
            "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
        }
        logger.debug(f"Caminhos configurados: {self.PATHS}")
        
        # Status do processamento
        self.processing_status = {
            "last_run": None,
            "success": False,
            "files_processed": 0,
            "details": []
        }
        
        # Cria a pasta cache se não existir
        cache_dir = "cache"
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"Pasta cache verificada/criada: {os.path.abspath(cache_dir)}")
    
    def get_last_processing_status(self) -> Dict[str, Any]:
        """
        Retorna o status do último processamento
        """
        logger.debug("Obtendo status do último processamento")
        # Se não houver status em memória, tenta ler do arquivo cache
        if self.processing_status["last_run"] is None:
            try:
                cache_file = "cache/entrada_processing_status.json"
                logger.debug(f"Verificando arquivo de cache: {os.path.abspath(cache_file)}")
                
                if os.path.exists(cache_file):
                    with open(cache_file, "r") as f:
                        self.processing_status = json.load(f)
                    logger.info(f"Status carregado do cache: último processamento em {self.processing_status['last_run']}")
                else:
                    logger.info("Arquivo de cache não encontrado, usando status padrão")
            except Exception as e:
                logger.error(f"Erro ao ler status de processamento do cache: {str(e)}")
                logger.error(traceback.format_exc())
        
        return self.processing_status
    
    def _save_processing_status(self):
        """
        Salva o status do processamento no cache
        """
        try:
            cache_file = "cache/entrada_processing_status.json"
            logger.debug(f"Salvando status no cache: {cache_file}")
            
            # Adicionar timestamp para debugging
            status_to_save = self.processing_status.copy()
            status_to_save["saved_at"] = datetime.now().isoformat()
            
            with open(cache_file, "w") as f:
                json.dump(status_to_save, f)
            
            logger.info(f"Status de processamento salvo com sucesso: {status_to_save}")
        except Exception as e:
            logger.error(f"Erro ao salvar status de processamento no cache: {str(e)}")
            logger.error(traceback.format_exc())
    
    async def process_files(self):
        """
        Processa os arquivos da pasta ENTRADA
        """
        try:
            logger.info(f"======= INÍCIO DO PROCESSAMENTO DE ARQUIVOS =======")
            logger.info(f"Data/hora: {datetime.now().isoformat()}")
            
            # Inicializa o status deste processamento
            self.processing_status = {
                "last_run": datetime.now().isoformat(),
                "success": False,
                "files_processed": 0,
                "details": []
            }
            logger.debug("Status de processamento inicializado")
            
            # Verificar acesso ao SharePoint
            token = self.sharepoint_auth.acquire_token()
            if not token:
                logger.error("FALHA CRÍTICA: Não foi possível obter token de autenticação do SharePoint")
                self.processing_status["error"] = "Falha na autenticação com SharePoint"
                self._save_processing_status()
                return
            logger.info("Autenticação com SharePoint bem-sucedida")
            
            # Lista os arquivos da pasta ENTRADA
            logger.info(f"Listando arquivos da pasta ENTRADA: {self.PATHS['ENTRADA']}")
            entrada_files = await self.sharepoint_client.list_files(self.PATHS["ENTRADA"])
            
            if entrada_files is None:
                logger.error("Falha ao listar arquivos: método retornou None")
                self.processing_status["error"] = "Falha ao listar arquivos da pasta ENTRADA"
                self._save_processing_status()
                return
            
            if not entrada_files:
                logger.info("Nenhum arquivo encontrado na pasta ENTRADA")
                self.processing_status["success"] = True
                self.processing_status["message"] = "Nenhum arquivo encontrado para processar"
                self._save_processing_status()
                return
            
            logger.info(f"Encontrados {len(entrada_files)} arquivos na pasta ENTRADA")
            logger.debug(f"Arquivos encontrados: {[f.get('Name', 'Sem nome') for f in entrada_files]}")
            
            # Processa cada arquivo
            for file in entrada_files:
                file_name = file.get("Name", "")
                file_result = {
                    "file_name": file_name,
                    "processed": False,
                    "destination": None,
                    "error": None
                }
                
                try:
                    logger.info(f"PROCESSANDO ARQUIVO: {file_name}")
                    
                    # Determina o tipo de arquivo e faz o processamento apropriado
                    if "R189" in file_name:
                        logger.info(f"Arquivo identificado como R189: {file_name}")
                        await self._process_r189_file(file_name)
                        file_result["destination"] = "R189"
                        file_result["processed"] = True
                        
                    elif re.search(r"QPE-\d{6}$", file_name):
                        logger.info(f"Arquivo identificado como QPE com cidade: {file_name}")
                        await self._process_qpe_cidade_file(file_name)
                        file_result["destination"] = "QPE"
                        file_result["processed"] = True
                        
                    elif re.search(r"QPE-\d{6}[A-Za-z]", file_name):
                        logger.info(f"Arquivo identificado como QPE fatura: {file_name}")
                        await self._process_qpe_fatura_file(file_name)
                        file_result["destination"] = "NFSERV"
                        file_result["processed"] = True
                        
                    elif any(city in file_name for city in ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]) and re.search(r"\d{6}[A-Za-z]\d{2}", file_name):
                        logger.info(f"Arquivo identificado como telecom: {file_name}")
                        await self._process_telecom_file(file_name)
                        file_result["destination"] = "NFSERV"
                        file_result["processed"] = True
                        
                    elif re.search(r"SPB-\d{6}", file_name):
                        logger.info(f"Arquivo identificado como SPB com cidade: {file_name}")
                        await self._process_spb_cidade_file(file_name)
                        file_result["destination"] = "SPB"
                        file_result["processed"] = True
                        
                    else:
                        logger.warning(f"Arquivo {file_name} não corresponde a nenhum padrão conhecido")
                        logger.debug(f"Verificação de padrões para {file_name}:")
                        logger.debug(f"  - R189 in file_name: {'R189' in file_name}")
                        logger.debug(f"  - QPE-\d{{6}}$: {bool(re.search(r'QPE-\d{6}$', file_name))}")
                        logger.debug(f"  - QPE-\d{{6}}[A-Za-z]: {bool(re.search(r'QPE-\d{6}[A-Za-z]', file_name))}")
                        logger.debug(f"  - SPB-\d{{6}}: {bool(re.search(r'SPB-\d{6}', file_name))}")
                        
                        file_result["error"] = "Padrão de nome não reconhecido"
                    
                except Exception as e:
                    error_trace = traceback.format_exc()
                    logger.error(f"Erro ao processar arquivo {file_name}: {str(e)}")
                    logger.error(error_trace)
                    file_result["error"] = str(e)
                
                # Adiciona o resultado deste arquivo ao status
                self.processing_status["details"].append(file_result)
                if file_result["processed"]:
                    self.processing_status["files_processed"] += 1
                
                # Salva o status parcial para não perder progresso em caso de falha
                self._save_processing_status()
            
            # Marca o processamento como concluído com sucesso
            self.processing_status["success"] = True
            logger.info(f"Processamento concluído. {self.processing_status['files_processed']} arquivos processados com sucesso.")
            
            # Salva o status final
            self._save_processing_status()
            
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"ERRO GERAL no processamento de arquivos: {str(e)}")
            logger.error(error_trace)
            self.processing_status["success"] = False
            self.processing_status["error"] = str(e)
            self._save_processing_status()
            
        finally:
            logger.info("======= FIM DO PROCESSAMENTO DE ARQUIVOS =======")
    
    async def _process_r189_file(self, file_name: str):
        """
        Processa arquivo R189
        """
        logger.info(f"Iniciando processamento de arquivo R189: {file_name}")
        
        # Download do arquivo
        logger.debug(f"Baixando arquivo da pasta ENTRADA: {file_name}")
        file_content = await self._download_file(file_name, self.PATHS["ENTRADA"])
        if not file_content:
            error_msg = f"Não foi possível baixar o arquivo {file_name}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # Upload para a pasta R189
        logger.debug(f"Enviando arquivo para a pasta R189: {file_name}")
        success = await self._upload_file(file_content, file_name, self.PATHS["R189"])
        if not success:
            error_msg = f"Não foi possível enviar o arquivo {file_name} para a pasta R189"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        logger.info(f"Arquivo R189 processado com sucesso: {file_name}")
    
    async def _process_qpe_cidade_file(self, file_name: str):
        """
        Processa arquivo QPE com extração de cidade
        """
        # Download do arquivo
        file_content = await self._download_file(file_name, self.PATHS["ENTRADA"])
        if not file_content:
            raise Exception(f"Não foi possível baixar o arquivo {file_name}")
        
        # Extrair cidade do PDF
        cidade = await self._extract_city_from_qpe(file_content)
        
        # Criar novo nome com cidade
        new_file_name = f"{cidade}_{file_name}" if cidade else file_name
        
        # Upload para a pasta QPE
        success = await self._upload_file(file_content, new_file_name, self.PATHS["QPE"])
        if not success:
            raise Exception(f"Não foi possível enviar o arquivo {new_file_name} para a pasta QPE")
        
        logger.info(f"Arquivo QPE processado com sucesso: {file_name} -> {new_file_name}")
    
    async def _process_qpe_fatura_file(self, file_name: str):
        """
        Processa arquivo QPE com padrão de fatura
        """
        # Download do arquivo
        file_content = await self._download_file(file_name, self.PATHS["ENTRADA"])
        if not file_content:
            raise Exception(f"Não foi possível baixar o arquivo {file_name}")
        
        # Criar novo nome com prefixo
        new_file_name = f"FATURA-LOCAÇÃO_{file_name}"
        
        # Upload para a pasta NFSERV
        success = await self._upload_file(file_content, new_file_name, self.PATHS["NFSERV"])
        if not success:
            raise Exception(f"Não foi possível enviar o arquivo {new_file_name} para a pasta NFSERV")
        
        logger.info(f"Arquivo QPE-Fatura processado com sucesso: {file_name} -> {new_file_name}")
    
    async def _process_telecom_file(self, file_name: str):
        """
        Processa arquivo de telecomunicações (BLU, POA, etc.)
        """
        # Download do arquivo
        file_content = await self._download_file(file_name, self.PATHS["ENTRADA"])
        if not file_content:
            raise Exception(f"Não foi possível baixar o arquivo {file_name}")
        
        # Criar novo nome com prefixo
        new_file_name = f"TELECOMUNICAÇÕES_{file_name}"
        
        # Upload para a pasta NFSERV
        success = await self._upload_file(file_content, new_file_name, self.PATHS["NFSERV"])
        if not success:
            raise Exception(f"Não foi possível enviar o arquivo {new_file_name} para a pasta NFSERV")
        
        logger.info(f"Arquivo Telecom processado com sucesso: {file_name} -> {new_file_name}")
    
    async def _process_spb_cidade_file(self, file_name: str):
        """
        Processa arquivo SPB com extração de cidade
        """
        # Download do arquivo
        file_content = await self._download_file(file_name, self.PATHS["ENTRADA"])
        if not file_content:
            raise Exception(f"Não foi possível baixar o arquivo {file_name}")
        
        # Extrair cidade do PDF
        cidade = await self._extract_city_from_spb(file_content)
        
        # Criar novo nome com cidade
        new_file_name = f"{cidade}_{file_name}" if cidade else file_name
        
        # Upload para a pasta SPB
        success = await self._upload_file(file_content, new_file_name, self.PATHS["SPB"])
        if not success:
            raise Exception(f"Não foi possível enviar o arquivo {new_file_name} para a pasta SPB")
        
        logger.info(f"Arquivo SPB processado com sucesso: {file_name} -> {new_file_name}")
    
    async def _download_file(self, file_name: str, folder_path: str) -> Optional[BytesIO]:
        """
        Faz o download de um arquivo do SharePoint
        """
        try:
            # Tenta método 1: usando SharePointClient
            file_data = await self.sharepoint_client.download_file(folder_path, file_name)
            if file_data:
                return file_data
            
            # Tenta método 2: usando SharePointAuth
            file_content = self.sharepoint_auth.baixar_arquivo_sharepoint(file_name, folder_path)
            if file_content:
                return BytesIO(file_content)
            
            return None
        except Exception as e:
            logger.error(f"Erro ao baixar arquivo {file_name}: {str(e)}")
            return None
    
    async def _upload_file(self, file_content: BytesIO, file_name: str, folder_path: str) -> bool:
        """
        Faz o upload de um arquivo para o SharePoint
        """
        try:
            # Tenta método 1: usando SharePointClient
            success = await self.sharepoint_client.upload_file(
                file_content=file_content,
                destination_name=file_name,
                folder_path=folder_path
            )
            
            if success:
                return True
            
            # Tenta método 2: usando SharePointAuth
            file_content.seek(0)  # Reinicia o ponteiro do arquivo
            success = self.sharepoint_auth.enviar_para_sharepoint(
                conteudo_arquivo=file_content,
                nome_destino=file_name,
                pasta_r189=folder_path
            )
            
            return success
        except Exception as e:
            logger.error(f"Erro ao enviar arquivo {file_name}: {str(e)}")
            return False
    
    async def _extract_city_from_qpe(self, file_content: BytesIO) -> Optional[str]:
        """
        Extrai a cidade de um arquivo PDF QPE
        """
        try:
            # Cria um objeto PDF
            file_content.seek(0)
            reader = PyPDF2.PdfReader(file_content)
            
            # Extrai texto de todas as páginas
            texto_combinado = ""
            for page_num in range(len(reader.pages)):
                texto_combinado += reader.pages[page_num].extract_text()
            
            # Busca cidade com o regex
            padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
            cidade_match = re.search(padrao_cidade, texto_combinado)
            cidade = cidade_match.group(1).strip() if cidade_match else None
            
            logger.info(f"Cidade extraída do QPE: {cidade}")
            return cidade
        except Exception as e:
            logger.error(f"Erro ao extrair cidade do QPE: {str(e)}")
            return None
    
    async def _extract_city_from_spb(self, file_content: BytesIO) -> Optional[str]:
        """
        Extrai a cidade de um arquivo PDF SPB
        """
        try:
            # Cria um objeto PDF
            file_content.seek(0)
            reader = PyPDF2.PdfReader(file_content)
            
            # Extrai texto de todas as páginas
            texto_combinado = ""
            for page_num in range(len(reader.pages)):
                texto_combinado += reader.pages[page_num].extract_text()
            
            # Busca cidade com o regex
            padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
            cidade_match = re.search(padrao_cidade, texto_combinado)
            cidade = re.sub(r'----$', '', cidade_match.group(1)).strip() if cidade_match else None
            
            logger.info(f"Cidade extraída do SPB: {cidade}")
            return cidade
        except Exception as e:
            logger.error(f"Erro ao extrair cidade do SPB: {str(e)}")
            return None 
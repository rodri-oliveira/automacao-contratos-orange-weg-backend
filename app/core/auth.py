import os
from dotenv import load_dotenv
import requests
import logging
from typing import Optional
from io import BytesIO
import traceback
import json

# Configurar logging mais detalhado
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SharePointAuth:
    def __init__(self):
        load_dotenv()
        logger.debug("Iniciando SharePointAuth...")
        
        # Log das variáveis de ambiente (sem expor secrets)
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.tenant_id = os.getenv("TENANT_ID")
        logger.debug(f"CLIENT_ID presente: {'Sim' if self.client_id else 'Não'}")
        logger.debug(f"CLIENT_SECRET presente: {'Sim' if self.client_secret else 'Não'}")
        logger.debug(f"TENANT_ID presente: {'Sim' if self.tenant_id else 'Não'}")
        
        # Tratamento do RESOURCE com logs
        resource = os.getenv("RESOURCE", "")
        logger.debug(f"RESOURCE original: {resource}")
        
        if "/" in resource:
            parts = resource.split("/")
            self.resource = parts[0]
            self.sharepoint_host = parts[1]
            logger.debug(f"RESOURCE processado - resource: {self.resource}")
            logger.debug(f"RESOURCE processado - sharepoint_host: {self.sharepoint_host}")
        else:
            logger.warning("RESOURCE não contém '/', usando valores padrão")
            self.resource = "00000003-0000-0ff1-ce00-000000000000"
            self.sharepoint_host = "weg365.sharepoint.com"
        
        self.site_url = os.getenv("SITE_URL", "").rstrip('/')
        logger.debug(f"SITE_URL configurada: {self.site_url}")
        
        self.token_url = f"https://accounts.accesscontrol.windows.net/{self.tenant_id}/tokens/OAuth/2"
        logger.debug(f"Token URL configurada: {self.token_url}")
        
        self._validate_credentials()

    def _validate_credentials(self):
        """Valida se todas as credenciais necessárias estão presentes."""
        logger.debug("Validando credenciais...")
        credenciais = {
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET": self.client_secret,
            "TENANT_ID": self.tenant_id,
            "RESOURCE": self.resource,
            "SITE_URL": self.site_url
        }
        
        missing = [k for k, v in credenciais.items() if not v]
        if missing:
            error_msg = f"Credenciais faltando: {', '.join(missing)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.debug("Todas as credenciais estão presentes")

    def acquire_token(self):
        """Obtém o token de autenticação para acessar o SharePoint."""
        try:
            logger.debug("Iniciando processo de obtenção do token...")
            
            # Corrigindo a formatação do resource_url
            resource_url = f"{self.resource}/{self.sharepoint_host}@{self.tenant_id}"
            client_id = f"{self.client_id}@{self.tenant_id}"
            
            logger.debug(f"Resource URL montada: {resource_url}")
            logger.debug(f"Client ID montado: {client_id}")
            
            payload = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': self.client_secret,
                'resource': resource_url
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            logger.info(f"Fazendo requisição para obter token em: {self.token_url}")
            logger.debug(f"Payload da requisição: {json.dumps(payload, default=str)}")
            
            response = requests.post(
                self.token_url,
                data=payload,
                headers=headers,
                verify=True
            )
            
            logger.debug(f"Status code: {response.status_code}")
            logger.debug(f"Resposta completa: {response.text}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("Token obtido com sucesso!")
                return token_data.get('access_token')
            else:
                logger.error(f"Erro na autenticação: {response.status_code}")
                logger.error(f"Detalhes do erro: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Erro durante autenticação: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def baixar_arquivo_sharepoint(self, nome_arquivo: str, pasta_r189: str) -> Optional[BytesIO]:
        """
        Baixa um arquivo específico do SharePoint.
        
        Args:
            nome_arquivo: Nome do arquivo a ser baixado
            pasta_r189: Caminho da pasta no SharePoint
            
        Returns:
            BytesIO contendo o arquivo ou None se houver erro
        """
        token = self.acquire_token()
        if not token:
            logger.error("Falha ao obter token para download")
            return None

        url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{pasta_r189}/{nome_arquivo}')/$value"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return BytesIO(response.content)
            else:
                logger.error(f"Erro ao baixar arquivo: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Erro durante o download: {str(e)}")
            return None

    def enviar_para_sharepoint(self, conteudo_arquivo: BytesIO, nome_destino: str, pasta_r189: str) -> bool:
        """
        Envia um arquivo para o SharePoint, substituindo o arquivo existente se já estiver presente.
        
        Args:
            conteudo_arquivo: BytesIO contendo o arquivo a ser enviado
            nome_destino: Nome do arquivo no destino
            pasta_r189: Caminho relativo da pasta no SharePoint
            
        Returns:
            bool indicando sucesso ou falha
        """
        token = self.acquire_token()
        if not token:
            logger.error("Falha ao obter token para upload")
            return False

        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/octet-stream'
        }

        endpoint_upload = (
            f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{pasta_r189}')"
            f"/Files/add(url='{nome_destino}',overwrite=true)"
        )

        try:
            logger.info(f"Enviando arquivo para: {endpoint_upload}")
            response = requests.post(
                endpoint_upload,
                headers=headers,
                data=conteudo_arquivo.getvalue()
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Arquivo {nome_destino} enviado com sucesso")
                return True
            else:
                logger.error(f"Erro ao enviar arquivo. Status: {response.status_code}")
                logger.error(f"Resposta: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Erro durante upload: {str(e)}")
            logger.error(traceback.format_exc())
            return False
        
    def excluir_arquivo_sharepoint(self, nome_arquivo: str, pasta_r189: str) -> bool:
        """
        Exclui um arquivo específico no SharePoint
        """
        token = self.acquire_token()
        if not token:
            return False

        url = (
            f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{pasta_r189}/{nome_arquivo}')/"
            "DeleteObject()"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose",
            "X-RequestDigest": self._get_request_digest(token)
        }

        try:
            response = requests.post(url, headers=headers)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Erro ao excluir arquivo: {str(e)}")
            return False

    def _get_request_digest(self, token: str) -> str:
        """
        Obtém o request digest necessário para operações de escrita no SharePoint
        """
        url = f"{self.site_url}/_api/contextinfo"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }
        
        try:
            response = requests.post(url, headers=headers)
            if response.status_code == 200:
                return response.json()['d']['GetContextWebInformation']['FormDigestValue']
            return ""
        except Exception as e:
            logger.error(f"Erro ao obter request digest: {str(e)}")
            return ""

    async def fazer_requisicao_sharepoint(self, url: str, headers: dict):
        """Faz uma requisição ao SharePoint."""
        try:
            logger.info(f"Iniciando requisição para: {url}")
            logger.debug(f"Headers: {json.dumps(headers)}")
            
            response = requests.get(
                url,
                headers=headers,
                verify=True  # Garante verificação SSL
            )
            
            logger.debug(f"Status da resposta: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("Requisição bem sucedida")
                return response
            else:
                logger.error(f"Erro na requisição: {response.status_code}")
                logger.error(f"Detalhes: {response.text}")
                return response
            
        except Exception as e:
            logger.error(f"Erro na requisição: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
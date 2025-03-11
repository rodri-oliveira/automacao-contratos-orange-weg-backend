import os
from dotenv import load_dotenv
import requests
from io import BytesIO
from typing import Optional, List, Dict, Any
import logging
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

class SharePointAuth:
    def __init__(self):
        load_dotenv()
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.tenant_id = os.getenv("TENANT_ID")
        self.resource = os.getenv("RESOURCE")
        self.site_url = os.getenv("SITE_URL", "").rstrip('/')
        self._validate_credentials()
    
    def _validate_credentials(self):
        """Valida se todas as credenciais necessárias estão presentes."""
        credenciais = {
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET": self.client_secret,
            "TENANT_ID": self.tenant_id,
            "RESOURCE": self.resource,
            "SITE_URL": self.site_url
        }
        
        missing = [key for key, value in credenciais.items() if not value]
        if missing:
            raise ValueError(f"Credenciais ausentes: {', '.join(missing)}")
    
    def acquire_token(self) -> Optional[str]:
        """Adquire um token de acesso para o SharePoint."""
        try:
            token_endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/token"
            
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'resource': self.resource
            }
            
            response = requests.post(token_endpoint, data=data)
            response.raise_for_status()  # Lança exceção para status codes de erro
            
            return response.json().get("access_token")
            
        except Exception as e:
            logger.error(f"Erro ao adquirir token: {str(e)}")
            return None

class SharePointClient:
    def __init__(self):
        self.auth = SharePointAuth()
        self.logger = logging.getLogger(__name__)
        self.site_url = os.getenv("SITE_URL", "").rstrip('/')
        self._session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def list_files(self, folder_path: str) -> Optional[List[Dict[str, Any]]]:
        """Lista arquivos em uma pasta do SharePoint de forma assíncrona"""
        try:
            token = self.auth.acquire_token()
            if not token:
                self.logger.error("Failed to acquire token")
                return None

            session = await self._get_session()
            url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json;odata=verbose"
            }

            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("d", {}).get("results", [])
                else:
                    self.logger.error(f"Error listing files: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error listing files: {str(e)}")
            return None

    async def download_file(self, folder_path: str, file_name: str) -> Optional[BytesIO]:
        """Download de arquivo do SharePoint de forma assíncrona"""
        try:
            token = self.auth.acquire_token()
            if not token:
                return None

            session = await self._get_session()
            url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{folder_path}/{file_name}')/$value"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json;odata=verbose"
            }

            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    return BytesIO(content)
                else:
                    self.logger.error(f"Error downloading file: {response.status}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error downloading file: {str(e)}")
            return None

    async def upload_file(self, file_content: BytesIO, destination_name: str, folder_path: str) -> bool:
        """Upload a file to SharePoint asynchronously"""
        try:
            token = self.auth.acquire_token()
            if not token:
                self.logger.error("Failed to acquire token")
                return False

            url = (
                f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')"
                f"/Files/add(url='{destination_name}',overwrite=true)"
            )

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream"
            }

            session = await self._get_session()
            
            self.logger.info(f"Enviando arquivo para: {url}")
            self.logger.info(f"Tamanho do arquivo: {file_content.getbuffer().nbytes} bytes")
            
            async with session.post(url, data=file_content.getvalue(), headers=headers) as response:
                if response.status in [200, 201]:
                    self.logger.info(f"Arquivo {destination_name} enviado com sucesso")
                    return True
                else:
                    self.logger.error(f"Erro ao enviar arquivo. Status: {response.status}")
                    response_text = await response.text()
                    self.logger.error(f"Resposta: {response_text}")
                    return False
            
        except Exception as e:
            self.logger.error(f"Error uploading file: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False


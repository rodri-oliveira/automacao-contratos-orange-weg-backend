import os
from dotenv import load_dotenv
import requests
from io import BytesIO
from typing import Optional, List, Dict, Any
import logging
from fastapi import Depends, HTTPException

logger = logging.getLogger(__name__)

class SharePointAuth:
    def __init__(self):
        load_dotenv()
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.tenant_id = os.getenv("TENANT_ID")
        self.resource = os.getenv("RESOURCE")
        self.site_url = os.getenv("SITE_URL").rstrip('/')
        self.token_url = f"https://accounts.accesscontrol.windows.net/{self.tenant_id}/tokens/OAuth/2"
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
    
    def acquire_token(self):
        """
        Adquire um token de acesso para o SharePoint usando autenticação de aplicativo.
        """
        try:
            # Endpoint para obter o token
            token_endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/token"
            
            # Dados para a requisição
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'resource': self.resource
            }
            
            # Fazer a requisição para obter o token
            response = requests.post(token_endpoint, data=data)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")
            else:
                print(f"Erro ao obter token: {response.status_code}")
                return None
        except Exception as e:
            print(f"Erro ao adquirir token: {str(e)}")
            return None

class SharePointClient:
    def __init__(self):
        self.site_url = os.getenv("SITE_URL")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.tenant_id = os.getenv("TENANT_ID")
        self.resource = os.getenv("RESOURCE")
        self.token = None
        
    def acquire_token(self):
        """
        Adquire um token de acesso para o SharePoint usando autenticação de aplicativo.
        """
        try:
            # Endpoint para obter o token
            token_endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/token"
            
            # Dados para a requisição
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'resource': self.resource
            }
            
            # Fazer a requisição para obter o token
            response = requests.post(token_endpoint, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.token = token_data.get('access_token')
                return self.token
            else:
                print(f"Erro ao obter token: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Erro ao adquirir token: {str(e)}")
            return None
    
    def list_files(self, folder_path):
        """
        Lista arquivos em uma pasta do SharePoint.
        """
        if not self.token:
            self.token = self.acquire_token()
            
        if not self.token:
            raise Exception("Falha na autenticação com SharePoint")
            
        url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            files = [
                {
                    "name": file["Name"],
                    "size": file["Length"],
                    "modified": file["TimeLastModified"]
                }
                for file in data["d"]["results"]
            ]
            return files
        else:
            raise Exception(f"Erro ao buscar arquivos: {response.status_code} - {response.text}")
    
    def download_file(self, file_path):
        """
        Baixa um arquivo do SharePoint.
        """
        if not self.token:
            self.token = self.acquire_token()
            
        if not self.token:
            raise Exception("Falha na autenticação com SharePoint")
            
        url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{file_path}')/$value"
        
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f"Erro ao baixar arquivo: {response.status_code} - {response.text}")
    
    def upload_file(self, folder_path, file_name, file_content):
        """
        Envia um arquivo para o SharePoint.
        """
        if not self.token:
            self.token = self.acquire_token()
            
        if not self.token:
            raise Exception("Falha na autenticação com SharePoint")
            
        url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(url='{file_name}',overwrite=true)"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/octet-stream"
        }
        
        response = requests.post(url, headers=headers, data=file_content)
        
        if response.status_code in [200, 201]:
            return True
        else:
            raise Exception(f"Erro ao enviar arquivo: {response.status_code} - {response.text}")

class SharePointService:
    def __init__(self, auth: SharePointAuth = None):
        self.auth = auth or SharePointAuth()
        self.site_url = os.getenv("SITE_URL").rstrip('/')
        self.folders = {
            'R189': "/teams/BR-TI-TIN/AutomaoFinanas/R189",
            'QPE': "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
            'SPB': "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
            'NFSERV': "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV"
        }

    async def list_files(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        Lista arquivos em uma pasta do SharePoint.
        """
        token = self.auth.acquire_token()
        if not token:
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")
            
        url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            files = [
                {
                    "name": file["Name"],
                    "size": file["Length"],
                    "modified": file["TimeLastModified"]
                }
                for file in data["d"]["results"]
            ]
            return files
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro ao buscar arquivos: {response.status_code}"
            )

    async def download_file(self, folder_path: str, file_name: str) -> Optional[BytesIO]:
        """Baixa um arquivo específico do SharePoint."""
        token = self.auth.acquire_token()
        if not token:
            logger.error("Falha ao obter token para download")
            return None

        url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{folder_path}/{file_name}')/$value"
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

    async def upload_file(self, folder_path: str, file_name: str, content: BytesIO) -> bool:
        """Envia um arquivo para o SharePoint."""
        token = self.auth.acquire_token()
        if not token:
            logger.error("Falha ao obter token para upload")
            return False

        url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(url='{file_name}',overwrite=true)"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json;odata=verbose"
        }

        try:
            response = requests.post(url, headers=headers, data=content.getvalue())
            if response.status_code in [200, 201]:
                logger.info(f"Arquivo {file_name} enviado com sucesso")
                return True
            else:
                logger.error(f"Erro ao enviar arquivo: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Erro durante o upload: {str(e)}")
            return False

def get_sharepoint_service():
    """
    Dependency para injetar o serviço SharePoint.
    """
    return SharePointService()
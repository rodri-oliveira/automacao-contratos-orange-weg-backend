import os
from dotenv import load_dotenv
import requests
from io import BytesIO
from typing import Optional

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
        """Obtém o token de autenticação para acessar o SharePoint."""
        payload = {
            'grant_type': 'client_credentials',
            'client_id': f"{self.client_id}@{self.tenant_id}",
            'client_secret': self.client_secret,
            'resource': f"{self.resource}@{self.tenant_id}"
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            response = requests.post(self.token_url, data=payload, headers=headers)
            
            if response.status_code == 200:
                return response.json()['access_token']
            else:
                print(f"Erro na autenticação: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter token: {str(e)}")
            return None

    def baixar_arquivo_sharepoint(self, nome_arquivo: str, pasta: str) -> Optional[BytesIO]:
        """
        Baixa um arquivo específico do SharePoint.
        
        Args:
            nome_arquivo: Nome do arquivo a ser baixado
            pasta: Caminho da pasta no SharePoint
            
        Returns:
            BytesIO contendo o arquivo ou None se houver erro
        """
        token = self.acquire_token()
        if not token:
            print("Falha ao obter token para download")
            return None

        url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{pasta}/{nome_arquivo}')/$value"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return BytesIO(response.content)
            else:
                print(f"Erro ao baixar arquivo: {response.status_code}")
                return None
        except Exception as e:
            print(f"Erro durante o download: {str(e)}")
            return None

    def enviar_para_sharepoint(self, conteudo_arquivo: BytesIO, nome_destino: str, pasta: str) -> bool:
        """
        Envia um arquivo para o SharePoint, substituindo o arquivo existente se já estiver presente.
        
        Args:
            conteudo_arquivo: BytesIO contendo o arquivo a ser enviado
            nome_destino: Nome do arquivo no destino
            pasta: Caminho relativo da pasta no SharePoint
            
        Returns:
            bool indicando sucesso ou falha
        """
        token = self.acquire_token()
        if not token:
            print("Falha ao obter token para upload")
            return False

        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/octet-stream'
        }

        endpoint_upload = (
            f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{pasta}')"
            f"/Files/add(url='{nome_destino}',overwrite=true)"
        )

        try:
            print(f"Enviando arquivo para: {endpoint_upload}")
            response = requests.post(
                endpoint_upload,
                headers=headers,
                data=conteudo_arquivo.getvalue()
            )
            
            if response.status_code in [200, 201]:
                print(f"Arquivo {nome_destino} enviado com sucesso")
                return True
            else:
                print(f"Erro ao enviar arquivo. Status: {response.status_code}")
                print(f"Resposta: {response.text}")
                return False
        except Exception as e:
            print(f"Erro durante upload: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False 
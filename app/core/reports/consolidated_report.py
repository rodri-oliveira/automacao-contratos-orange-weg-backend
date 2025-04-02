import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import logging
import os
import re

from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class ConsolidatedReport:
    """
    Classe responsável por consolidar os relatórios de divergências em um único arquivo Excel.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        self.relatorios_base_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS"
        
    async def _list_files_in_folder(self, folder_path):
        """
        Lista todos os arquivos Excel em uma pasta do SharePoint.
        """
        token = self.sharepoint_auth.acquire_token()
        if not token:
            logger.error("Falha ao obter token para listar arquivos")
            return []
        
        api_url = f"{self.sharepoint_auth.site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }
        
        try:
            response = await self.sharepoint_auth.fazer_requisicao_sharepoint(api_url, headers)
            
            if response.get('status_code') == 200:
                text = response.get('text', '{}')
                import json
                data = json.loads(text)
                files = data.get('d', {}).get('results', [])
                
                # Filtra apenas arquivos Excel
                excel_files = [f for f in files if f.get('Name', '').lower().endswith(('.xlsx', '.xls'))]
                
                return excel_files
            else:
                logger.error(f"Erro ao listar arquivos: {response.get('status_code')}")
                return []
        except Exception as e:
            logger.error(f"Exceção ao listar arquivos: {str(e)}")
            return []
    
    def _extract_date_from_filename(self, filename):
        """
        Extrai data e hora de um nome de arquivo com formato de data (AAAAMMDD_HHMMSS).
        """
        # Busca padrão de data no nome do arquivo
        pattern = r'(\d{8}_\d{6})'  # Formato: AAAAMMDD_HHMMSS
        match = re.search(pattern, filename)
        
        if match:
            try:
                # Converte para objeto datetime
                date_str = match.group(1)
                date_obj = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                return date_obj
            except ValueError:
                pass
        
        # Retorna data antiga se não encontrar padrão válido
        return datetime(1900, 1, 1)
    
    async def _get_latest_file(self, folder_path):
        """
        Obtém o arquivo Excel mais recente de uma pasta.
        """
        files = await self._list_files_in_folder(folder_path)
        
        if not files:
            logger.warning(f"Nenhum arquivo encontrado em: {folder_path}")
            return None
        
        # Ordena pelo timestamp extraído do nome do arquivo
        latest_file = max(files, key=lambda f: self._extract_date_from_filename(f.get('Name', '')))
        
        logger.info(f"Arquivo mais recente encontrado: {latest_file.get('Name')}")
        
        # Baixa o conteúdo do arquivo
        file_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
            latest_file.get('Name'),
            folder_path
        )
        
        if file_content:
            return {
                'name': latest_file.get('Name'),
                'content': file_content
            }
        
        return None
        
    async def consolidate_reports(self):
        """
        Cria um relatório consolidado com abas para cada tipo de relatório.
        """
        try:
            logger.info("=== INICIANDO CRIAÇÃO DE RELATÓRIO CONSOLIDADO ===")
            
            # Define as pastas e nomes das abas
            folders = [
                {"path": "MUN_CODE", "sheet_name": "Mun_Code_R189"},
                {"path": "SRV_CODE_SIMPLE", "sheet_name": "Srv_Code_Simple"},
                {"path": "R189", "sheet_name": "Divergencias_R189"},
                {"path": "QPE_R189", "sheet_name": "QPE_vs_R189"},
                {"path": "SPO_R189", "sheet_name": "SPB_vs_R189"},
                {"path": "NFSERV_R189", "sheet_name": "NFSERV_vs_R189"}
            ]
            
            # Cria DataFrames vazios para o caso de não encontrar arquivos
            reports_data = {
                folder["sheet_name"]: pd.DataFrame({"Mensagem": ["Relatório não disponível"]})
                for folder in folders
            }
            
            # Contador de relatórios encontrados
            found_reports = 0
            
            # Processa cada pasta
            for folder_info in folders:
                folder_path = f"{self.relatorios_base_path}/{folder_info['path']}"
                logger.info(f"Buscando o arquivo mais recente em: {folder_path}")
                
                # Obtém o arquivo mais recente
                file_data = await self._get_latest_file(folder_path)
                
                if file_data:
                    try:
                        # Lê o arquivo Excel
                        df = pd.read_excel(BytesIO(file_data['content']))
                        
                        if not df.empty:
                            reports_data[folder_info['sheet_name']] = df
                            found_reports += 1
                            logger.info(f"Arquivo {file_data['name']} lido com sucesso: {len(df)} linhas")
                    except Exception as e:
                        logger.error(f"Erro ao processar arquivo {file_data['name']}: {str(e)}")
            
            # Cria o arquivo Excel consolidado
            logger.info("Criando arquivo Excel consolidado")
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for sheet_name, df in reports_data.items():
                    # Limita o nome da aba a 31 caracteres (limite do Excel)
                    sheet_name = sheet_name[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    # Ajusta a largura das colunas
                    worksheet = writer.sheets[sheet_name]
                    for i, col in enumerate(df.columns):
                        max_length = max(
                            df[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.set_column(i, i, max_length + 2)
            
            output.seek(0)
            
            # Nome do arquivo consolidado com timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            consolidated_filename = f"RELATORIOS-ORANGE_{timestamp}.xlsx"
            
            # Pasta para salvar o relatório consolidado
            consolidado_path = f"{self.relatorios_base_path}/RELATORIO_CONSOLIDADO"
            
            # Envia o arquivo consolidado para o SharePoint
            logger.info(f"Enviando arquivo consolidado: {consolidated_filename} para {consolidado_path}")
            upload_success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                conteudo=output.getvalue(),
                nome_arquivo=consolidated_filename,
                pasta=consolidado_path
            )
            
            if not upload_success:
                logger.error("Erro ao enviar arquivo consolidado para o SharePoint")
                return {
                    "success": False,
                    "error": "Erro ao enviar arquivo consolidado para o SharePoint",
                    "show_popup": True
                }
            
            # Mensagem de sucesso com base no número de relatórios encontrados
            if found_reports > 0:
                message = f"Relatórios consolidados com sucesso no arquivo {consolidated_filename}.\n\nForam encontrados {found_reports} relatórios.\n\nO arquivo foi salvo na pasta RELATÓRIOS/RELATORIO_CONSOLIDADO no SharePoint."
            else:
                message = f"Arquivo consolidado criado com abas vazias, pois nenhum relatório foi encontrado.\n\nO arquivo foi salvo na pasta RELATÓRIOS/RELATORIO_CONSOLIDADO no SharePoint."
            
            logger.info("Arquivo consolidado enviado com sucesso")
            return {
                "success": True,
                "message": message,
                "show_popup": True,
                "filename": consolidated_filename
            }
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao consolidar relatórios: {str(e)}")
            return {
                "success": False,
                "error": f"Erro inesperado ao consolidar relatórios: {str(e)}",
                "show_popup": True
            }
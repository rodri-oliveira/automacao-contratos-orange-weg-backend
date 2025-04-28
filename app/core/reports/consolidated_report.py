import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import logging
import os
import re
import traceback
import aiohttp

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
        self.orange_repository_path = "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/RELATORIOS"
        
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
                {"path": "R189", "sheet_name": "Divergencias_R189"},
                {"path": "SRV_CODE_SIMPLE", "sheet_name": "Srv_Code_Simple"},
                {"path": "MUN_CODE", "sheet_name": "SRV_Code"}, # Nome da aba alterado
                {"path": "QPE_R189", "sheet_name": "QPE_vs_R189"},
                {"path": "SPO_R189", "sheet_name": "SPB_vs_R189"},
                {"path": "NFSERV_R189", "sheet_name": "FATURAS"} # Nome da aba alterado
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
            
            # Enviar também para o repositório Orange
            orange_result = await self.send_report_to_orange_repository(output.getvalue(), consolidated_filename)
            
            # Mensagem de sucesso com base no número de relatórios encontrados
            if found_reports > 0:
                message = f"Relatórios consolidados com sucesso no arquivo {consolidated_filename}.\n\nForam encontrados {found_reports} relatórios.\n\nO arquivo foi salvo na pasta RELATÓRIOS/RELATORIO_CONSOLIDADO no SharePoint."
                
                # Adiciona informação sobre o envio para o repositório Orange
                if orange_result.get("success"):
                    message += f"\n\nO arquivo também foi enviado para o repositório Orange no caminho: {orange_result.get('path')}"
            else:
                message = f"Arquivo consolidado criado com abas vazias, pois nenhum relatório foi encontrado.\n\nO arquivo foi salvo na pasta RELATÓRIOS/RELATORIO_CONSOLIDADO no SharePoint."
                
                # Adiciona informação sobre o envio para o repositório Orange
                if orange_result.get("success"):
                    message += f"\n\nO arquivo também foi enviado para o repositório Orange no caminho: {orange_result.get('path')}"
            
            logger.info("Arquivo consolidado enviado com sucesso")
            return {
                "success": True,
                "message": message,
                "show_popup": True,
                "filename": consolidated_filename,
                "orange_repository": orange_result
            }
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao consolidar relatórios: {str(e)}")
            return {
                "success": False,
                "error": f"Erro inesperado ao consolidar relatórios: {str(e)}",
                "show_popup": True
            }

    async def send_report_to_orange_repository(self, file_content, file_name):
        """
        Envia o relatório consolidado para o repositório Orange no SharePoint.
        
        O caminho base é: /teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/RELATORIOS
        
        Esta função:
        1. Verifica se existe uma pasta com o ano corrente (ex: 2025)
        2. Verifica se existe uma pasta com o ano e mês corrente (ex: 2025.04)
        3. Cria as pastas se não existirem
        4. Envia o relatório consolidado para a pasta ano.mês
        
        Args:
            file_content: Conteúdo do arquivo em bytes
            file_name: Nome do arquivo a ser enviado
            
        Returns:
            dict: Resultado da operação com informações sobre o sucesso e o caminho
        """
        try:
            logger.info("=== INICIANDO ENVIO PARA REPOSITÓRIO ORANGE ===")
            
            # Obter token de autenticação
            token = self.sharepoint_auth.acquire_token()
            if not token:
                logger.error("Falha ao obter token para envio ao repositório Orange")
                return {
                    "success": False,
                    "error": "Falha ao obter token para envio ao repositório Orange"
                }
            
            # URL base para o SharePoint Contratos - IMPORTANTE: é diferente do site_url padrão
            sharepoint_contratos_base_url = "https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos"
            logger.info(f"Usando URL base para SharePoint Contratos: {sharepoint_contratos_base_url}")
            
            # Obter data atual para criar estrutura de pastas
            current_date = datetime.now()
            current_year = str(current_date.year)
            current_year_month = f"{current_date.year}.{current_date.month:02d}"
            
            logger.info(f"Data atual: Ano={current_year}, Mês={current_year_month}")
            
            # Verificar se a pasta do ano existe
            year_folder_path = f"{self.orange_repository_path}/{current_year}"
            
            # Importar funções necessárias do file_processor
            from app.api.routes.file_processor import check_folder_exists, create_folder, list_files
            
            # Verificar se a pasta do ano existe
            year_folder_exists = await check_folder_exists(token, sharepoint_contratos_base_url, year_folder_path)
            
            # Criar pasta do ano se não existir
            if not year_folder_exists:
                logger.info(f"Criando pasta do ano: {year_folder_path}")
                year_folder_created = await create_folder(token, sharepoint_contratos_base_url, year_folder_path)
                
                if not year_folder_created:
                    logger.error(f"Falha ao criar pasta do ano: {year_folder_path}")
                    return {
                        "success": False,
                        "error": f"Falha ao criar pasta do ano: {year_folder_path}"
                    }
                
                logger.info(f"Pasta do ano criada com sucesso: {year_folder_path}")
            else:
                logger.info(f"Pasta do ano já existe: {year_folder_path}")
            
            # Caminho para pasta ano.mês
            year_month_folder_path = f"{year_folder_path}/{current_year_month}"
            year_month_folder_exists = await check_folder_exists(token, sharepoint_contratos_base_url, year_month_folder_path)
            
            # Criar pasta ano.mês se não existir
            if not year_month_folder_exists:
                # Criar pasta ano.mês
                logger.info(f"Criando pasta ano.mês: {year_month_folder_path}")
                year_month_folder_created = await create_folder(token, sharepoint_contratos_base_url, year_month_folder_path)
                
                if not year_month_folder_created:
                    logger.error(f"Falha ao criar pasta ano.mês: {year_month_folder_path}")
                    return {
                        "success": False,
                        "error": f"Falha ao criar pasta ano.mês: {year_month_folder_path}"
                    }
                
                logger.info(f"Pasta ano.mês criada com sucesso: {year_month_folder_path}")
            else:
                logger.info(f"Pasta ano.mês já existe: {year_month_folder_path}")
            
            # Enviar o arquivo para a pasta ano.mês
            logger.info(f"Enviando arquivo {file_name} para {year_month_folder_path}")
            
            # Verificar se o arquivo já existe na pasta
            files = await list_files(token, sharepoint_contratos_base_url, year_month_folder_path)
            existing_files = [f.get('Name') for f in files]
            
            if file_name in existing_files:
                logger.info(f"Arquivo {file_name} já existe na pasta. Gerando nome único.")
                # Adicionar timestamp ao nome do arquivo para torná-lo único
                name_parts = file_name.split('.')
                extension = name_parts[-1]
                base_name = '.'.join(name_parts[:-1])
                unique_timestamp = datetime.now().strftime('%H%M%S')
                file_name = f"{base_name}_{unique_timestamp}.{extension}"
                logger.info(f"Novo nome de arquivo: {file_name}")
            
            # Enviar o arquivo usando a URL base correta para o site de contratos
            # Precisamos criar uma função específica para enviar para o site de contratos
            # já que o método enviar_arquivo_sharepoint usa o site_url padrão
            
            # Montar a URL para upload com parâmetro de sobrescrita explícito
            url = f"{sharepoint_contratos_base_url}/_api/web/GetFolderByServerRelativeUrl('{year_month_folder_path}')/Files/add(url='{file_name}',overwrite=true)"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json;odata=verbose",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(file_content))
            }
            
            logger.info(f"URL de upload para contratos: {url}")
            
            try:
                async with aiohttp.ClientSession() as session:
                    logger.info("Iniciando requisição POST para o site de contratos")
                    async with session.post(url, headers=headers, data=file_content) as response:
                        status = response.status
                        logger.info(f"Status da resposta: {status}")
                        
                        texto = await response.text()
                        logger.info(f"Resposta: {texto[:500]}..." if len(texto) > 500 else texto)
                        
                        if status in [200, 201]:
                            logger.info(f"Upload do arquivo {file_name} concluído com sucesso para o site de contratos")
                            upload_success = True
                        else:
                            logger.error(f"Erro ao enviar arquivo {file_name} para o site de contratos. Status: {status}")
                            logger.error(f"Resposta completa: {texto}")
                            upload_success = False
            except Exception as e:
                logger.error(f"Exceção ao enviar arquivo para o site de contratos: {str(e)}")
                logger.error(traceback.format_exc())
                upload_success = False
            
            if not upload_success:
                logger.error(f"Erro ao enviar arquivo para o repositório Orange: {year_month_folder_path}")
                return {
                    "success": False,
                    "error": f"Erro ao enviar arquivo para o repositório Orange: {year_month_folder_path}"
                }
            
            logger.info(f"Arquivo enviado com sucesso para o repositório Orange: {year_month_folder_path}")
            return {
                "success": True,
                "path": year_month_folder_path,
                "file_name": file_name
            }
            
        except Exception as e:
            logger.error(f"Erro ao enviar relatório para repositório Orange: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao enviar relatório para repositório Orange: {str(e)}"
            }
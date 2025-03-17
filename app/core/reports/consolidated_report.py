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
        
    async def consolidate_reports(self):
        """
        Cria um relatório consolidado com abas para cada tipo de relatório.
        
        Returns:
            dict: Resultado da consolidação
        """
        try:
            logger.info("=== INICIANDO CRIAÇÃO DE RELATÓRIO CONSOLIDADO ===")
            
            # Cria um DataFrame vazio para cada tipo de relatório
            reports_data = {
                "Mun_Code_R189": pd.DataFrame({"Mensagem": ["Relatório não disponível"]}),
                "Divergencias_R189": pd.DataFrame({"Mensagem": ["Relatório não disponível"]}),
                "QPE_vs_R189": pd.DataFrame({"Mensagem": ["Relatório não disponível"]}),
                "SPB_vs_R189": pd.DataFrame({"Mensagem": ["Relatório não disponível"]}),
                "NFSERV_vs_R189": pd.DataFrame({"Mensagem": ["Relatório não disponível"]})
            }
            
            # Lista de arquivos para buscar
            specific_files = [
                {
                    "folder": "MUN_CODE",
                    "sheet_name": "Mun_Code_R189",
                    "filenames": [
                        "report_mun_code_r189_20250317_165659.xlsx",
                        "report_mun_code_r189_20250316_165659.xlsx",
                        "report_mun_code_r189_20250315_165659.xlsx"
                    ]
                },
                {
                    "folder": "R189",
                    "sheet_name": "Divergencias_R189",
                    "filenames": [
                        "report_divergencias_r189_20250317_165704.xlsx",
                        "report_divergencias_r189_20250316_165704.xlsx",
                        "report_divergencias_r189_20250315_165704.xlsx"
                    ]
                },
                {
                    "folder": "QPE_R189",
                    "sheet_name": "QPE_vs_R189",
                    "filenames": [
                        "20250317_165720_divergencias_qpe_r189.xlsx",
                        "20250316_165720_divergencias_qpe_r189.xlsx",
                        "20250315_165720_divergencias_qpe_r189.xlsx"
                    ]
                },
                {
                    "folder": "SPO_R189",
                    "sheet_name": "SPB_vs_R189",
                    "filenames": [
                        "report_divergencias_spb_r189_20250317_165714.xlsx",
                        "report_divergencias_spb_r189_20250316_165714.xlsx",
                        "report_divergencias_spb_r189_20250315_165714.xlsx"
                    ]
                },
                {
                    "folder": "NFSERV_R189",
                    "sheet_name": "NFSERV_vs_R189",
                    "filenames": [
                        "20250317_165724_divergencias_nfserv_r189.xlsx",
                        "20250316_165724_divergencias_nfserv_r189.xlsx",
                        "20250315_165724_divergencias_nfserv_r189.xlsx"
                    ]
                }
            ]
            
            # Hoje e dias anteriores
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            two_days_ago = today - timedelta(days=2)
            
            # Datas formatadas
            dates = [
                today.strftime('%Y%m%d'),
                yesterday.strftime('%Y%m%d'),
                two_days_ago.strftime('%Y%m%d')
            ]
            
            # Adiciona arquivos com datas atuais
            for file_info in specific_files:
                # Gera nomes atualizados baseados na data atual
                if "filenames" in file_info:
                    base_filename = file_info["filenames"][0]
                    current_filenames = []
                    
                    # Para cada data, gera um nome de arquivo
                    for date in dates:
                        if "_20" in base_filename:  # Contém data no formato _YYYYMMDD_
                            parts = base_filename.split("_20")
                            if len(parts) >= 2:
                                # Reconstrói com a nova data
                                new_filename = f"{parts[0]}_20{date}{parts[1][8:]}"
                                current_filenames.append(new_filename)
                    
                    # Adiciona os nomes gerados à lista
                    file_info["filenames"].extend(current_filenames)
            
            # Contador de relatórios encontrados
            found_reports = 0
            
            # Para cada tipo de arquivo
            for file_info in specific_files:
                folder = file_info["folder"]
                sheet_name = file_info["sheet_name"]
                filenames = file_info["filenames"]
                
                folder_path = f"{self.relatorios_base_path}/{folder}"
                logger.info(f"Buscando arquivos na pasta {folder_path}")
                
                # Tenta cada nome de arquivo na lista
                for filename in filenames:
                    logger.info(f"Tentando baixar arquivo {filename}")
                    
                    # Tenta baixar o arquivo
                    file_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                        filename,
                        folder_path
                    )
                    
                    # Se conseguiu baixar o arquivo
                    if file_content is not None:
                        try:
                            # Lê o arquivo Excel
                            df = pd.read_excel(BytesIO(file_content))
                            
                            # Se o DataFrame não estiver vazio
                            if not df.empty:
                                reports_data[sheet_name] = df
                                found_reports += 1
                                logger.info(f"Arquivo {filename} lido com sucesso: {len(df)} linhas")
                                break  # Encontrou um arquivo válido, sai do loop
                        except Exception as e:
                            logger.error(f"Erro ao ler arquivo {filename}: {str(e)}")
                    else:
                        logger.warning(f"Arquivo {filename} não encontrado")
            
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
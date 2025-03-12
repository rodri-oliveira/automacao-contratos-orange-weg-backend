import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
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
            
            # Lista de arquivos específicos para tentar baixar (baseado nos exemplos fornecidos)
            specific_files = [
                {
                    "folder": "MUN_CODE",
                    "sheet_name": "Mun_Code_R189",
                    "filename": "report_mun_code_r189_20250312_102552.xlsx"
                },
                {
                    "folder": "R189",
                    "sheet_name": "Divergencias_R189",
                    "filename": "report_divergencias_r189_20250312_092310.xlsx"
                },
                {
                    "folder": "QPE_R189",
                    "sheet_name": "QPE_vs_R189",
                    "filename": "20250312_092337_divergencias_qpe_r189.xlsx"
                },
                {
                    "folder": "SPO_R189",
                    "sheet_name": "SPB_vs_R189",
                    "filename": "report_divergencias_spb_r189_20250312_093327.xlsx"
                },
                {
                    "folder": "NFSERV_R189",
                    "sheet_name": "NFSERV_vs_R189",
                    "filename": "20250312_094849_divergencias_nfserv_r189.xlsx"
                }
            ]
            
            # Contador de relatórios encontrados
            found_reports = 0
            
            # Para cada arquivo específico, tenta baixá-lo
            for file_info in specific_files:
                folder = file_info["folder"]
                sheet_name = file_info["sheet_name"]
                filename = file_info["filename"]
                folder_path = f"{self.relatorios_base_path}/{folder}"
                
                logger.info(f"Tentando baixar arquivo {filename} da pasta {folder_path}")
                
                # Tenta baixar o arquivo
                file_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                    filename,
                    folder_path
                )
                
                # Se conseguiu baixar o arquivo, lê o conteúdo
                if file_content is not None:
                    try:
                        # Lê o arquivo Excel
                        df = pd.read_excel(BytesIO(file_content))
                        
                        # Se o DataFrame não estiver vazio, armazena-o
                        if not df.empty:
                            reports_data[sheet_name] = df
                            found_reports += 1
                            logger.info(f"Arquivo {filename} lido com sucesso: {len(df)} linhas")
                    except Exception as e:
                        logger.error(f"Erro ao ler arquivo {filename}: {str(e)}")
                else:
                    logger.warning(f"Arquivo {filename} não encontrado na pasta {folder_path}")
            
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
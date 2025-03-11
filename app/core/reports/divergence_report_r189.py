from typing import Dict, Any, Tuple, List
import pandas as pd
from io import BytesIO
from datetime import datetime
import logging
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient
import aiohttp
import traceback

# Configurar logger
logger = logging.getLogger(__name__)

class DivergenceReportR189:
    """
    Classe responsável por verificar divergências no arquivo R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        
        # Mapeamento de CNPJ para Site Name esperado
        self.cnpj_site_mapping = {
            "60.621.141/0005-87": ["PMAR_BRCSA"],
            "07.175.725/0030-02": ["WEL_BRGCV"],
            "60.621.141/0006-68": ["PMAR_BRMUA"],
            "07.175.725/0010-50": ["WEL_BRJGS"],
            "10.885.321/0001-74": ["WLI_BRLNH"],
            "84.584.994/0007-16": ["WTB_BRSZO"],
            "07.175.725/0042-38": ["WEL_BRBTI"],
            "14.759.173/0001-00": ["WCES_BRMTT"],
            "14.759.173/0002-83": ["WCES_BRBGV"],
            "07.175.725/0024-56": ["WEL_BRRPO"],
            "07.175.725/0014-84": ["WEL_BRBNU"],
            "13.772.125/0007-77": ["RF_BRCOR"],
            "07.175.725/0004-02": ["WEL_BRITJ"],
            "60.621.141/0004-04": ["PMAR_BRGRM"],
            "07.175.725/0021-03": ["WEL_BRSBC"],
            "07.175.725/0026-18": ["WEL_BRSPO"]
        }
        
        # Lista de possíveis nomes para a coluna de total
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera']

    async def check_divergences(self, consolidated_data: pd.DataFrame) -> tuple[bool, str, pd.DataFrame]:
        """
        Verifica divergências entre os dados consolidados e o mapeamento esperado.
        
        Args:
            consolidated_data: DataFrame com os dados consolidados do R189
            
        Returns:
            tuple: (sucesso, mensagem, DataFrame com divergências)
        """
        try:
            logger.info("Iniciando verificação de divergências no R189")
            
            # Validação inicial do DataFrame
            if consolidated_data is None:
                logger.error("DataFrame não pode ser None")
                return False, "Erro: DataFrame não pode ser None", pd.DataFrame()
                
            if consolidated_data.empty:
                logger.error("DataFrame está vazio")
                return False, "Erro: DataFrame está vazio", pd.DataFrame()
            
            logger.info(f"DataFrame recebido com {len(consolidated_data)} linhas e {len(consolidated_data.columns)} colunas")
            logger.info(f"Colunas disponíveis: {consolidated_data.columns.tolist()}")
            
            divergences = []
            
            # Verifica qual coluna de total está presente no DataFrame
            coluna_total_encontrada = None
            for col in self.colunas_total:
                if col in consolidated_data.columns:
                    coluna_total_encontrada = col
                    logger.info(f"Coluna de total encontrada: {coluna_total_encontrada}")
                    break
                    
            if not coluna_total_encontrada:
                logger.error(f"Nenhuma das colunas de total foi encontrada. Esperado: {self.colunas_total}")
                return False, f"Erro: Nenhuma das colunas de total foi encontrada. Esperado uma das seguintes: {self.colunas_total}", pd.DataFrame()
            
            # Verifica se as colunas necessárias existem
            required_columns = ['CNPJ - WEG', 'Site Name - WEG 2', 'Invoice number', coluna_total_encontrada]
            missing_columns = [col for col in required_columns if col not in consolidated_data.columns]
            if missing_columns:
                logger.error(f"Colunas necessárias não encontradas: {missing_columns}")
                return False, f"Erro: Colunas necessárias não encontradas: {', '.join(missing_columns)}", pd.DataFrame()
            
            # Validação de tipos de dados
            try:
                logger.info(f"Convertendo coluna '{coluna_total_encontrada}' para numérico")
                consolidated_data[coluna_total_encontrada] = pd.to_numeric(consolidated_data[coluna_total_encontrada], errors='coerce')
            except Exception as e:
                logger.error(f"Erro ao converter valores da coluna '{coluna_total_encontrada}': {str(e)}")
                return False, f"Erro: Valores inválidos na coluna '{coluna_total_encontrada}': {str(e)}", pd.DataFrame()
            
            # Verifica valores nulos
            null_cnpj = consolidated_data['CNPJ - WEG'].isnull().sum()
            null_site = consolidated_data['Site Name - WEG 2'].isnull().sum()
            null_invoice = consolidated_data['Invoice number'].isnull().sum()
            null_total = consolidated_data[coluna_total_encontrada].isnull().sum()
            
            logger.info(f"Valores nulos encontrados - CNPJ: {null_cnpj}, Site Name: {null_site}, Invoice: {null_invoice}, Total: {null_total}")
            
            if any([null_cnpj, null_site, null_invoice, null_total]):
                logger.error("Encontrados valores nulos nas colunas obrigatórias")
                return False, (
                    "Erro: Encontrados valores nulos:\n"
                    f"CNPJ: {null_cnpj} valores nulos\n"
                    f"Site Name: {null_site} valores nulos\n"
                    f"Invoice: {null_invoice} valores nulos\n"
                    f"{coluna_total_encontrada}: {null_total} valores nulos"
                ), pd.DataFrame()
            
            # Itera sobre cada linha do DataFrame
            logger.info("Iniciando verificação linha a linha")
            for idx, row in consolidated_data.iterrows():
                cnpj = str(row['CNPJ - WEG']).strip()
                site_name = str(row['Site Name - WEG 2']).strip()
                invoice = str(row['Invoice number']).strip()
                valor = float(row[coluna_total_encontrada])
                
                # Validação do CNPJ
                if not cnpj or len(cnpj) != 18:  # Formato XX.XXX.XXX/XXXX-XX
                    logger.warning(f"CNPJ inválido encontrado: {cnpj}")
                    divergences.append({
                        'Tipo': 'CNPJ inválido',
                        'Invoice Number': invoice,
                        'CNPJ': cnpj,
                        'Site Name Encontrado': site_name,
                        'Site Name Esperado': 'CNPJ em formato inválido',
                        'Total Geral': valor
                    })
                    continue
                
                # Validação do Site Name
                if not site_name:
                    logger.warning(f"Site Name vazio para CNPJ: {cnpj}, Invoice: {invoice}")
                    divergences.append({
                        'Tipo': 'Site Name vazio',
                        'Invoice Number': invoice,
                        'CNPJ': cnpj,
                        'Site Name Encontrado': 'VAZIO',
                        'Site Name Esperado': 'Site Name não pode ser vazio',
                        'Total Geral': valor
                    })
                    continue
                
                # Verifica se o CNPJ existe no mapeamento
                if cnpj in self.cnpj_site_mapping:
                    # Verifica se o Site Name está correto
                    if site_name not in self.cnpj_site_mapping[cnpj]:
                        logger.warning(f"Site Name incorreto para CNPJ: {cnpj}, Encontrado: {site_name}, Esperado: {self.cnpj_site_mapping[cnpj]}")
                        divergences.append({
                            'Tipo': 'Site Name incorreto',
                            'Invoice Number': invoice,
                            'CNPJ': cnpj,
                            'Site Name Encontrado': site_name,
                            'Site Name Esperado': ', '.join(self.cnpj_site_mapping[cnpj]),
                            'Total Geral': valor
                        })
                else:
                    logger.warning(f"CNPJ não mapeado: {cnpj}")
                    divergences.append({
                        'Tipo': 'CNPJ não mapeado',
                        'Invoice Number': invoice,
                        'CNPJ': cnpj,
                        'Site Name Encontrado': site_name,
                        'Site Name Esperado': 'CNPJ não cadastrado',
                        'Total Geral': valor
                    })
            
            if divergences:
                df_divergences = pd.DataFrame(divergences)
                logger.info(f"Encontradas {len(divergences)} divergências")
                logger.info(f"Resumo por tipo: {df_divergences['Tipo'].value_counts().to_dict()}")
                return True, f"Encontradas {len(divergences)} divergências:\n" + \
                           f"- {df_divergences['Tipo'].value_counts().to_string()}", df_divergences
            
            logger.info("Nenhuma divergência encontrada nos dados analisados")
            return True, "Nenhuma divergência encontrada nos dados analisados", pd.DataFrame()
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao verificar divergências: {str(e)}")
            return False, f"Erro inesperado ao verificar divergências: {str(e)}\n" + \
                         "Por favor, verifique se o arquivo está no formato correto.", pd.DataFrame()

    async def generate_excel_report(self, divergences_df: pd.DataFrame) -> dict:
        """
        Gera um relatório Excel com as divergências encontradas.
        
        Args:
            divergences_df: DataFrame com as divergências encontradas
            
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("Iniciando geração do relatório Excel")
            
            if divergences_df is None:
                logger.error("DataFrame de divergências é None")
                return {"success": False, "error": "DataFrame de divergências é None"}
                
            if divergences_df.empty:
                logger.info("Nenhuma divergência para gerar relatório")
                return {"success": True, "message": "Nenhuma divergência para gerar relatório"}
            
            # Validação das colunas necessárias
            required_columns = ['Tipo', 'Invoice Number', 'CNPJ', 'Site Name Encontrado', 'Site Name Esperado', 'Total Geral']
            missing_columns = [col for col in required_columns if col not in divergences_df.columns]
            if missing_columns:
                logger.error(f"Colunas necessárias não encontradas: {missing_columns}")
                return {"success": False, "error": f"Colunas necessárias não encontradas: {', '.join(missing_columns)}"}
            
            # Adiciona data e hora ao DataFrame
            now = datetime.now()
            divergences_df['Data Verificação'] = now.strftime('%Y-%m-%d')
            divergences_df['Hora Verificação'] = now.strftime('%H:%M:%S')
            
            try:
                logger.info("Criando arquivo Excel na memória")
                # Cria o arquivo Excel na memória
                excel_file = BytesIO()
                with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
                    divergences_df.to_excel(writer, index=False, sheet_name='Divergencias_R189')
                    
                    # Ajusta a largura das colunas
                    worksheet = writer.sheets['Divergencias_R189']
                    for i, col in enumerate(divergences_df.columns):
                        max_length = max(
                            divergences_df[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.set_column(i, i, max_length + 2)
                
                excel_file.seek(0)
                logger.info("Arquivo Excel criado com sucesso")
                
                # Nome do arquivo com timestamp no início
                filename = f"report_divergencias_r189_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                return {
                    "success": True,
                    "file_content": excel_file,
                    "filename": filename
                }
                
            except Exception as e:
                logger.exception(f"Erro ao criar arquivo Excel: {str(e)}")
                return {"success": False, "error": f"Erro ao criar arquivo Excel: {str(e)}"}
                
        except Exception as e:
            logger.exception(f"Erro inesperado ao gerar relatório Excel: {str(e)}")
            return {"success": False, "error": f"Erro inesperado ao gerar relatório Excel: {str(e)}"}

    async def generate_report(self):
        """
        Gera o relatório de divergências a partir do arquivo consolidado.
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO DE DIVERGÊNCIAS R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca o arquivo consolidado no SharePoint
            logger.info("Baixando arquivo R189_consolidado.xlsx")
            r189_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'R189_consolidado.xlsx',
                consolidado_path
            )
            
            if not r189_content:
                logger.error("Não foi possível baixar o arquivo R189_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo R189_consolidado.xlsx",
                    "show_popup": True
                }
            
            # Lê o arquivo em DataFrame
            logger.info("Lendo arquivo Excel")
            try:
                r189_io = BytesIO(r189_content)
                df = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                logger.info(f"Arquivo lido com {len(df)} linhas")
            except Exception as e:
                logger.error(f"Erro ao ler arquivo Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivo Excel: {str(e)}",
                    "show_popup": True
                }
            
            # Verifica divergências
            success, message, divergences_df = await self.check_divergences(df)
            
            if not success:
                logger.error(f"Erro na verificação: {message}")
                return {
                    "success": False,
                    "error": message,
                    "show_popup": True
                }
            
            # Se encontrou divergências, gera o relatório Excel
            if not divergences_df.empty:
                logger.info(f"Gerando relatório Excel com {len(divergences_df)} divergências")
                
                # Adiciona data e hora ao DataFrame
                now = datetime.now()
                divergences_df['Data Verificação'] = now.strftime('%Y-%m-%d')
                divergences_df['Hora Verificação'] = now.strftime('%H:%M:%S')
                
                # Cria o arquivo Excel na memória
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    divergences_df.to_excel(writer, index=False, sheet_name='Divergencias_R189')
                    
                    # Ajusta a largura das colunas
                    workbook = writer.book
                    worksheet = writer.sheets['Divergencias_R189']
                    for i, col in enumerate(divergences_df.columns):
                        max_length = max(
                            divergences_df[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.set_column(i, i, max_length + 2)
                
                output.seek(0)
                
                # Nome do arquivo com timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_filename = f'report_divergencias_r189_{timestamp}.xlsx'
                
                # Envia o relatório para o SharePoint
                logger.info(f"Enviando relatório {report_filename} para o SharePoint")
                relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/R189"
                
                # Usar o método assíncrono do SharePointAuth
                upload_success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    conteudo=output.getvalue(),
                    nome_arquivo=report_filename,
                    pasta=relatorios_path
                )
                
                if not upload_success:
                    logger.error("Erro ao enviar relatório para o SharePoint")
                    return {
                        "success": False,
                        "error": "Erro ao enviar relatório para o SharePoint",
                        "show_popup": True
                    }
                
                logger.info("Relatório enviado com sucesso")
                return {
                    "success": True,
                    "message": f"Relatório de divergências gerado e salvo com sucesso!\n\nResumo das divergências encontradas:\n{message}\n\nO arquivo foi salvo na pasta RELATÓRIOS/R189 no SharePoint.",
                    "show_popup": True
                }
            
            logger.info("Nenhuma divergência encontrada, não é necessário gerar relatório")
            return {
                "success": True,
                "message": "Validação concluída. Nenhuma divergência encontrada.",
                "show_popup": True
            }
            
        except Exception as e:
            logger.error(f"Erro inesperado ao gerar relatório: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro inesperado ao gerar relatório: {str(e)}",
                "show_popup": True
            }

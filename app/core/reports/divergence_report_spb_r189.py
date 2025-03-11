from typing import Dict, Any, List, Tuple
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
import traceback
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class DivergenceReportSPBR189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados SPB e R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        # Lista de possíveis nomes para a coluna de total
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera', 'Total', 'Valor Total']

    async def check_divergences(self, spb_data: pd.DataFrame, r189_data: pd.DataFrame, nfserv_data: pd.DataFrame) -> Tuple[bool, str, pd.DataFrame]:
        """
        Verifica divergências entre os dados consolidados do SPB e R189.
        
        Args:
            spb_data: DataFrame com os dados consolidados do SPB
            r189_data: DataFrame com os dados consolidados do R189
            nfserv_data: DataFrame com os dados consolidados do NFSERV
            
        Returns:
            tuple: (sucesso, mensagem, DataFrame com divergências)
        """
        try:
            logger.info("Iniciando verificação de divergências entre SPB, NFSERV e R189")
            
            # Validação inicial dos DataFrames
            if spb_data is None or r189_data is None or nfserv_data is None:
                logger.error("DataFrames não podem ser None")
                return False, "Erro: DataFrames não podem ser None", pd.DataFrame()
                
            if spb_data.empty or r189_data.empty or nfserv_data.empty:
                logger.error("DataFrames não podem estar vazios")
                return False, "Erro: DataFrames não podem estar vazios", pd.DataFrame()
            
            logger.info(f"SPB: {len(spb_data)} linhas, R189: {len(r189_data)} linhas, NFSERV: {len(nfserv_data)} linhas")
            
            # Verifica qual coluna de total está presente no DataFrame do R189
            coluna_total_encontrada = None
            for col in self.colunas_total:
                if col in r189_data.columns:
                    coluna_total_encontrada = col
                    logger.info(f"Coluna de total encontrada no R189: {col}")
                    break
                    
            if not coluna_total_encontrada:
                logger.error(f"Nenhuma das colunas de total foi encontrada no R189: {self.colunas_total}")
                return False, f"Erro: Nenhuma das colunas de total foi encontrada no R189. Esperado uma das seguintes: {self.colunas_total}", pd.DataFrame()
            
            # Verifica se as colunas necessárias existem no R189
            r189_required = ['Invoice number', 'CNPJ - WEG', coluna_total_encontrada]
            missing_r189 = [col for col in r189_required if col not in r189_data.columns]
            if missing_r189:
                logger.error(f"Colunas necessárias não encontradas no R189: {missing_r189}")
                return False, f"Erro: Colunas necessárias não encontradas no R189: {', '.join(missing_r189)}", pd.DataFrame()
            
            # Validação de tipos de dados
            try:
                logger.info("Convertendo colunas de valor para numérico")
                spb_data['VALOR_TOTAL'] = pd.to_numeric(spb_data['VALOR_TOTAL'].astype(str).str.replace(',', '.'), errors='coerce')
                nfserv_data['VALOR_TOTAL'] = pd.to_numeric(nfserv_data['VALOR_TOTAL'].astype(str).str.replace(',', '.'), errors='coerce')
                r189_data[coluna_total_encontrada] = pd.to_numeric(r189_data[coluna_total_encontrada].astype(str).str.replace(',', '.'), errors='coerce')
            except Exception as e:
                logger.error(f"Erro ao converter valores: {str(e)}")
                return False, f"Erro: Valores inválidos nas colunas de valor: {str(e)}", pd.DataFrame()
            
            divergences = []
            
            # Contagem de SPB_ID do SPB_consolidado
            spb_ids = set(spb_data['SPB_ID'].unique())
            qtd_spb = len(spb_ids)
            
            # Contagem de SPB no NFSERV (procurando SPB no NFSERV_ID)
            nfserv_spb_ids = set(nfserv_data[nfserv_data['NFSERV_ID'].str.contains('SPB', na=False)]['NFSERV_ID'].unique())
            qtd_nfserv_spb = len(nfserv_spb_ids)
            
            # Contagem de SPB no R189
            r189_spb_ids = set(r189_data[r189_data['Invoice number'].str.contains('SPB', na=False)]['Invoice number'].unique())
            qtd_r189_spb = len(r189_spb_ids)
            
            logger.info(f"Contagem - SPB: {qtd_spb}, NFSERV SPB: {qtd_nfserv_spb}, R189 SPB: {qtd_r189_spb}")
            
            # Adiciona informação de quantidade ao início do relatório
            if (qtd_spb + qtd_nfserv_spb) != qtd_r189_spb:
                logger.warning(f"Divergência na contagem de SPB: SPB+NFSERV={qtd_spb + qtd_nfserv_spb}, R189={qtd_r189_spb}")
                divergences.append({
                    'Tipo': 'CONTAGEM_SPB',
                    'SPB_ID': 'N/A',
                    'CNPJ SPB': 'N/A',
                    'CNPJ R189': 'N/A',
                    'Valor SPB': qtd_spb + qtd_nfserv_spb,
                    'Valor R189': qtd_r189_spb,
                    'Detalhes': f'SPB: {qtd_spb}, NFSERV: {qtd_nfserv_spb}, R189: {qtd_r189_spb}'
                })
            
            # IDs que estão no R189 mas não em nenhum dos consolidados
            ids_r189_nao_encontrados = r189_spb_ids - (spb_ids.union(nfserv_spb_ids))
            logger.info(f"IDs encontrados apenas no R189: {len(ids_r189_nao_encontrados)}")
            
            for spb_id in ids_r189_nao_encontrados:
                r189_row = r189_data[r189_data['Invoice number'] == spb_id].iloc[0]
                divergences.append({
                    'Tipo': 'ID encontrado apenas no R189',
                    'SPB_ID': spb_id,
                    'CNPJ SPB': 'N/A',
                    'CNPJ R189': r189_row['CNPJ - WEG'],
                    'Valor SPB': 'N/A',
                    'Valor R189': r189_row[coluna_total_encontrada]
                })
            
            # IDs que estão nos consolidados mas não no R189
            todos_spb_ids = spb_ids.union(nfserv_spb_ids)
            ids_faltando_r189 = todos_spb_ids - r189_spb_ids
            logger.info(f"IDs não encontrados no R189: {len(ids_faltando_r189)}")
            
            for spb_id in ids_faltando_r189:
                # Procura primeiro no SPB_consolidado
                spb_row = spb_data[spb_data['SPB_ID'] == spb_id]
                if not spb_row.empty:
                    row = spb_row.iloc[0]
                    origem = "SPB"
                    cnpj = row['CNPJ']
                    valor = row['VALOR_TOTAL']
                else:
                    # Se não encontrou, procura no NFSERV
                    nfserv_row = nfserv_data[nfserv_data['NFSERV_ID'] == spb_id]
                    if nfserv_row.empty:
                        logger.warning(f"ID {spb_id} não encontrado nem no SPB nem no NFSERV")
                        continue
                    row = nfserv_row.iloc[0]
                    origem = "NFSERV"
                    cnpj = row['CNPJ']
                    valor = row['VALOR_TOTAL']
                
                divergences.append({
                    'Tipo': f'ID do {origem} não encontrado no R189',
                    'SPB_ID': spb_id,
                    'CNPJ SPB': cnpj,
                    'CNPJ R189': 'N/A',
                    'Valor SPB': valor,
                    'Valor R189': 'N/A'
                })
            
            # Verifica divergências de CNPJ e valor para IDs que existem em ambos
            ids_em_ambos = r189_spb_ids.intersection(todos_spb_ids)
            logger.info(f"IDs presentes em ambos os sistemas: {len(ids_em_ambos)}")
            
            for spb_id in ids_em_ambos:
                r189_rows = r189_data[r189_data['Invoice number'] == spb_id]
                if r189_rows.empty:
                    logger.warning(f"ID {spb_id} não encontrado no R189 (inconsistência)")
                    continue
                
                r189_row = r189_rows.iloc[0]
                
                # Procura primeiro no SPB_consolidado
                spb_row = spb_data[spb_data['SPB_ID'] == spb_id]
                if not spb_row.empty:
                    row = spb_row.iloc[0]
                    origem = "SPB"
                else:
                    # Se não encontrou, procura no NFSERV
                    nfserv_row = nfserv_data[nfserv_data['NFSERV_ID'] == spb_id]
                    if nfserv_row.empty:
                        logger.warning(f"ID {spb_id} não encontrado nem no SPB nem no NFSERV (inconsistência)")
                        continue
                    row = nfserv_row.iloc[0]
                    origem = "NFSERV"
                
                # Verifica CNPJ
                if row['CNPJ'] != r189_row['CNPJ - WEG']:
                    logger.warning(f"CNPJ divergente para {spb_id}: {origem}={row['CNPJ']}, R189={r189_row['CNPJ - WEG']}")
                    divergences.append({
                        'Tipo': 'CNPJ divergente',
                        'SPB_ID': spb_id,
                        'CNPJ SPB': row['CNPJ'],
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor SPB': row['VALOR_TOTAL'],
                        'Valor R189': r189_row[coluna_total_encontrada]
                    })
                
                # Verifica valor
                valor_spb = round(float(row['VALOR_TOTAL']), 2)
                valor_r189 = round(float(r189_row[coluna_total_encontrada]), 2)
                if abs(valor_spb - valor_r189) > 0.01:  # Tolerância de 1 centavo
                    logger.warning(f"Valor divergente para {spb_id}: {origem}={valor_spb}, R189={valor_r189}")
                    divergences.append({
                        'Tipo': 'Valor divergente',
                        'SPB_ID': spb_id,
                        'CNPJ SPB': row['CNPJ'],
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor SPB': row['VALOR_TOTAL'],
                        'Valor R189': r189_row[coluna_total_encontrada]
                    })
            
            if divergences:
                df_divergences = pd.DataFrame(divergences)
                logger.info(f"Encontradas {len(divergences)} divergências")
                logger.info(f"Resumo por tipo: {df_divergences['Tipo'].value_counts().to_dict()}")
                return True, f"Encontradas {len(divergences)} divergências:\n" + \
                           f"- {df_divergences['Tipo'].value_counts().to_string()}", df_divergences
            
            logger.info("Nenhuma divergência encontrada")
            return True, "Nenhuma divergência encontrada nos dados analisados", pd.DataFrame()
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao verificar divergências: {str(e)}")
            return False, f"Erro inesperado ao verificar divergências: {str(e)}\n" + \
                         "Por favor, verifique se os arquivos estão no formato correto.", pd.DataFrame()

    async def generate_excel_report(self, divergences_df):
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
                return {"success": False, "error": "DataFrame de divergências é None"}
            
            if divergences_df.empty:
                return {"success": True, "message": "Nenhuma divergência para gerar relatório"}
            
            # Validação das colunas necessárias
            required_columns = ['Tipo', 'SPB_ID', 'CNPJ SPB', 'CNPJ R189', 'Valor SPB', 'Valor R189']
            missing_columns = [col for col in required_columns if col not in divergences_df.columns]
            if missing_columns:
                return {"success": False, "error": f"Colunas necessárias não encontradas: {', '.join(missing_columns)}"}
            
            # Adiciona data e hora ao DataFrame
            now = datetime.now()
            divergences_df['Data Verificação'] = now.strftime('%Y-%m-%d')
            divergences_df['Hora Verificação'] = now.strftime('%H:%M:%S')
            
            try:
                logger.info("Criando arquivo Excel na memória")
                # Cria o arquivo Excel na memória
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    divergences_df.to_excel(writer, index=False, sheet_name='Divergencias_SPB_R189')
                    
                    # Ajusta a largura das colunas
                    workbook = writer.book
                    worksheet = writer.sheets['Divergencias_SPB_R189']
                    for i, col in enumerate(divergences_df.columns):
                        max_length = max(
                            divergences_df[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.set_column(i, i, max_length + 2)
                
                output.seek(0)
                logger.info("Arquivo Excel criado com sucesso")
                
                # Nome do arquivo com timestamp
                timestamp = now.strftime('%Y%m%d_%H%M%S')
                report_name = f'report_divergencias_spb_r189_{timestamp}.xlsx'
                
                return {
                    "success": True,
                    "file_content": output,
                    "filename": report_name
                }
            except Exception as e:
                logger.exception(f"Erro ao criar arquivo Excel: {str(e)}")
                return {"success": False, "error": f"Erro ao criar arquivo Excel: {str(e)}"}
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao gerar relatório Excel: {str(e)}")
            return {"success": False, "error": f"Erro inesperado ao gerar relatório Excel: {str(e)}"}

    async def generate_report(self):
        """
        Gera o relatório de divergências comparando SPB e R189.
        
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO SPB vs R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca os arquivos consolidados no SharePoint
            logger.info("Baixando arquivo SPB_consolidado.xlsx")
            spb_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'SPB_consolidado.xlsx',
                consolidado_path
            )
            
            if spb_content is None:
                logger.error("Não foi possível baixar o arquivo SPB_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo SPB_consolidado.xlsx",
                    "show_popup": True
                }
            
            logger.info("Baixando arquivo R189_consolidado.xlsx")
            r189_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'R189_consolidado.xlsx',
                consolidado_path
            )
            
            if r189_content is None:
                logger.error("Não foi possível baixar o arquivo R189_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo R189_consolidado.xlsx",
                    "show_popup": True
                }
                
            logger.info("Baixando arquivo NFSERV_consolidado.xlsx")
            nfserv_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'NFSERV_consolidado.xlsx',
                consolidado_path
            )
            
            if nfserv_content is None:
                logger.error("Não foi possível baixar o arquivo NFSERV_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo NFSERV_consolidado.xlsx",
                    "show_popup": True
                }
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos Excel")
            try:
                spb_io = BytesIO(spb_content)
                r189_io = BytesIO(r189_content)
                nfserv_io = BytesIO(nfserv_content)
                
                df_spb = pd.read_excel(spb_io, sheet_name='Consolidado_SPB')
                df_r189 = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                df_nfserv = pd.read_excel(nfserv_io, sheet_name='Consolidado_NFSERV')
                
                logger.info(f"Linhas em SPB: {len(df_spb)}")
                logger.info(f"Linhas em R189: {len(df_r189)}")
                logger.info(f"Linhas em NFSERV: {len(df_nfserv)}")
            except Exception as e:
                logger.error(f"Erro ao ler arquivos Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos Excel: {str(e)}",
                    "show_popup": True
                }
            
            if df_spb.empty:
                logger.error("Arquivo SPB_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo SPB_consolidado.xlsx está vazio",
                    "show_popup": True
                }
                
            if df_r189.empty:
                logger.error("Arquivo R189_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo R189_consolidado.xlsx está vazio",
                    "show_popup": True
                }
                
            if df_nfserv.empty:
                logger.error("Arquivo NFSERV_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo NFSERV_consolidado.xlsx está vazio",
                    "show_popup": True
                }
            
            # Verifica divergências
            logger.info("Verificando divergências")
            success, message, divergences_df = await self.check_divergences(df_spb, df_r189, df_nfserv)
            
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
                report_result = await self.generate_excel_report(divergences_df)
                
                if not report_result.get("success", False):
                    error_msg = report_result.get("error", "Erro desconhecido ao gerar relatório")
                    logger.error(f"Erro ao gerar relatório: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "show_popup": True
                    }
                
                # Nome do arquivo de relatório
                report_filename = report_result.get("filename")
                if not report_filename:
                    logger.error("Nome do arquivo de relatório não encontrado no resultado")
                    return {
                        "success": False,
                        "error": "Nome do arquivo de relatório não encontrado",
                        "show_popup": True
                    }
                
                file_content = report_result.get("file_content")
                if not file_content:
                    logger.error("Conteúdo do arquivo de relatório não encontrado no resultado")
                    return {
                        "success": False,
                        "error": "Conteúdo do arquivo de relatório não encontrado",
                        "show_popup": True
                    }
                
                # Envia o relatório para o SharePoint
                logger.info(f"Enviando relatório {report_filename} para o SharePoint")
                relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/SPO_R189"
                
                # Usar o método assíncrono do SharePointAuth
                upload_success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    conteudo=file_content.getvalue(),
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
                    "message": f"Relatório de divergências gerado e salvo com sucesso!\n\nResumo das divergências encontradas:\n{message}\n\nO arquivo foi salvo na pasta RELATÓRIOS/SPO_R189 no SharePoint.",
                    "show_popup": True
                }
            
            logger.info("Nenhuma divergência encontrada, não é necessário gerar relatório")
            return {
                "success": True,
                "message": message,
                "show_popup": True
            }

        except Exception as e:
            logger.exception(f"Erro inesperado ao gerar relatório: {str(e)}")
            return {
                "success": False,
                "error": f"Erro inesperado ao gerar relatório: {str(e)}\nPor favor, verifique:\n1. Se os arquivos consolidados existem no SharePoint\n2. Se você tem permissão de acesso\n3. Se a conexão com o SharePoint está funcionando",
                "show_popup": True
            }

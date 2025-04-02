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
            
            # Verificação para Invoice Type
            if 'Invoice Type' not in r189_data.columns:
                logger.warning("Coluna 'Invoice Type' não encontrada no R189. Esta coluna é necessária para comparação correta.")
                r189_data['Invoice Type'] = None  # Adiciona coluna vazia para evitar erros
            
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
            
            # NOVA LÓGICA: Filtrar apenas SPBs com Type=SRV no R189
            logger.info("Filtrando SPBs com Type=SRV no R189")
            
            # Filtrar SPBs no R189 com base no Invoice Type
            spb_srv_mask = (r189_data['Invoice number'].str.contains('SPB', na=False)) & (r189_data['Invoice Type'] == 'SRV')
            
            # Obter conjunto de IDs para SPBs com SRV
            r189_spb_srv_ids = set(r189_data[spb_srv_mask]['Invoice number'].unique())
            
            # Contar SPBs com SRV
            qtd_spb_srv = len(r189_spb_srv_ids)
            
            logger.info(f"SPBs no R189 com Type=SRV: {qtd_spb_srv}")
            
            # Contagem de SPB_ID do SPB_consolidado
            spb_ids = set(spb_data['SPB_ID'].unique())
            qtd_spb = len(spb_ids)
            
            logger.info(f"SPBs no consolidado SPB: {qtd_spb}")
            
            # Adiciona informação de contagem SPB com SRV (para SPB consolidado)
            divergences.append({
                'Tipo': 'CONTAGEM_SPB_SRV',
                'SPB_ID': 'N/A',
                'CNPJ SPB': 'N/A',
                'CNPJ R189': 'N/A',
                'Valor SPB': qtd_spb,
                'Valor R189': qtd_spb_srv,
                'Detalhes': f'SPB consolidado: {qtd_spb}, R189 com Type=SRV: {qtd_spb_srv}'
            })
            
            # SPBs com Type=SRV que estão no R189 mas não no SPB consolidado
            spb_srv_missing = r189_spb_srv_ids - spb_ids
            if spb_srv_missing:
                logger.warning(f"Encontrados {len(spb_srv_missing)} SPBs com Type=SRV no R189 que estão ausentes no SPB consolidado")
                for spb_id in spb_srv_missing:
                    r189_row = r189_data[r189_data['Invoice number'] == spb_id].iloc[0]
                    divergences.append({
                        'Tipo': 'ID encontrado apenas no R189',
                        'SPB_ID': spb_id,
                        'CNPJ SPB': 'N/A',
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor SPB': 'N/A',
                        'Valor R189': r189_row[coluna_total_encontrada],
                        'Detalhes': f'SPB com Type=SRV não encontrado no SPB consolidado'
                    })
            
            # SPBs que estão no SPB consolidado mas não como Type=SRV no R189
            spb_missing_srv = spb_ids - r189_spb_srv_ids
            if spb_missing_srv:
                logger.warning(f"Encontrados {len(spb_missing_srv)} SPBs no consolidado SPB que não são Type=SRV no R189")
                for spb_id in spb_missing_srv:
                    # Verificar se existe no R189 com outro tipo
                    r189_row = r189_data[r189_data['Invoice number'] == spb_id]
                    if not r189_row.empty:
                        invoice_type = r189_row.iloc[0]['Invoice Type']
                        logger.warning(f"SPB {spb_id} encontrado no R189 com Type={invoice_type}, deveria ser SRV")
                        divergences.append({
                            'Tipo': 'SPB no consolidado com tipo incorreto no R189',
                            'SPB_ID': spb_id,
                            'CNPJ SPB': spb_data[spb_data['SPB_ID'] == spb_id].iloc[0]['CNPJ'],
                            'CNPJ R189': r189_row.iloc[0]['CNPJ - WEG'],
                            'Valor SPB': spb_data[spb_data['SPB_ID'] == spb_id].iloc[0]['VALOR_TOTAL'],
                            'Valor R189': r189_row.iloc[0][coluna_total_encontrada],
                            'Detalhes': f'SPB existe no R189 com Type={invoice_type}, deveria ser SRV'
                        })
                    else:
                        # Não existe no R189
                        spb_row = spb_data[spb_data['SPB_ID'] == spb_id].iloc[0]
                        divergences.append({
                            'Tipo': 'ID do SPB não encontrado no R189',
                            'SPB_ID': spb_id,
                            'CNPJ SPB': spb_row['CNPJ'],
                            'CNPJ R189': 'N/A',
                            'Valor SPB': spb_row['VALOR_TOTAL'],
                            'Valor R189': 'N/A',
                            'Detalhes': 'SPB do consolidado não encontrado no R189'
                        })
            
            # Verificar divergências de CNPJ e valor para SPBs com Type=SRV que existem em ambos
            spb_srv_em_ambos = r189_spb_srv_ids.intersection(spb_ids)
            logger.info(f"SPBs com Type=SRV presentes tanto no R189 quanto no SPB consolidado: {len(spb_srv_em_ambos)}")
            
            for spb_id in spb_srv_em_ambos:
                r189_row = r189_data[r189_data['Invoice number'] == spb_id].iloc[0]
                spb_row = spb_data[spb_data['SPB_ID'] == spb_id].iloc[0]
                
                # Verifica CNPJ
                if spb_row['CNPJ'] != r189_row['CNPJ - WEG']:
                    logger.warning(f"CNPJ divergente para SPB {spb_id} com Type=SRV: SPB={spb_row['CNPJ']}, R189={r189_row['CNPJ - WEG']}")
                    divergences.append({
                        'Tipo': 'CNPJ divergente',
                        'SPB_ID': spb_id,
                        'CNPJ SPB': spb_row['CNPJ'],
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor SPB': spb_row['VALOR_TOTAL'],
                        'Valor R189': r189_row[coluna_total_encontrada],
                        'Detalhes': f'CNPJ divergente para SPB {spb_id} com Type=SRV'
                    })
                
                # Verifica valor
                valor_spb = round(float(spb_row['VALOR_TOTAL']), 2)
                valor_r189 = round(float(r189_row[coluna_total_encontrada]), 2)
                if abs(valor_spb - valor_r189) > 0.01:  # Tolerância de 1 centavo
                    logger.warning(f"Valor divergente para SPB {spb_id} com Type=SRV: SPB={valor_spb}, R189={valor_r189}")
                    divergences.append({
                        'Tipo': 'Valor divergente',
                        'SPB_ID': spb_id,
                        'CNPJ SPB': spb_row['CNPJ'],
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor SPB': valor_spb,
                        'Valor R189': valor_r189,
                        'Detalhes': f'Valor divergente para SPB {spb_id} com Type=SRV'
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
                
                # Listar todas as planilhas disponíveis nos arquivos
                spb_excel = pd.ExcelFile(spb_io)
                spb_sheets = spb_excel.sheet_names
                logger.info(f"Planilhas disponíveis em SPB_consolidado.xlsx: {spb_sheets}")
                
                r189_excel = pd.ExcelFile(r189_io)
                r189_sheets = r189_excel.sheet_names
                logger.info(f"Planilhas disponíveis em R189_consolidado.xlsx: {r189_sheets}")
                
                nfserv_excel = pd.ExcelFile(nfserv_io)
                nfserv_sheets = nfserv_excel.sheet_names
                logger.info(f"Planilhas disponíveis em NFSERV_consolidado.xlsx: {nfserv_sheets}")
                
                # Reabrir os BytesIO pois foram consumidos pelo ExcelFile
                spb_io = BytesIO(spb_content)
                r189_io = BytesIO(r189_content)
                nfserv_io = BytesIO(nfserv_content)
                
                # Usar o nome correto da planilha 'SPB_Consolidado' em vez de 'Consolidado_SPB'
                df_spb = pd.read_excel(spb_io, sheet_name='SPB_Consolidado')
                
                # Usar a primeira planilha disponível para R189 e NFSERV se as específicas não existirem
                if 'Consolidado_R189' in r189_sheets:
                    df_r189 = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                else:
                    df_r189 = pd.read_excel(r189_io, sheet_name=r189_sheets[0])
                    logger.info(f"Usando planilha alternativa para R189: {r189_sheets[0]}")
                
                if 'Consolidado_NFSERV' in nfserv_sheets:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name='Consolidado_NFSERV')
                else:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name=nfserv_sheets[0])
                    logger.info(f"Usando planilha alternativa para NFSERV: {nfserv_sheets[0]}")
                
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
from typing import Dict, Any, Tuple
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class DivergenceReportNFSERVR189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados NFSERV e R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        # Lista de possíveis nomes para a coluna de total
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera', 'Total', 'Valor Total']

    async def check_divergences(self, nfserv_data, r189_data):
        """
        Verifica divergências entre os dados consolidados do NFSERV e R189.
        
        Args:
            nfserv_data: DataFrame com os dados consolidados do NFSERV
            r189_data: DataFrame com os dados consolidados do R189
            
        Returns:
            tuple: (sucesso, mensagem, DataFrame com divergências)
        """
        try:
            logger.info("Iniciando verificação de divergências entre NFSERV e R189")
            
            # Validação inicial dos DataFrames
            if nfserv_data is None or r189_data is None:
                logger.error("DataFrames não podem ser None")
                return False, "Erro: DataFrames não podem ser None", pd.DataFrame()
                
            if nfserv_data.empty or r189_data.empty:
                logger.error("DataFrames não podem estar vazios")
                return False, "Erro: DataFrames não podem estar vazios", pd.DataFrame()
            
            logger.info(f"NFSERV: {len(nfserv_data)} linhas, R189: {len(r189_data)} linhas")
            
            divergences = []
            
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
            
            # Extrai as siglas dos IDs
            def extract_sigla(id_value):
                if pd.isna(id_value):
                    return None
                parts = str(id_value).split('-')
                return parts[0] if len(parts) > 1 else None
            
            # Adiciona coluna de sigla em ambos os DataFrames
            logger.info("Extraindo siglas dos IDs")
            nfserv_data['SIGLA'] = nfserv_data['NFSERV_ID'].apply(extract_sigla)
            r189_data['SIGLA'] = r189_data['Invoice number'].apply(extract_sigla)
            
            # Obtém siglas únicas (excluindo SPB e valores nulos)
            siglas_unicas = set(nfserv_data['SIGLA'].unique()) - {'SPB', None}
            logger.info(f"Siglas únicas encontradas: {siglas_unicas}")
            
            # Verifica se as colunas necessárias existem
            nfserv_required = ['NFSERV_ID', 'CNPJ', 'VALOR_TOTAL']
            r189_required = ['Invoice number', 'CNPJ - WEG', coluna_total_encontrada]
            
            missing_nfserv = [col for col in nfserv_required if col not in nfserv_data.columns]
            if missing_nfserv:
                logger.error(f"Colunas necessárias não encontradas no NFSERV: {missing_nfserv}")
                return False, f"Erro: Colunas necessárias não encontradas no NFSERV: {', '.join(missing_nfserv)}", pd.DataFrame()
                
            missing_r189 = [col for col in r189_required if col not in r189_data.columns]
            if missing_r189:
                logger.error(f"Colunas necessárias não encontradas no R189: {missing_r189}")
                return False, f"Erro: Colunas necessárias não encontradas no R189: {', '.join(missing_r189)}", pd.DataFrame()
            
            # Validação de tipos de dados
            try:
                logger.info("Convertendo colunas de valor para numérico")
                nfserv_data['VALOR_TOTAL'] = pd.to_numeric(nfserv_data['VALOR_TOTAL'], errors='coerce')
                r189_data[coluna_total_encontrada] = pd.to_numeric(r189_data[coluna_total_encontrada], errors='coerce')
            except Exception as e:
                logger.error(f"Erro ao converter valores: {str(e)}")
                return False, f"Erro: Valores inválidos nas colunas de valor: {str(e)}", pd.DataFrame()
            
            # Para cada sigla, verifica as contagens e divergências
            for sigla in siglas_unicas:
                logger.info(f"Analisando sigla: {sigla}")
                
                # Contagem no NFSERV
                nfserv_count = len(nfserv_data[nfserv_data['SIGLA'] == sigla])
                
                # Contagem no R189
                r189_count = len(r189_data[r189_data['SIGLA'] == sigla])
                
                logger.info(f"Contagem para sigla {sigla}: NFSERV={nfserv_count}, R189={r189_count}")
                
                # Adiciona contagem para todas as siglas
                divergences.append({
                    'Tipo': f'CONTAGEM_{sigla}',
                    'NFSERV_ID': 'N/A',
                    'CNPJ NFSERV': 'N/A',
                    'CNPJ R189': 'N/A',
                    'Valor NFSERV': nfserv_count,
                    'Valor R189': r189_count,
                    'Detalhes': f'Total de notas {sigla}: NFSERV={nfserv_count}, R189={r189_count}'
                })
                
                # Se houver diferença nas contagens, registra a divergência
                if nfserv_count != r189_count:
                    logger.warning(f"Divergência na contagem para sigla {sigla}: NFSERV={nfserv_count}, R189={r189_count}")
                    divergences.append({
                        'Tipo': 'CONTAGEM_NFSERV',
                        'NFSERV_ID': 'N/A',
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': 'N/A',
                        'Valor NFSERV': nfserv_count,
                        'Valor R189': r189_count
                    })
                
                # Verifica IDs específicos da sigla
                nfserv_ids = set(nfserv_data[nfserv_data['SIGLA'] == sigla]['NFSERV_ID'])
                r189_ids = set(r189_data[r189_data['SIGLA'] == sigla]['Invoice number'])
                
                # IDs no NFSERV mas não no R189
                missing_in_r189 = nfserv_ids - r189_ids
                logger.info(f"IDs no NFSERV mas não no R189 para sigla {sigla}: {len(missing_in_r189)}")
                
                for nfserv_id in missing_in_r189:
                    nfserv_rows = nfserv_data[nfserv_data['NFSERV_ID'] == nfserv_id]
                    if nfserv_rows.empty:
                        continue
                    
                    nfserv_row = nfserv_rows.iloc[0]
                    divergences.append({
                        'Tipo': 'Nota não encontrada no R189',
                        'NFSERV_ID': nfserv_id,
                        'CNPJ NFSERV': nfserv_row['CNPJ'],
                        'CNPJ R189': 'Não encontrado',
                        'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                        'Valor R189': 'N/A',
                        'Detalhes': f'Nota {nfserv_id} existe no NFSERV mas não foi encontrada no R189'
                    })
                
                # IDs no R189 mas não no NFSERV
                missing_in_nfserv = r189_ids - nfserv_ids
                logger.info(f"IDs no R189 mas não no NFSERV para sigla {sigla}: {len(missing_in_nfserv)}")
                
                for r189_id in missing_in_nfserv:
                    r189_rows = r189_data[r189_data['Invoice number'] == r189_id]
                    if r189_rows.empty:
                        continue
                    
                    r189_row = r189_rows.iloc[0]
                    divergences.append({
                        'Tipo': 'Nota não encontrada no NFSERV',
                        'NFSERV_ID': r189_id,
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor NFSERV': 'N/A',
                        'Valor R189': r189_row[coluna_total_encontrada],
                        'Detalhes': f'Nota {r189_id} existe no R189 mas não foi encontrada no NFSERV'
                    })
                
                # Verifica divergências para IDs que existem em ambos
                common_ids = nfserv_ids & r189_ids
                logger.info(f"IDs presentes em ambos os sistemas para sigla {sigla}: {len(common_ids)}")
                
                for nfserv_id in common_ids:
                    nfserv_rows = nfserv_data[nfserv_data['NFSERV_ID'] == nfserv_id]
                    r189_rows = r189_data[r189_data['Invoice number'] == nfserv_id]
                    
                    if nfserv_rows.empty or r189_rows.empty:
                        continue
                    
                    nfserv_row = nfserv_rows.iloc[0]
                    r189_row = r189_rows.iloc[0]
                    
                    # Verifica CNPJ - Normaliza removendo espaços e pontuação
                    nfserv_cnpj = str(nfserv_row['CNPJ']).strip().replace('.', '').replace('-', '').replace('/', '')
                    r189_cnpj = str(r189_row['CNPJ - WEG']).strip().replace('.', '').replace('-', '').replace('/', '')
                    
                    if nfserv_cnpj != r189_cnpj:
                        logger.warning(f"CNPJ divergente para {nfserv_id}: NFSERV={nfserv_row['CNPJ']}, R189={r189_row['CNPJ - WEG']}")
                        divergences.append({
                            'Tipo': 'CNPJ divergente',
                            'NFSERV_ID': nfserv_id,
                            'CNPJ NFSERV': nfserv_row['CNPJ'],
                            'CNPJ R189': r189_row['CNPJ - WEG'],
                            'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                            'Valor R189': r189_row[coluna_total_encontrada],
                            'Detalhes': f'CNPJ diferente para nota {nfserv_id}: NFSERV={nfserv_row["CNPJ"]}, R189={r189_row["CNPJ - WEG"]}'
                        })
                    
                    # Verifica Valor
                    try:
                        # Trata valores com vírgula ou ponto
                        nfserv_valor = str(nfserv_row['VALOR_TOTAL']).strip().replace(',', '.')
                        r189_valor = str(r189_row[coluna_total_encontrada]).strip().replace(',', '.')
                        
                        # Remove caracteres não numéricos exceto ponto
                        nfserv_valor = ''.join(c for c in nfserv_valor if c.isdigit() or c == '.')
                        r189_valor = ''.join(c for c in r189_valor if c.isdigit() or c == '.')
                        
                        # Converte para float
                        nfserv_valor_float = float(nfserv_valor)
                        r189_valor_float = float(r189_valor)
                        
                        # Se os valores forem diferentes (com margem de tolerância)
                        if abs(nfserv_valor_float - r189_valor_float) > 0.01:
                            logger.warning(f"Valor divergente para {nfserv_id}: NFSERV={nfserv_valor_float}, R189={r189_valor_float}")
                            divergences.append({
                                'Tipo': 'VALOR',
                                'NFSERV_ID': nfserv_id,
                                'CNPJ NFSERV': nfserv_row['CNPJ'],
                                'CNPJ R189': r189_row['CNPJ - WEG'],
                                'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                                'Valor R189': r189_row[coluna_total_encontrada],
                                'Detalhes': f'Valor diferente para nota {nfserv_id}: NFSERV={nfserv_row["VALOR_TOTAL"]}, R189={r189_row[coluna_total_encontrada]}'
                            })
                    except (ValueError, TypeError) as e:
                        # Se houver erro na conversão, registra como divergência
                        logger.warning(f"Erro na validação de valor para {nfserv_id}: {str(e)}")
                        divergences.append({
                            'Tipo': 'Erro na validação de valor',
                            'NFSERV_ID': nfserv_id,
                            'CNPJ NFSERV': nfserv_row['CNPJ'],
                            'CNPJ R189': r189_row['CNPJ - WEG'],
                            'Valor NFSERV': str(nfserv_row['VALOR_TOTAL']),
                            'Valor R189': str(r189_row[coluna_total_encontrada]),
                            'Detalhes': f'Erro ao comparar valores para nota {nfserv_id}: Formato inválido'
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
            required_columns = ['Tipo', 'NFSERV_ID', 'CNPJ NFSERV', 'CNPJ R189', 'Valor NFSERV', 'Valor R189']
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
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    divergences_df.to_excel(writer, index=False, sheet_name='Divergencias_NFSERV_R189')
                    
                    # Ajusta a largura das colunas
                    workbook = writer.book
                    worksheet = writer.sheets['Divergencias_NFSERV_R189']
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
                report_name = f'{timestamp}_divergencias_nfserv_r189.xlsx'
                
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
        Gera o relatório de divergências comparando NFSERV e R189.
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO NFSERV vs R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca os arquivos consolidados no SharePoint
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
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos Excel")
            try:
                nfserv_io = BytesIO(nfserv_content)
                r189_io = BytesIO(r189_content)
                
                # Listar todas as planilhas disponíveis nos arquivos
                nfserv_excel = pd.ExcelFile(nfserv_io)
                nfserv_sheets = nfserv_excel.sheet_names
                logger.info(f"Planilhas disponíveis em NFSERV_consolidado.xlsx: {nfserv_sheets}")
                
                r189_excel = pd.ExcelFile(r189_io)
                r189_sheets = r189_excel.sheet_names
                logger.info(f"Planilhas disponíveis em R189_consolidado.xlsx: {r189_sheets}")
                
                # Reabrir os BytesIO pois foram consumidos pelo ExcelFile
                nfserv_io = BytesIO(nfserv_content)
                r189_io = BytesIO(r189_content)
                
                # Usar a primeira planilha disponível para NFSERV e R189 se as específicas não existirem
                if 'NFSERV_consolidado' in nfserv_sheets:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name='NFSERV_consolidado')
                    logger.info("Usando planilha 'NFSERV_consolidado'")
                elif 'Consolidado_NFSERV' in nfserv_sheets:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name='Consolidado_NFSERV')
                    logger.info("Usando planilha 'Consolidado_NFSERV'")
                else:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name=nfserv_sheets[0])
                    logger.info(f"Usando primeira planilha disponível para NFSERV: {nfserv_sheets[0]}")
                
                if 'Consolidado_R189' in r189_sheets:
                    df_r189 = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                    logger.info("Usando planilha 'Consolidado_R189'")
                else:
                    df_r189 = pd.read_excel(r189_io, sheet_name=r189_sheets[0])
                    logger.info(f"Usando primeira planilha disponível para R189: {r189_sheets[0]}")
                
                logger.info(f"Linhas em NFSERV: {len(df_nfserv)}")
                logger.info(f"Linhas em R189: {len(df_r189)}")
            except Exception as e:
                logger.error(f"Erro ao ler arquivos Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos Excel: {str(e)}",
                    "show_popup": True
                }
            
            if df_nfserv.empty:
                logger.error("Arquivo NFSERV_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo NFSERV_consolidado.xlsx está vazio",
                    "show_popup": True
                }
                
            if df_r189.empty:
                logger.error("Arquivo R189_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo R189_consolidado.xlsx está vazio",
                    "show_popup": True
                }
            
            # Verifica divergências
            logger.info("Verificando divergências")
            success, message, divergences_df = await self.check_divergences(df_nfserv, df_r189)
            
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
                relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/NFSERV_R189"
                
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
                    "message": f"Relatório de divergências gerado e salvo com sucesso!\n\nResumo das divergências encontradas:\n{message}\n\nO arquivo foi salvo na pasta RELATÓRIOS/NFSERV_R189 no SharePoint.",
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
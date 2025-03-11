from typing import Dict, Any, List
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
import traceback
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class DivergenceReportQPER189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados QPE e R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()

    async def check_divergences(self, qpe_data: pd.DataFrame, r189_data: pd.DataFrame) -> tuple[bool, str, pd.DataFrame]:
        """
        Verifica divergências entre os dados consolidados do QPE e R189.
        
        Args:
            qpe_data: DataFrame com os dados consolidados do QPE
            r189_data: DataFrame com os dados consolidados do R189
            
        Returns:
            tuple: (sucesso, mensagem, DataFrame com divergências)
        """
        try:
            logger.info("Iniciando verificação de divergências entre QPE e R189")
            
            # Validação inicial dos DataFrames
            if qpe_data is None or r189_data is None:
                logger.error("DataFrames não podem ser None")
                return False, "Erro: DataFrames não podem ser None", pd.DataFrame()
                
            if qpe_data.empty or r189_data.empty:
                logger.error("DataFrames não podem estar vazios")
                return False, "Erro: DataFrames não podem estar vazios", pd.DataFrame()
            
            logger.info(f"QPE: {len(qpe_data)} linhas, R189: {len(r189_data)} linhas")
            
            divergences = []
            
            # Contagem de QPE_ID
            qpe_ids = set(qpe_data['QPE_ID'].str.lower().unique())
            r189_qpe_ids = set(r189_data[r189_data['Invoice number'].str.lower().str.startswith('qpe-', na=False)]['Invoice number'].str.lower().unique())
            
            logger.info(f"QPE IDs: {len(qpe_ids)}, R189 QPE IDs: {len(r189_qpe_ids)}")
            
            # Adiciona informação de quantidade ao início do relatório
            divergences.append({
                'Tipo': 'CONTAGEM_QPE',
                'QPE_ID': 'N/A',
                'CNPJ QPE': 'N/A',
                'CNPJ R189': 'N/A',
                'Valor QPE': len(qpe_ids),
                'Valor R189': len(r189_qpe_ids)
            })
            
            # Se houver divergência na quantidade, identifica quais estão faltando
            if len(qpe_ids) != len(r189_qpe_ids):
                logger.info("Divergência na quantidade de QPE IDs")
                
                # IDs que estão no QPE mas não no R189
                missing_in_r189 = qpe_ids - r189_qpe_ids
                logger.info(f"IDs no QPE mas não no R189: {len(missing_in_r189)}")
                
                for qpe_id in missing_in_r189:
                    qpe_row = qpe_data[qpe_data['QPE_ID'].str.lower() == qpe_id].iloc[0]
                    divergences.append({
                        'Tipo': 'QPE_ID não encontrado no R189',
                        'QPE_ID': qpe_row['QPE_ID'],  # Mantém o caso original
                        'CNPJ QPE': qpe_row['CNPJ'],
                        'CNPJ R189': 'N/A',
                        'Valor QPE': qpe_row['VALOR_TOTAL'],
                        'Valor R189': 'N/A'
                    })
                
                # IDs que estão no R189 mas não no QPE
                missing_in_qpe = r189_qpe_ids - qpe_ids
                logger.info(f"IDs no R189 mas não no QPE: {len(missing_in_qpe)}")
                
                for r189_id in missing_in_qpe:
                    r189_row = r189_data[r189_data['Invoice number'].str.lower() == r189_id].iloc[0]
                    divergences.append({
                        'Tipo': 'QPE_ID não encontrado no QPE',
                        'QPE_ID': r189_row['Invoice number'],  # Mantém o caso original
                        'CNPJ QPE': 'N/A',
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor QPE': 'N/A',
                        'Valor R189': r189_row['Total Geral']
                    })
            
            # Verifica se as colunas necessárias existem
            qpe_required = ['QPE_ID', 'CNPJ', 'VALOR_TOTAL']
            r189_required = ['Invoice number', 'CNPJ - WEG', 'Total Geral']
            
            missing_qpe = [col for col in qpe_required if col not in qpe_data.columns]
            if missing_qpe:
                logger.error(f"Colunas necessárias não encontradas no QPE: {missing_qpe}")
                return False, f"Erro: Colunas necessárias não encontradas no QPE: {', '.join(missing_qpe)}", pd.DataFrame()
                
            missing_r189 = [col for col in r189_required if col not in r189_data.columns]
            if missing_r189:
                logger.error(f"Colunas necessárias não encontradas no R189: {missing_r189}")
                return False, f"Erro: Colunas necessárias não encontradas no R189: {', '.join(missing_r189)}", pd.DataFrame()
            
            # Validação de tipos de dados
            try:
                logger.info("Convertendo colunas de valor para numérico")
                qpe_data['VALOR_TOTAL'] = pd.to_numeric(qpe_data['VALOR_TOTAL'], errors='coerce')
                r189_data['Total Geral'] = pd.to_numeric(r189_data['Total Geral'], errors='coerce')
            except Exception as e:
                logger.error(f"Erro ao converter valores: {str(e)}")
                return False, f"Erro: Valores inválidos nas colunas de valor: {str(e)}", pd.DataFrame()
            
            # Verifica valores nulos
            null_qpe_id = qpe_data['QPE_ID'].isnull().sum()
            null_qpe_cnpj = qpe_data['CNPJ'].isnull().sum()
            null_qpe_valor = qpe_data['VALOR_TOTAL'].isnull().sum()
            
            logger.info(f"Valores nulos - QPE_ID: {null_qpe_id}, CNPJ: {null_qpe_cnpj}, VALOR_TOTAL: {null_qpe_valor}")
            
            if any([null_qpe_id, null_qpe_cnpj, null_qpe_valor]):
                logger.error("Encontrados valores nulos no QPE")
                return False, (
                    "Erro: Encontrados valores nulos no QPE:\n"
                    f"QPE_ID: {null_qpe_id} valores nulos\n"
                    f"CNPJ: {null_qpe_cnpj} valores nulos\n"
                    f"VALOR_TOTAL: {null_qpe_valor} valores nulos"
                ), pd.DataFrame()
            
            # Itera sobre cada linha do QPE
            logger.info("Verificando divergências linha a linha")
            for idx, qpe_row in qpe_data.iterrows():
                qpe_id = str(qpe_row['QPE_ID']).strip()
                qpe_cnpj = str(qpe_row['CNPJ']).strip()
                qpe_valor = float(qpe_row['VALOR_TOTAL'])
                
                # Validação do QPE_ID
                if not qpe_id:
                    logger.warning(f"QPE_ID vazio encontrado para CNPJ: {qpe_cnpj}")
                    divergences.append({
                        'Tipo': 'QPE_ID vazio',
                        'QPE_ID': 'VAZIO',
                        'CNPJ QPE': qpe_cnpj,
                        'CNPJ R189': 'N/A',
                        'Valor QPE': qpe_valor,
                        'Valor R189': 'N/A'
                    })
                    continue
                
                # Validação do CNPJ
                if not qpe_cnpj or len(qpe_cnpj) != 18:  # Formato XX.XXX.XXX/XXXX-XX
                    logger.warning(f"CNPJ inválido encontrado: {qpe_cnpj} para QPE_ID: {qpe_id}")
                    divergences.append({
                        'Tipo': 'CNPJ inválido',
                        'QPE_ID': qpe_id,
                        'CNPJ QPE': qpe_cnpj,
                        'CNPJ R189': 'N/A',
                        'Valor QPE': qpe_valor,
                        'Valor R189': 'N/A'
                    })
                    continue
                
                # Procura o QPE_ID no R189
                r189_match = r189_data[r189_data['Invoice number'].str.lower() == qpe_id.lower()]
                
                if r189_match.empty:
                    # Não adiciona novamente se já foi registrado como ausente
                    if qpe_id.lower() not in missing_in_r189:
                        logger.warning(f"QPE_ID não encontrado no R189: {qpe_id}")
                        divergences.append({
                            'Tipo': 'QPE_ID não encontrado no R189',
                            'QPE_ID': qpe_id,
                            'CNPJ QPE': qpe_cnpj,
                            'CNPJ R189': 'Não encontrado',
                            'Valor QPE': qpe_valor,
                            'Valor R189': 'Não encontrado'
                        })
                else:
                    r189_row = r189_match.iloc[0]
                    r189_cnpj = str(r189_row['CNPJ - WEG']).strip()
                    r189_valor = float(r189_row['Total Geral'])
                    
                    # Verifica CNPJ
                    if qpe_cnpj != r189_cnpj:
                        logger.warning(f"CNPJ divergente para QPE_ID: {qpe_id}, QPE: {qpe_cnpj}, R189: {r189_cnpj}")
                        divergences.append({
                            'Tipo': 'CNPJ divergente',
                            'QPE_ID': qpe_id,
                            'CNPJ QPE': qpe_cnpj,
                            'CNPJ R189': r189_cnpj,
                            'Valor QPE': qpe_valor,
                            'Valor R189': r189_valor
                        })
                    # Verifica Valor
                    elif abs(qpe_valor - r189_valor) > 0.01:  # Tolerância de 1 centavo
                        logger.warning(f"Valor divergente para QPE_ID: {qpe_id}, QPE: {qpe_valor}, R189: {r189_valor}")
                        divergences.append({
                            'Tipo': 'Valor divergente',
                            'QPE_ID': qpe_id,
                            'CNPJ QPE': qpe_cnpj,
                            'CNPJ R189': r189_cnpj,
                            'Valor QPE': qpe_valor,
                            'Valor R189': r189_valor
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

    async def generate_excel_report(self, divergences_df: pd.DataFrame) -> Dict[str, Any]:
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
            required_columns = ['Tipo', 'QPE_ID', 'CNPJ QPE', 'CNPJ R189', 'Valor QPE', 'Valor R189']
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
                    divergences_df.to_excel(writer, index=False, sheet_name='Divergencias_QPE_R189')
                    
                    # Ajusta a largura das colunas
                    workbook = writer.book
                    worksheet = writer.sheets['Divergencias_QPE_R189']
                    for i, col in enumerate(divergences_df.columns):
                        max_length = max(
                            divergences_df[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.set_column(i, i, max_length + 2)
                
                output.seek(0)
                logger.info("Arquivo Excel criado com sucesso")
                
                # Nome do arquivo com timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_name = f'report_divergencias_qpe_r189_{timestamp}.xlsx'
                
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
        Gera o relatório de divergências comparando QPE e R189.
        
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO QPE vs R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca os arquivos consolidados no SharePoint
            logger.info("Baixando arquivo QPE_consolidado.xlsx")
            qpe_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'QPE_consolidado.xlsx',
                consolidado_path
            )
            
            if not qpe_content:
                logger.error("Não foi possível baixar o arquivo QPE_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo QPE_consolidado.xlsx",
                    "show_popup": True
                }
            
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
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos Excel")
            try:
                qpe_io = BytesIO(qpe_content)
                r189_io = BytesIO(r189_content)
                
                df_qpe = pd.read_excel(qpe_io, sheet_name='Consolidado_QPE')
                df_r189 = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                
                logger.info(f"Linhas em QPE: {len(df_qpe)}")
                logger.info(f"Linhas em R189: {len(df_r189)}")
            except Exception as e:
                logger.error(f"Erro ao ler arquivos Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos Excel: {str(e)}",
                    "show_popup": True
                }
            
            if df_qpe.empty:
                logger.error("Arquivo QPE_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo QPE_consolidado.xlsx está vazio",
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
            success, message, divergences_df = await self.check_divergences(df_qpe, df_r189)
            
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
                
                if not report_result["success"]:
                    logger.error(f"Erro ao gerar relatório: {report_result.get('error')}")
                    return {
                        "success": False,
                        "error": report_result.get("error"),
                        "show_popup": True
                    }
                
                # Nome do arquivo de relatório
                report_filename = report_result["filename"]
                
                # Envia o relatório para o SharePoint
                logger.info(f"Enviando relatório {report_filename} para o SharePoint")
                relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/QPE_R189"
                
                # Usar o método assíncrono do SharePointAuth
                upload_success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    conteudo=report_result["file_content"].getvalue(),
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
                    "message": f"Relatório de divergências gerado e salvo com sucesso!\n\nResumo das divergências encontradas:\n{message}\n\nO arquivo foi salvo na pasta RELATÓRIOS/QPE_R189 no SharePoint.",
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
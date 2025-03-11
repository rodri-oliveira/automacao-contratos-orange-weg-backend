from typing import Dict, Any, List
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class ReportMunCodeR189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados de códigos municipais e R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        
        # Mapeamento de serviços para material e tipo
        self.service_mapping = {
            "14.02": {"material": "80001098", "type": "Assistência Técnica"},
            "17.01": {"material": "80001110", "type": "Acessoria ou Consultoria"},
            "14.01": {"material": "80001097", "type": "LUBRIFICACAO, LIMPEZA"},
            "1.07": {"material": "80001019", "type": "SUPORTE TECNICO EM INFORMATICA"},
            "3115": {"material": "80001110", "type": "Assessoria E Consultoria"},
            "1880": {"material": "80001098", "type": "Assistência Técnica - Instalação"},
            "1.03": {"material": "80001680", "type": "Processamento e Armazenamento"}
        }
        
        self.service_cnpj_mapping = {
            "14.02 - Assistência Técnica": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "17.01 - Acessoria ou Consultoria": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "14.01 - LUBRIFICACAO, LIMPEZA": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "1.07 - SUPORTE TECNICO EM INFORMATICA": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "3115 - Assessoria E Consultoria": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "1880 - Assistência Técnica - Instalação": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            },
            "1.03 - Processamento e Armazenamento": {
                "14.759.173/0002-83", "07.175.725/0042-38", "07.175.725/0014-84",
                "60.621.141/0005-87", "13.772.125/0007-77", "07.175.725/0030-02",
                "60.621.141/0004-04", "07.175.725/0004-02", "07.175.725/0010-50",
                "10.885.321/0001-74", "60.621.141/0006-68", "14.759.173/0001-00",
                "07.175.725/0024-56", "07.175.725/0021-03", "07.175.725/0026-18",
                "84.584.994/0007-16"
            }
        }
        
        # Lista de possíveis nomes para a coluna de total
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera', 'Total', 'Valor Total']

    def validate_service_cnpj(self, row) -> bool:
        """
        Valida se o CNPJ está autorizado para o serviço específico.
        """
        try:
            municipality_code = str(row['Municipality Code']).strip()
            try:
                # Tenta converter para formato numérico se for um número
                municipality_code = str(int(float(municipality_code)))
            except (ValueError, TypeError):
                pass
                
            cnpj = str(row['CNPJ - WEG']).strip()
            
            logger.debug(f"Validando: Municipality Code={municipality_code}, CNPJ={cnpj}")
            
            # Procura o serviço que corresponde ao código municipal
            service = None
            for service_name in self.service_cnpj_mapping:
                service_code = service_name.split(' - ')[0].strip()
                try:
                    # Tenta converter para formato numérico se for um número
                    service_code = str(int(float(service_code)))
                except (ValueError, TypeError):
                    pass
                    
                logger.debug(f"Comparando: {service_code} == {municipality_code}")
                if service_code == municipality_code:
                    service = service_name
                    logger.debug(f"Serviço encontrado: {service}")
                    break
            
            if not service:
                logger.debug(f"Nenhum serviço encontrado para o código {municipality_code}")
                return False
            
            is_authorized = cnpj in self.service_cnpj_mapping[service]
            logger.debug(f"CNPJ {cnpj} {'está' if is_authorized else 'não está'} autorizado para o serviço {service}")
            return is_authorized
            
        except Exception as e:
            logger.error(f"Erro ao validar CNPJ: {str(e)}")
            return False

    async def check_municipality_codes(self, mun_code_data, r189_data, qpe_data=None, spb_data=None):
        """
        Verifica divergências entre os dados consolidados dos códigos municipais e R189.
        """
        try:
            # Verifica qual coluna de total está presente no DataFrame
            coluna_total = None
            for col in self.colunas_total:
                if col in mun_code_data.columns:
                    coluna_total = col
                    break
            
            if not coluna_total:
                return {
                    "success": False,
                    "error": f"Nenhuma coluna de total encontrada. Colunas disponíveis: {', '.join(mun_code_data.columns)}"
                }

            # Primeiro, valida os CNPJs por serviço
            mun_code_data['CNPJ_Autorizado'] = mun_code_data.apply(self.validate_service_cnpj, axis=1)
            
            # Filtra apenas os registros com CNPJs não autorizados
            cnpj_divergences = mun_code_data[~mun_code_data['CNPJ_Autorizado']].copy()
            cnpj_divergences['Tipo_Divergencia'] = 'CNPJ não autorizado para o serviço'
            
            # Filtra apenas os registros com CNPJs autorizados para o agrupamento
            valid_data = mun_code_data[mun_code_data['CNPJ_Autorizado']].drop('CNPJ_Autorizado', axis=1)
            
            # Agrupa os dados por Municipality Code, CNPJ - WEG e Invoice number
            grouped_data = valid_data.groupby(
                ['Municipality Code', 'CNPJ - WEG', 'Invoice number']
            ).agg({
                coluna_total: 'sum',
                'Site Name - WEG 2': 'first'  # Mantém o primeiro Site Name encontrado
            }).reset_index()
            
            # Ordena o DataFrame agrupado para melhor visualização
            grouped_data = grouped_data.sort_values(
                by=['Municipality Code', 'CNPJ - WEG', 'Invoice number']
            )
            
            # Adiciona a coluna NF
            def get_nota_fiscal(row):
                try:
                    invoice_number = str(row['Invoice number']).strip()
                    
                    if invoice_number.startswith('QPE'):
                        # Busca no QPE_consolidado
                        if qpe_data is not None and 'QPE_ID' in qpe_data.columns and 'NOTA_FISCAL' in qpe_data.columns:
                            matching_rows = qpe_data[qpe_data['QPE_ID'] == invoice_number]
                            if not matching_rows.empty:
                                matching_nota = matching_rows['NOTA_FISCAL'].iloc[0]
                                return str(matching_nota).strip()
                    elif invoice_number.startswith('SPB'):
                        # Busca no SPB_consolidado
                        if spb_data is not None and 'SPB_ID' in spb_data.columns and 'Num_Nota' in spb_data.columns:
                            matching_rows = spb_data[spb_data['SPB_ID'] == invoice_number]
                            if not matching_rows.empty:
                                matching_nota = matching_rows['Num_Nota'].iloc[0]
                                return str(matching_nota).strip()
                    return ''
                except Exception as e:
                    logger.error(f"Erro ao processar invoice number {invoice_number}: {str(e)}")
                    return ''
            
            grouped_data['NF'] = grouped_data.apply(get_nota_fiscal, axis=1)
            
            # Aplica o mapeamento para criar as novas colunas
            def get_material_and_type(row):
                try:
                    # Pega o código do serviço (antes do hífen, se houver)
                    service_code = str(row['Municipality Code']).strip().split(' - ')[0].strip()
                    
                    # Busca no mapeamento
                    if service_code in self.service_mapping:
                        return pd.Series([
                            self.service_mapping[service_code]['material'],
                            self.service_mapping[service_code]['type']
                        ])
                    return pd.Series(['', ''])
                except Exception as e:
                    logger.error(f"Erro ao processar código de serviço {service_code}: {str(e)}")
                    return pd.Series(['', ''])
            
            # Aplica o mapeamento para criar as novas colunas
            grouped_data[['MATERIAL', 'Invoice_Type']] = grouped_data.apply(get_material_and_type, axis=1)
            
            # Reordena as colunas na ordem especificada
            try:
                grouped_data = grouped_data.reindex(columns=[
                    'CNPJ - WEG',
                    'Municipality Code',
                    'MATERIAL',
                    'Invoice_Type',
                    'NF',
                    'Site Name - WEG 2',
                    coluna_total
                ])
            except Exception as e:
                logger.warning(f"Erro ao reordenar colunas: {str(e)}")
            
            has_divergences = not cnpj_divergences.empty
            
            if has_divergences:
                message = f"Encontradas {len(cnpj_divergences)} divergências de CNPJ não autorizado."
            else:
                message = "Nenhuma divergência encontrada."
                
            message += f"\nForam geradas {len(grouped_data)} linhas após o agrupamento."

            return {
                "success": True,
                "message": message,
                "divergences": cnpj_divergences.to_dict('records') if not cnpj_divergences.empty else [],
                "grouped_data": grouped_data.to_dict('records')
            }

        except Exception as e:
            import traceback
            logger.error(f"Erro ao verificar divergências: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao verificar divergências: {str(e)}"
            }

    async def generate_excel_report(self, divergences, grouped_data):
        """
        Gera relatório Excel com as divergências encontradas e dados agrupados.
        """
        try:
            # Criar arquivo Excel em memória
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Aba de divergências (se houver)
                if divergences:
                    div_df = pd.DataFrame(divergences)
                    div_df.to_excel(
                        writer, 
                        index=False, 
                        sheet_name='Divergencias_CNPJs'
                    )
                
                # Aba de dados agrupados
                grouped_df = pd.DataFrame(grouped_data)
                grouped_df.to_excel(
                    writer, 
                    index=False, 
                    sheet_name='Dados_Agrupados'
                )
                
                # Ajusta o formato das colunas
                workbook = writer.book
                
                # Formato para valores monetários
                money_format = workbook.add_format({'num_format': '#,##0.00'})
                
                # Aplica formato nas abas
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    # Ajusta largura das colunas
                    for idx, col in enumerate(grouped_df.columns):
                        max_length = max(
                            grouped_df[col].astype(str).apply(len).max(),
                            len(col)
                        ) if not grouped_df.empty else len(col)
                        worksheet.set_column(idx, idx, max_length + 2)
                    
                    # Aplica formato monetário na coluna de total
                    for col in self.colunas_total:
                        if col in grouped_df.columns:
                            total_col = grouped_df.columns.get_loc(col)
                            worksheet.set_column(total_col, total_col, None, money_format)
                            break
            
            output.seek(0)
            
            # Define o nome do arquivo com timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_name = f'report_mun_code_r189_{timestamp}.xlsx'
            
            return {
                "success": True,
                "file_content": output,
                "filename": report_name
            }

        except Exception as e:
            import traceback
            logger.error(f"Erro ao gerar relatório Excel: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

    async def generate_report(self):
        """
        Gera o relatório de divergências entre códigos municipais e R189.
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO MUN_CODE vs R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca os arquivos consolidados no SharePoint
            logger.info("Baixando arquivo Municipality_Code_consolidado.xlsx")
            mun_code_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'Municipality_Code_consolidado.xlsx',
                consolidado_path
            )
            
            if not mun_code_content:
                logger.error("Não foi possível baixar o arquivo Municipality_Code_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo Municipality_Code_consolidado.xlsx",
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
            
            # Baixa os arquivos QPE e SPB para obter os números das notas fiscais
            logger.info("Baixando arquivo QPE_consolidado.xlsx")
            qpe_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'QPE_consolidado.xlsx',
                consolidado_path
            )
            
            logger.info("Baixando arquivo SPB_consolidado.xlsx")
            spb_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'SPB_consolidado.xlsx',
                consolidado_path
            )
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos Excel")
            try:
                mun_code_io = BytesIO(mun_code_content)
                r189_io = BytesIO(r189_content)
                
                mun_code_df = pd.read_excel(mun_code_io)
                r189_df = pd.read_excel(r189_io)
                
                qpe_df = pd.read_excel(BytesIO(qpe_content)) if qpe_content else None
                spb_df = pd.read_excel(BytesIO(spb_content)) if spb_content else None
                
                logger.info(f"Linhas em Municipality_Code: {len(mun_code_df)}")
                logger.info(f"Linhas em R189: {len(r189_df)}")
                logger.info(f"Linhas em QPE: {len(qpe_df) if qpe_df is not None else 0}")
                logger.info(f"Linhas em SPB: {len(spb_df) if spb_df is not None else 0}")
            except Exception as e:
                logger.error(f"Erro ao ler arquivos Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos Excel: {str(e)}",
                    "show_popup": True
                }
            
            # Verifica divergências e obtém dados agrupados
            logger.info("Verificando divergências")
            result = await self.check_municipality_codes(mun_code_df, r189_df, qpe_df, spb_df)
            
            if not result["success"]:
                logger.error(f"Erro na verificação: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "show_popup": True
                }
            
            divergences = result.get("divergences", [])
            grouped_data = result.get("grouped_data", [])
            message = result.get("message", "")
            
            logger.info(f"Resultado da verificação: {message}")
            
            # Gera o arquivo de relatório
            logger.info("Gerando relatório Excel")
            report_result = await self.generate_excel_report(divergences, grouped_data)
            
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
            relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/MUN_CODE"

            # Usar o método assíncrono do SharePointAuth em vez do SharePointClient
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
                "message": f"{message}\nRelatório gerado com sucesso: {report_filename}",
                "show_popup": True
            }
            
        except Exception as e:
            import traceback
            logger.error(f"Erro na geração do relatório: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro na geração do relatório: {str(e)}",
                "show_popup": True
            }

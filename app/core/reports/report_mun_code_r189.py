import pandas as pd
from io import BytesIO
import logging
from datetime import datetime
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class ReportMunCodeR189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados de códigos municipais e R189.
    """
    
    def __init__(self):
        self.report_name = "Relatório de Divergências MUN_CODE vs R189"
        self.sharepoint_auth = SharePointAuth()
        
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
        
        Args:
            row: Linha do DataFrame contendo Municipality Code e CNPJ - WEG
            
        Returns:
            bool: True se o CNPJ está autorizado para o serviço, False caso contrário
        """
        # Converte o código do município para inteiro
        try:
            municipality_code = str(int(float(str(row['Municipality Code']).strip())))
        except (ValueError, TypeError):
            municipality_code = str(row['Municipality Code']).strip()
            
        cnpj = str(row['CNPJ - WEG']).strip()
        
        # Debug: imprime os valores para verificação
        logger.info(f"Validando: Municipality Code={municipality_code}, CNPJ={cnpj}")
        
        # Procura o serviço que corresponde ao código municipal
        service = None
        for service_name in self.service_cnpj_mapping:
            # Extrai apenas o código numérico do nome do serviço e converte para inteiro
            try:
                service_code = str(int(float(service_name.split(' - ')[0].strip())))
            except (ValueError, TypeError):
                service_code = service_name.split(' - ')[0].strip()
                
            logger.info(f"Comparando: {service_code} == {municipality_code}")
            if service_code == municipality_code:
                service = service_name
                logger.info(f"Serviço encontrado: {service}")
                break
        
        if not service:
            logger.info(f"Nenhum serviço encontrado para o código {municipality_code}")
            return False
        
        is_authorized = cnpj in self.service_cnpj_mapping[service]
        logger.info(f"CNPJ {cnpj} {'está' if is_authorized else 'não está'} autorizado para o serviço {service}")
        return is_authorized

    async def check_municipality_codes(self, r189_data, municipality_data, qpe_data=None, spb_data=None):
        """
        Verifica divergências entre os dados consolidados dos códigos municipais e R189.
        
        Args:
            r189_data: Lista de dicionários com dados do R189
            municipality_data: Lista de dicionários com dados do Municipality_Code
            qpe_data: Lista de dicionários com dados do QPE (opcional)
            spb_data: Lista de dicionários com dados do SPB (opcional)
            
        Returns:
            dict: Resultado da verificação com divergências encontradas
        """
        try:
            logger.info("Verificando divergências entre MUN_CODE e R189")
            
            # Converter listas de dicionários para DataFrames
            mun_code_df = pd.DataFrame(municipality_data)
            r189_df = pd.DataFrame(r189_data)
            qpe_df = pd.DataFrame(qpe_data) if qpe_data else pd.DataFrame()
            spb_df = pd.DataFrame(spb_data) if spb_data else pd.DataFrame()
            
            # Verificar se as colunas necessárias existem
            required_columns = ['Municipality Code', 'CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']
            
            for col in required_columns:
                if col not in mun_code_df.columns:
                    return {
                        "success": False, 
                        "error": f"Coluna '{col}' não encontrada no arquivo Municipality_Code"
                    }
            
            # Verifica qual coluna de total está presente no DataFrame
            coluna_total = None
            for col in self.colunas_total:
                if col in mun_code_df.columns:
                    coluna_total = col
                    break
                    
            if not coluna_total:
                logger.warning(f"Nenhuma coluna de total encontrada. Colunas disponíveis: {', '.join(mun_code_df.columns)}")
                # Usar 'Total Geral' como padrão se não encontrar
                coluna_total = 'Total Geral'
                if coluna_total not in mun_code_df.columns:
                    return {
                        "success": False,
                        "error": f"Coluna de total não encontrada. Colunas disponíveis: {', '.join(mun_code_df.columns)}"
                    }
            
            # Primeiro, valida os CNPJs por serviço
            # Não podemos usar await dentro de lambda, então vamos fazer um loop
            cnpj_autorizado = []
            for _, row in mun_code_df.iterrows():
                cnpj_autorizado.append(self.validate_service_cnpj(row))
            
            mun_code_df['CNPJ_Autorizado'] = cnpj_autorizado
            
            # Filtra apenas os registros com CNPJs não autorizados
            cnpj_divergences = mun_code_df[~mun_code_df['CNPJ_Autorizado']].copy()
            cnpj_divergences['Tipo_Divergencia'] = 'CNPJ não autorizado para o serviço'
            
            # Filtra apenas os registros com CNPJs autorizados para o agrupamento
            valid_data = mun_code_df[mun_code_df['CNPJ_Autorizado']].drop('CNPJ_Autorizado', axis=1)
            
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
                        if not qpe_df.empty and 'QPE_ID' in qpe_df.columns and 'NOTA_FISCAL' in qpe_df.columns:
                            matching_rows = qpe_df[qpe_df['QPE_ID'] == invoice_number]
                            if not matching_rows.empty:
                                matching_nota = matching_rows['NOTA_FISCAL'].iloc[0]
                                return str(matching_nota).strip()
                    elif invoice_number.startswith('SPB'):
                        # Busca no SPB_consolidado
                        if not spb_df.empty and 'SPB_ID' in spb_df.columns and 'Num_Nota' in spb_df.columns:
                            matching_rows = spb_df[spb_df['SPB_ID'] == invoice_number]
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
            columns_to_include = [
                'CNPJ - WEG',
                'Municipality Code',
                'MATERIAL',
                'Invoice_Type',
                'NF',
                'Site Name - WEG 2'
            ]
            
            # Adiciona a coluna de total (que pode ter nome diferente)
            if coluna_total not in columns_to_include:
                columns_to_include.append(coluna_total)
            
            # Filtra apenas as colunas que existem no DataFrame
            columns_to_include = [col for col in columns_to_include if col in grouped_data.columns]
            
            # Reordena as colunas
            grouped_data = grouped_data.reindex(columns=columns_to_include)
            
            has_divergences = not cnpj_divergences.empty
            
            # Converter DataFrames de volta para listas de dicionários
            divergences_list = cnpj_divergences.to_dict('records') if has_divergences else []
            grouped_data_list = grouped_data.to_dict('records')
            
            logger.info(f"Verificação concluída. {len(divergences_list)} divergências encontradas.")
            logger.info(f"Foram geradas {len(grouped_data_list)} linhas após o agrupamento.")
            
            return {
                "success": True,
                "divergences": divergences_list,
                "grouped_data": grouped_data_list,
                "has_divergences": has_divergences,
                "message": f"Encontradas {len(divergences_list)} divergências de CNPJ não autorizado. Foram geradas {len(grouped_data_list)} linhas após o agrupamento."
            }
            
        except Exception as e:
            logger.error(f"Erro ao verificar códigos de município: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao verificar códigos de município: {str(e)}"
            }

    async def generate_excel_report(self, divergences, grouped_data):
        """
        Gera um relatório Excel com as divergências encontradas e dados agrupados
        
        Args:
            divergences: Lista de divergências encontradas
            grouped_data: Lista de dados agrupados
            
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("Gerando relatório Excel")
            
            # Criar DataFrames
            df_divergences = pd.DataFrame(divergences) if divergences else pd.DataFrame()
            df_grouped = pd.DataFrame(grouped_data) if grouped_data else pd.DataFrame()
            
            # Criar arquivo Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Aba de divergências (se houver)
                if not df_divergences.empty:
                    df_divergences.to_excel(
                        writer, 
                        index=False, 
                        sheet_name='Divergencias_CNPJs'
                    )
                
                # Aba de dados agrupados
                if not df_grouped.empty:
                    df_grouped.to_excel(
                        writer, 
                        index=False, 
                        sheet_name='Dados_Agrupados'
                    )
            
            # Nome do arquivo com timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Divergencias_MUN_CODE_R189_{timestamp}.xlsx"
            
            logger.info(f"Relatório gerado: {filename}")
            
            return {
                "success": True,
                "filename": filename,
                "file_content": output
            }
        
        except Exception as e:
            logger.error(f"Erro ao gerar relatório Excel: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }
            
    async def generate_report(self):
        """
        Gera o relatório de divergências entre códigos municipais e R189.
        Similar ao método generate_report do projeto desktop.
        
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("Iniciando geração do relatório MUN_CODE vs R189")
            
            # Busca os arquivos consolidados no SharePoint
            logger.info("Baixando arquivos consolidados do SharePoint")
            
            mun_code_file = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'Municipality_Code_consolidado.xlsx',
                '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            )
            
            if not mun_code_file:
                logger.error("Arquivo Municipality_Code_consolidado.xlsx não encontrado no SharePoint")
                return {
                    "success": False,
                    "error": "Arquivo Municipality_Code_consolidado.xlsx não encontrado no SharePoint"
                }
            
            r189_file = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'R189_consolidado.xlsx',
                '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            )
            
            if not r189_file:
                logger.error("Arquivo R189_consolidado.xlsx não encontrado no SharePoint")
                return {
                    "success": False,
                    "error": "Arquivo R189_consolidado.xlsx não encontrado no SharePoint"
                }
            
            # Baixa os arquivos QPE e SPB consolidados para obter os números das notas fiscais
            logger.info("Baixando arquivos QPE e SPB consolidados")
            qpe_file = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'QPE_consolidado.xlsx',
                '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            )
            
            spb_file = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'SPB_consolidado.xlsx',
                '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            )
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos consolidados")
            try:
                mun_code_df = pd.read_excel(BytesIO(mun_code_file))
                r189_df = pd.read_excel(BytesIO(r189_file))
                
                # Lê os arquivos QPE e SPB se estiverem disponíveis
                qpe_df = pd.read_excel(BytesIO(qpe_file)) if qpe_file else pd.DataFrame()
                spb_df = pd.read_excel(BytesIO(spb_file)) if spb_file else pd.DataFrame()
                
                # Converter DataFrames para listas de dicionários
                mun_code_data = mun_code_df.to_dict('records')
                r189_data = r189_df.to_dict('records')
                qpe_data = qpe_df.to_dict('records') if not qpe_df.empty else []
                spb_data = spb_df.to_dict('records') if not spb_df.empty else []
            except Exception as e:
                logger.error(f"Erro ao ler arquivos consolidados: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos consolidados: {str(e)}"
                }
            
            # Verificar divergências
            logger.info("Verificando divergências")
            result = await self.check_municipality_codes(r189_data, mun_code_data, qpe_data, spb_data)
            
            if not result["success"]:
                logger.error(f"Falha na verificação de divergências: {result.get('error')}")
                return result
            
            # Se encontrou divergências ou dados agrupados, gera o relatório Excel
            if result.get("divergences") or result.get("grouped_data"):
                logger.info("Gerando relatório Excel")
                report_result = await self.generate_excel_report(
                    result.get("divergences", []), 
                    result.get("grouped_data", [])
                )
                
                if not report_result["success"]:
                    logger.error(f"Falha na geração do relatório Excel: {report_result.get('error')}")
                    return report_result
                
                # Enviar o relatório para o SharePoint
                logger.info("Enviando relatório para o SharePoint")
                filename = report_result["filename"]
                file_content = report_result["file_content"].getvalue()
                
                # Use await aqui, pois este método é assíncrono
                success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    file_content,
                    filename,
                    '/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/MUN_CODE'
                )
                
                if not success:
                    logger.error("Falha ao enviar relatório para o SharePoint")
                    return {
                        "success": False,
                        "error": "Falha ao enviar relatório para o SharePoint"
                    }
                
                return {
                    "success": True,
                    "message": result.get("message", "") + f" Relatório gerado: {filename}"
                }
            else:
                return {
                    "success": True,
                    "message": "Validação concluída. Nenhuma divergência encontrada."
                }
                
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao gerar relatório: {str(e)}"
            }
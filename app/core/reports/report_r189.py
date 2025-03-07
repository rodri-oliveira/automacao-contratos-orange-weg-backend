import pandas as pd
from io import BytesIO
import logging
from datetime import datetime
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class ReportR189:
    """
    Classe responsável por verificar divergências no arquivo R189.
    """
    
    def __init__(self):
        self.report_name = "Relatório de Divergências R189"
        self.sharepoint_auth = SharePointAuth()
        
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
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera', 'Total', 'Valor Total']

    async def check_divergences(self, consolidated_data):
        """
        Verifica divergências entre os dados consolidados e o mapeamento esperado.
        
        Args:
            consolidated_data: Lista de dicionários com os dados consolidados do R189
            
        Returns:
            dict: Resultado da verificação com divergências encontradas
        """
        try:
            # Converter lista de dicionários para DataFrame
            df = pd.DataFrame(consolidated_data)
            
            # Validação inicial do DataFrame
            if df.empty:
                return {
                    "success": False,
                    "error": "Erro: DataFrame está vazio"
                }
            
            divergences = []
            
            # Verifica qual coluna de total está presente no DataFrame
            coluna_total_encontrada = None
            for col in self.colunas_total:
                if col in df.columns:
                    coluna_total_encontrada = col
                    break
                    
            if not coluna_total_encontrada:
                return {
                    "success": False,
                    "error": f"Erro: Nenhuma das colunas de total foi encontrada. Esperado uma das seguintes: {self.colunas_total}"
                }
            
            # Verifica se as colunas necessárias existem
            required_columns = ['CNPJ - WEG', 'Site Name - WEG 2', 'Invoice number', coluna_total_encontrada]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return {
                    "success": False,
                    "error": f"Erro: Colunas necessárias não encontradas: {', '.join(missing_columns)}"
                }
            
            # Validação de tipos de dados
            try:
                df[coluna_total_encontrada] = pd.to_numeric(df[coluna_total_encontrada], errors='coerce')
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Erro: Valores inválidos na coluna '{coluna_total_encontrada}': {str(e)}"
                }
            
            # Verifica valores nulos
            null_cnpj = df['CNPJ - WEG'].isnull().sum()
            null_site = df['Site Name - WEG 2'].isnull().sum()
            null_invoice = df['Invoice number'].isnull().sum()
            null_total = df[coluna_total_encontrada].isnull().sum()
            
            if any([null_cnpj, null_site, null_invoice, null_total]):
                return {
                    "success": False,
                    "error": (
                        "Erro: Encontrados valores nulos:\n"
                        f"CNPJ: {null_cnpj} valores nulos\n"
                        f"Site Name: {null_site} valores nulos\n"
                        f"Invoice: {null_invoice} valores nulos\n"
                        f"{coluna_total_encontrada}: {null_total} valores nulos"
                    )
                }
            
            # Itera sobre cada linha do DataFrame
            for idx, row in df.iterrows():
                cnpj = str(row['CNPJ - WEG']).strip()
                site_name = str(row['Site Name - WEG 2']).strip()
                invoice = str(row['Invoice number']).strip()
                valor = float(row[coluna_total_encontrada])
                
                # Validação do CNPJ
                if not cnpj or len(cnpj) != 18:  # Formato XX.XXX.XXX/XXXX-XX
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
                        divergences.append({
                            'Tipo': 'Site Name incorreto',
                            'Invoice Number': invoice,
                            'CNPJ': cnpj,
                            'Site Name Encontrado': site_name,
                            'Site Name Esperado': ', '.join(self.cnpj_site_mapping[cnpj]),
                            'Total Geral': valor
                        })
                else:
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
                tipo_counts = df_divergences['Tipo'].value_counts().to_dict()
                tipo_summary = "\n".join([f"- {tipo}: {count}" for tipo, count in tipo_counts.items()])
                
                return {
                    "success": True,
                    "divergences": divergences,
                    "message": f"Encontradas {len(divergences)} divergências:\n{tipo_summary}",
                    "has_divergences": True
                }
            
            return {
                "success": True,
                "divergences": [],
                "message": "Nenhuma divergência encontrada nos dados analisados",
                "has_divergences": False
            }
            
        except Exception as e:
            logger.error(f"Erro ao verificar divergências: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao verificar divergências: {str(e)}"
            }

    async def generate_excel_report(self, divergences):
        """
        Gera um relatório Excel com as divergências encontradas
        
        Args:
            divergences: Lista de divergências encontradas
            
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("Gerando relatório Excel")
            
            if not divergences:
                return {
                    "success": True,
                    "message": "Nenhuma divergência para gerar relatório",
                    "has_report": False
                }
            
            # Criar DataFrame
            df_divergences = pd.DataFrame(divergences)
            
            # Adiciona data e hora ao DataFrame
            now = datetime.now()
            df_divergences['Data Verificação'] = now.strftime('%Y-%m-%d')
            df_divergences['Hora Verificação'] = now.strftime('%H:%M:%S')
            
            # Criar arquivo Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_divergences.to_excel(writer, index=False, sheet_name='Divergencias_R189')
            
            # Nome do arquivo com timestamp
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_divergencias_r189.xlsx"
            
            logger.info(f"Relatório gerado: {filename}")
            
            return {
                "success": True,
                "filename": filename,
                "file_content": output,
                "has_report": True
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
        Gera o relatório de divergências a partir do arquivo consolidado.
        
        Returns:
            dict: Resultado da geração do relatório
        """
        try:
            logger.info("Iniciando geração do relatório R189")
            
            # Tenta baixar o arquivo consolidado
            consolidado = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'R189_consolidado.xlsx',
                '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            )
            
            if not consolidado:
                logger.error("Arquivo R189_consolidado.xlsx não encontrado no SharePoint")
                return {
                    "success": False,
                    "error": "Erro: Arquivo R189_consolidado.xlsx não encontrado no SharePoint"
                }
            
            try:
                # Lê o arquivo consolidado
                df = pd.read_excel(BytesIO(consolidado))
                
                # Verifica se existe a aba 'Consolidado_R189'
                if isinstance(df, dict) and 'Consolidado_R189' in df:
                    df = df['Consolidado_R189']
                
                # Converter DataFrame para lista de dicionários
                data = df.to_dict('records')
            except Exception as e:
                logger.error(f"Erro ao ler arquivo consolidado: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivo consolidado: {str(e)}"
                }
            
            if not data:
                logger.error("Arquivo consolidado está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo consolidado está vazio"
                }
            
            # Verifica divergências
            result = await self.check_divergences(data)
            
            if not result["success"]:
                logger.error(f"Falha na verificação de divergências: {result.get('error')}")
                return result
            
            # Se encontrou divergências, gera o relatório Excel
            if result.get("has_divergences"):
                logger.info("Gerando relatório Excel")
                report_result = await self.generate_excel_report(result.get("divergences", []))
                
                if not report_result["success"]:
                    logger.error(f"Falha na geração do relatório Excel: {report_result.get('error')}")
                    return report_result
                
                if report_result.get("has_report"):
                    # Enviar o relatório para o SharePoint
                    logger.info("Enviando relatório para o SharePoint")
                    filename = report_result["filename"]
                    file_content = report_result["file_content"].getvalue()
                    
                    # Use await aqui, pois este método é assíncrono
                    success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                        file_content,
                        filename,
                        '/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/R189'
                    )
                    
                    if not success:
                        logger.error("Falha ao enviar relatório para o SharePoint")
                        return {
                            "success": False,
                            "error": "Falha ao enviar relatório para o SharePoint"
                        }
                    
                    return {
                        "success": True,
                        "message": (
                            "Relatório de divergências gerado e salvo com sucesso!\n\n"
                            f"{result.get('message')}\n\n"
                            "O arquivo foi salvo na pasta RELATÓRIOS/R189 no SharePoint."
                        )
                    }
            
            return {
                "success": True,
                "message": result.get("message", "Validação concluída.")
            }
                
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao gerar relatório: {str(e)}"
            } 
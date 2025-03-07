from typing import Dict, Any, List, Tuple
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class DivergenceReportNFSERVR189:
    """
    Classe responsável por verificar divergências entre NFSERV e R189
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.tolerance = 0.01  # Tolerância para diferenças de valor (centavos)
        logger.info("Inicializando DivergenceReportNFSERVR189")

    async def check_divergences(self, nfserv_data: List[Dict[str, Any]] = None, r189_data: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Verifica divergências entre dados do NFSERV e R189
        """
        try:
            logger.info("Iniciando verificação de divergências entre NFSERV e R189")
            
            # Se os dados não foram fornecidos, busca do SharePoint
            if not nfserv_data or not r189_data:
                logger.info("Dados não fornecidos, buscando do SharePoint")
                nfserv_file = await self.sharepoint_auth.baixar_arquivo_sharepoint(
                    'NFSERV_consolidado.xlsx',
                    '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
                )
                
                if not nfserv_file:
                    logger.error("Arquivo NFSERV_consolidado.xlsx não encontrado no SharePoint")
                    return {
                        "success": False,
                        "error": "Arquivo NFSERV_consolidado.xlsx não encontrado no SharePoint"
                    }
                
                r189_file = await self.sharepoint_auth.baixar_arquivo_sharepoint(
                    'R189_consolidado.xlsx',
                    '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
                )
                
                if not r189_file:
                    logger.error("Arquivo R189_consolidado.xlsx não encontrado no SharePoint")
                    return {
                        "success": False,
                        "error": "Arquivo R189_consolidado.xlsx não encontrado no SharePoint"
                    }
                
                try:
                    # Lê os arquivos consolidados
                    nfserv_df = pd.read_excel(BytesIO(nfserv_file), sheet_name='Consolidado_NFSERV')
                    r189_df = pd.read_excel(BytesIO(r189_file), sheet_name='Consolidado_R189')
                    
                    # Converte DataFrames para listas de dicionários
                    nfserv_data = nfserv_df.to_dict('records')
                    r189_data = r189_df.to_dict('records')
                except Exception as e:
                    logger.error(f"Erro ao ler arquivos consolidados: {str(e)}")
                    return {
                        "success": False,
                        "error": f"Erro ao ler arquivos consolidados: {str(e)}"
                    }

            # Converter listas para DataFrames
            nfserv_df = pd.DataFrame(nfserv_data)
            r189_df = pd.DataFrame(r189_data)
            
            if not nfserv_data or not r189_data:
                return {
                    "success": False,
                    "error": "Dados NFSERV ou R189 vazios"
                }
            
            # Merge dos dados usando empresa, nota fiscal e código do município como chaves
            merged = pd.merge(
                nfserv_df,
                r189_df,
                on=['empresa', 'nota_fiscal', 'codigo_municipio'],
                how='outer',
                suffixes=('_nfserv', '_r189')
            )
            
            divergences = []
            
            for _, row in merged.iterrows():
                # Verificar notas fiscais não encontradas
                if pd.isna(row.get('valor_total_nfserv')) or pd.isna(row.get('valor_total_r189')):
                    divergences.append({
                        "tipo": "Nota Fiscal não encontrada",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "codigo_municipio": row['codigo_municipio'],
                        "cnpj_fornecedor_nfserv": row.get('cnpj_fornecedor_nfserv'),
                        "cnpj_fornecedor_r189": row.get('cnpj_fornecedor_r189'),
                        "valor_nfserv": row.get('valor_total_nfserv'),
                        "valor_r189": row.get('valor_total_r189')
                    })
                    continue

                # Verificar divergência de valores
                valor_nfserv = float(row['valor_total_nfserv'])
                valor_r189 = float(row['valor_total_r189'])
                
                if abs(valor_nfserv - valor_r189) > self.tolerance:
                    divergences.append({
                        "tipo": "Divergência de Valor",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "codigo_municipio": row['codigo_municipio'],
                        "cnpj_fornecedor_nfserv": row['cnpj_fornecedor_nfserv'],
                        "cnpj_fornecedor_r189": row['cnpj_fornecedor_r189'],
                        "valor_nfserv": valor_nfserv,
                        "valor_r189": valor_r189,
                        "diferenca": valor_nfserv - valor_r189
                    })

                # Verificar divergência de CNPJ do fornecedor
                if row['cnpj_fornecedor_nfserv'] != row['cnpj_fornecedor_r189']:
                    divergences.append({
                        "tipo": "Divergência de CNPJ",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "codigo_municipio": row['codigo_municipio'],
                        "cnpj_fornecedor_nfserv": row['cnpj_fornecedor_nfserv'],
                        "cnpj_fornecedor_r189": row['cnpj_fornecedor_r189'],
                        "valor_nfserv": valor_nfserv,
                        "valor_r189": valor_r189
                    })

            return {
                "success": True,
                "divergences": divergences,
                "summary": {
                    "total_nfserv": len(nfserv_df),
                    "total_r189": len(r189_df),
                    "total_divergencias": len(divergences),
                    "data_analise": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

        except Exception as e:
            logger.error(f"Erro ao verificar divergências: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao verificar divergências: {str(e)}"
            }

    async def generate_excel_report(self, divergences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Gera relatório Excel com as divergências encontradas
        """
        try:
            if not divergences:
                return {
                    "success": False,
                    "error": "Não há divergências para gerar relatório"
                }

            # Criar DataFrame com as divergências
            df = pd.DataFrame(divergences)
            
            # Criar arquivo Excel em memória
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Divergências')
            
            output.seek(0)
            
            # Nome do arquivo com timestamp
            filename = f"relatorio_divergencias_nfserv_r189_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Enviar para o SharePoint
            success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                output.getvalue(),
                filename,
                '/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/NFSERV_R189'
            )
            
            if success:
                return {
                    "success": True,
                    "file_content": output,
                    "filename": filename,
                    "message": f"Relatório gerado e salvo com sucesso: {filename}"
                }
            else:
                return {
                    "success": False,
                    "error": "Falha ao enviar relatório para o SharePoint"
                }

        except Exception as e:
            logger.error(f"Erro ao gerar relatório Excel: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

    async def generate_report(self) -> Dict[str, Any]:
        """
        Gera o relatório de divergências comparando NFSERV e R189.
        
        Returns:
            Dict: Resultado da geração do relatório
        """
        try:
            logger.info("Iniciando geração de relatório NFSERV x R189")
            
            # Verificar divergências
            result = await self.check_divergences()
            
            if not result["success"]:
                logger.error(f"Falha na verificação de divergências: {result.get('error')}")
                return result
            
            # Se encontrou divergências, gera o relatório Excel
            if result["divergences"]:
                report_result = await self.generate_excel_report(result["divergences"])
                
                if not report_result["success"]:
                    logger.error(f"Falha na geração do relatório Excel: {report_result.get('error')}")
                    return report_result
                
                # Retorna resultado completo
                return {
                    "success": True,
                    "message": (
                        f"Relatório de divergências gerado e salvo com sucesso!\n\n"
                        f"Resumo das divergências encontradas:\n{result['message']}\n\n"
                        f"O arquivo foi salvo na pasta RELATÓRIOS/NFSERV_R189 no SharePoint."
                    ),
                    "filename": report_result["filename"],
                    "summary": result["summary"]
                }
            else:
                logger.info("Nenhuma divergência encontrada")
                return {
                    "success": True,
                    "message": "Nenhuma divergência encontrada nos dados analisados."
                }
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": (
                    f"Erro inesperado ao gerar relatório: {str(e)}\n"
                    "Por favor, verifique:\n"
                    "1. Se os arquivos consolidados existem no SharePoint\n"
                    "2. Se você tem permissão de acesso\n"
                    "3. Se a conexão com o SharePoint está funcionando"
                )
            }

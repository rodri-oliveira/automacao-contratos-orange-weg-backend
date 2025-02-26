from typing import Dict, Any, List
import pandas as pd
from datetime import datetime
from io import BytesIO

class ReportMunCodeR189:
    """
    Classe responsável por verificar códigos de município no R189
    """
    
    def __init__(self):
        pass

    async def check_municipality_codes(
        self,
        r189_data: List[Dict[str, Any]],
        municipality_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verifica códigos de município nos dados do R189
        """
        try:
            if not r189_data or not municipality_data:
                return {
                    "success": False,
                    "error": "Dados R189 ou lista de municípios vazios"
                }

            # Converter listas para DataFrames
            r189_df = pd.DataFrame(r189_data)
            mun_df = pd.DataFrame(municipality_data)
            
            # Criar lista de códigos válidos
            valid_codes = set(mun_df['codigo_ibge'].astype(str))
            
            divergences = []
            
            # Verificar cada registro do R189
            for _, row in r189_df.iterrows():
                codigo_municipio = str(row['codigo_municipio'])
                
                if codigo_municipio not in valid_codes:
                    divergences.append({
                        "tipo": "Código de Município Inválido",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "codigo_municipio": codigo_municipio,
                        "fornecedor": row.get('fornecedor', ''),
                        "valor_total": row['valor_total']
                    })

            return {
                "success": True,
                "divergences": divergences,
                "summary": {
                    "total_registros": len(r189_df),
                    "total_divergencias": len(divergences),
                    "data_analise": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao verificar códigos de município: {str(e)}"
            }

    async def generate_excel_report(self, divergences: List[Dict[str, Any]], municipality_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Gera relatório Excel com as divergências encontradas e lista de municípios válidos
        """
        try:
            if not divergences and not municipality_data:
                return {
                    "success": False,
                    "error": "Não há dados para gerar relatório"
                }

            # Criar arquivo Excel em memória
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Aba de divergências
                if divergences:
                    div_df = pd.DataFrame(divergences)
                    div_df.to_excel(writer, index=False, sheet_name='Divergências')
                
                # Aba de municípios válidos
                if municipality_data:
                    mun_df = pd.DataFrame(municipality_data)
                    mun_df.to_excel(writer, index=False, sheet_name='Municípios Válidos')
            
            output.seek(0)
            
            return {
                "success": True,
                "file_content": output,
                "filename": f"relatorio_codigos_municipio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

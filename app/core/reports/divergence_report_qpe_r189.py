from typing import Dict, Any, List
import pandas as pd
from datetime import datetime
from io import BytesIO

class DivergenceReportQPER189:
    """
    Classe responsável por verificar divergências entre QPE e R189
    """
    
    def __init__(self):
        self.tolerance = 0.01  # Tolerância para diferenças de valor (centavos)

    async def check_divergences(self, qpe_data: List[Dict[str, Any]], r189_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica divergências entre dados do QPE e R189
        """
        try:
            if not qpe_data or not r189_data:
                return {
                    "success": False,
                    "error": "Dados QPE ou R189 vazios"
                }

            # Converter listas para DataFrames
            qpe_df = pd.DataFrame(qpe_data)
            r189_df = pd.DataFrame(r189_data)
            
            # Merge dos dados usando empresa e nota fiscal como chaves
            merged = pd.merge(
                qpe_df,
                r189_df,
                on=['empresa', 'nota_fiscal'],
                how='outer',
                suffixes=('_qpe', '_r189')
            )
            
            divergences = []
            
            for _, row in merged.iterrows():
                # Verificar notas fiscais não encontradas
                if pd.isna(row.get('valor_total_qpe')) or pd.isna(row.get('valor_total_r189')):
                    divergences.append({
                        "tipo": "Nota Fiscal não encontrada",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "fornecedor_qpe": row.get('fornecedor_qpe'),
                        "fornecedor_r189": row.get('fornecedor_r189'),
                        "valor_qpe": row.get('valor_total_qpe'),
                        "valor_r189": row.get('valor_total_r189')
                    })
                    continue

                # Verificar divergência de valores
                valor_qpe = float(row['valor_total_qpe'])
                valor_r189 = float(row['valor_total_r189'])
                
                if abs(valor_qpe - valor_r189) > self.tolerance:
                    divergences.append({
                        "tipo": "Divergência de Valor",
                        "empresa": row['empresa'],
                        "nota_fiscal": row['nota_fiscal'],
                        "fornecedor_qpe": row['fornecedor_qpe'],
                        "fornecedor_r189": row['fornecedor_r189'],
                        "valor_qpe": valor_qpe,
                        "valor_r189": valor_r189,
                        "diferenca": valor_qpe - valor_r189
                    })

            return {
                "success": True,
                "divergences": divergences,
                "summary": {
                    "total_qpe": len(qpe_df),
                    "total_r189": len(r189_df),
                    "total_divergencias": len(divergences),
                    "data_analise": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

        except Exception as e:
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
            
            return {
                "success": True,
                "file_content": output,
                "filename": f"relatorio_divergencias_qpe_r189_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

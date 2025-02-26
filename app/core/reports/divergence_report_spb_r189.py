from typing import Dict, Any, List
import pandas as pd
from datetime import datetime
from io import BytesIO

class DivergenceReportSPBR189:
    """
    Classe responsável por verificar divergências entre SPB e R189
    """
    
    def __init__(self):
        self.tolerance = 0.01  # Tolerância para diferenças de valor (centavos)

    async def check_divergences(self, spb_data: List[Dict[str, Any]], r189_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica divergências entre dados do SPB e R189
        """
        try:
            if not spb_data or not r189_data:
                return {
                    "success": False,
                    "error": "Dados SPB ou R189 vazios"
                }

            # Converter listas para DataFrames
            spb_df = pd.DataFrame(spb_data)
            r189_df = pd.DataFrame(r189_data)
            
            divergences = []
            
            # Verificar cada registro do SPB
            for _, spb_row in spb_df.iterrows():
                # Procurar nota fiscal correspondente no R189
                r189_match = r189_df[
                    (r189_df['nota_fiscal'] == spb_row['nota_fiscal']) &
                    (r189_df['cnpj'] == spb_row['cnpj'])
                ]
                
                if len(r189_match) == 0:
                    # Nota fiscal do SPB não encontrada no R189
                    divergences.append({
                        "tipo": "Nota Fiscal não encontrada no R189",
                        "spb_id": spb_row['spb_id'],
                        "nota_fiscal": spb_row['nota_fiscal'],
                        "cnpj": spb_row['cnpj'],
                        "valor_spb": spb_row['valor_total'],
                        "valor_r189": None
                    })
                else:
                    # Verificar divergência de valores
                    valor_r189 = float(r189_match.iloc[0]['valor_total'])
                    valor_spb = float(spb_row['valor_total'])
                    
                    if abs(valor_spb - valor_r189) > self.tolerance:
                        divergences.append({
                            "tipo": "Divergência de Valor",
                            "spb_id": spb_row['spb_id'],
                            "nota_fiscal": spb_row['nota_fiscal'],
                            "cnpj": spb_row['cnpj'],
                            "valor_spb": valor_spb,
                            "valor_r189": valor_r189,
                            "diferenca": valor_spb - valor_r189
                        })

            # Verificar notas fiscais no R189 que não estão no SPB
            for _, r189_row in r189_df.iterrows():
                spb_match = spb_df[
                    (spb_df['nota_fiscal'] == r189_row['nota_fiscal']) &
                    (spb_df['cnpj'] == r189_row['cnpj'])
                ]
                
                if len(spb_match) == 0:
                    divergences.append({
                        "tipo": "Nota Fiscal não encontrada no SPB",
                        "spb_id": None,
                        "nota_fiscal": r189_row['nota_fiscal'],
                        "cnpj": r189_row['cnpj'],
                        "valor_spb": None,
                        "valor_r189": float(r189_row['valor_total'])
                    })

            return {
                "success": True,
                "divergences": divergences,
                "summary": {
                    "total_spb": len(spb_df),
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
                "filename": f"relatorio_divergencias_spb_r189_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

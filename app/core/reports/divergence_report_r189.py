from typing import Dict, Any, Tuple, List
import pandas as pd
from datetime import datetime

class DivergenceReportR189:
    """
    Classe responsável por verificar divergências no arquivo R189.
    """
    
    def __init__(self):
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
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera']

    async def check_divergences(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica divergências nos dados do R189
        """
        try:
            if not data:
                return {
                    "success": False,
                    "error": "Dados vazios"
                }

            # Converter lista de dicionários para DataFrame
            df = pd.DataFrame(data)
            
            divergences = []
            
            # Verificar CNPJ e Site Name
            for _, row in df.iterrows():
                cnpj = row.get('cnpj')
                site_name = row.get('site_name')
                
                if cnpj in self.cnpj_site_mapping:
                    expected_sites = self.cnpj_site_mapping[cnpj]
                    if site_name not in expected_sites:
                        divergences.append({
                            "tipo": "Site Name Incorreto",
                            "cnpj": cnpj,
                            "site_atual": site_name,
                            "site_esperado": expected_sites[0],
                            "nota_fiscal": row.get('nota_fiscal'),
                            "valor_total": row.get('valor_total')
                        })
                else:
                    divergences.append({
                        "tipo": "CNPJ não mapeado",
                        "cnpj": cnpj,
                        "site_atual": site_name,
                        "site_esperado": "Não definido",
                        "nota_fiscal": row.get('nota_fiscal'),
                        "valor_total": row.get('valor_total')
                    })

            return {
                "success": True,
                "divergences": divergences,
                "summary": {
                    "total_analisado": len(df),
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
                "filename": f"relatorio_divergencias_r189_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao gerar relatório Excel: {str(e)}"
            }

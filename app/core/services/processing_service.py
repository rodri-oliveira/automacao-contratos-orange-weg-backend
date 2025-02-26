from typing import Dict, Any, List
from ..extractors.r189_extractor import R189Extractor
from ..extractors.qpe_extractor import QPEExtractor
from ..extractors.nfserv_extractor import NFServExtractor
from ..extractors.spb_extractor import SPBExtractor
from ..extractors.municipality_code_extractor import MunicipalityCodeExtractor
from io import BytesIO
import pandas as pd

class ProcessingService:
    def __init__(self):
        self.r189_extractor = R189Extractor()
        self.qpe_extractor = QPEExtractor()
        self.nfserv_extractor = NFServExtractor()
        self.spb_extractor = SPBExtractor()
        self.municipality_code_extractor = MunicipalityCodeExtractor()

    async def process_files(self, files: Dict[str, BytesIO]) -> Dict[str, Any]:
        """
        Processa os arquivos enviados e gera relatório de divergências
        """
        try:
            # Processar R189
            r189_result = await self.r189_extractor.extract(files.get('r189'))
            if not r189_result['success']:
                return r189_result

            # Determinar tipo de verificação baseado nos arquivos enviados
            if 'qpe' in files:
                qpe_result = await self.qpe_extractor.extract(files.get('qpe'))
                if not qpe_result['success']:
                    return qpe_result
                divergences = self._find_divergences_qpe(r189_result['data'], qpe_result['data'])
            elif 'nfserv' in files:
                nfserv_result = await self.nfserv_extractor.extract(files.get('nfserv'))
                if not nfserv_result['success']:
                    return nfserv_result
                divergences = self._find_divergences_nfserv(r189_result['data'], nfserv_result['data'])
            elif 'spb' in files:
                spb_result = await self.spb_extractor.extract(files.get('spb'))
                if not spb_result['success']:
                    return spb_result
                divergences = self._find_divergences_spb(r189_result['data'], spb_result['data'])
            else:
                # Verificar apenas o R189 (sites e CNPJs)
                divergences = self._check_r189_consistency(r189_result['data'])

            return {
                "success": True,
                "divergences": divergences
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro durante o processamento: {str(e)}"
            }

    def _check_r189_consistency(self, r189_data: List[Dict]) -> List[Dict]:
        """
        Verifica consistência dos dados do R189 (sites e CNPJs)
        """
        divergences = []
        df = pd.DataFrame(r189_data)
        
        for _, row in df.iterrows():
            cnpj = row['empresa']
            if cnpj in self.r189_extractor.cnpj_site_mapping:
                expected_sites = self.r189_extractor.cnpj_site_mapping[cnpj]
                if row['site'] not in expected_sites:
                    divergences.append({
                        "tipo": "Site incorreto",
                        "empresa": cnpj,
                        "nota_fiscal": row['nota_fiscal'],
                        "site_atual": row['site'],
                        "sites_esperados": expected_sites
                    })
            else:
                divergences.append({
                    "tipo": "CNPJ não mapeado",
                    "empresa": cnpj,
                    "nota_fiscal": row['nota_fiscal']
                })
        
        return divergences

    def _find_divergences_qpe(self, r189_data: List[Dict], qpe_data: List[Dict]) -> List[Dict]:
        """
        Encontra divergências entre os dados do R189 e QPE
        """
        divergences = []

        # Criar DataFrames para facilitar a comparação
        r189_df = pd.DataFrame(r189_data)
        qpe_df = pd.DataFrame(qpe_data)

        # Merge dos dados usando nota fiscal e empresa como chaves
        merged = pd.merge(
            r189_df, 
            qpe_df, 
            on=['empresa', 'nota_fiscal'], 
            how='outer',
            suffixes=('_r189', '_qpe')
        )

        # Encontrar divergências
        for _, row in merged.iterrows():
            if pd.isna(row.get('fornecedor_r189')) or pd.isna(row.get('fornecedor_qpe')):
                # Nota fiscal presente em um arquivo mas não no outro
                divergences.append({
                    "tipo": "Nota fiscal não encontrada",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row.get('fornecedor_r189'),
                    "fornecedor_qpe": row.get('fornecedor_qpe'),
                    "valor_r189": row.get('valor_total_r189'),
                    "valor_qpe": row.get('valor_total_qpe')
                })
            elif abs(row['valor_total_r189'] - row['valor_total_qpe']) > 0.01:
                # Divergência de valores
                divergences.append({
                    "tipo": "Divergência de valores",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row['fornecedor_r189'],
                    "fornecedor_qpe": row['fornecedor_qpe'],
                    "valor_r189": row['valor_total_r189'],
                    "valor_qpe": row['valor_total_qpe'],
                    "diferenca": row['valor_total_r189'] - row['valor_total_qpe']
                })

        return divergences

    def _find_divergences_nfserv(self, r189_data: List[Dict], nfserv_data: List[Dict]) -> List[Dict]:
        """
        Encontra divergências entre os dados do R189 e NFSERV
        """
        divergences = []
        r189_df = pd.DataFrame(r189_data)
        nfserv_df = pd.DataFrame(nfserv_data)

        # Merge dos dados
        merged = pd.merge(
            r189_df,
            nfserv_df,
            on=['empresa', 'nota_fiscal'],
            how='outer',
            suffixes=('_r189', '_nfserv')
        )

        for _, row in merged.iterrows():
            if pd.isna(row.get('fornecedor_r189')) or pd.isna(row.get('fornecedor_nfserv')):
                divergences.append({
                    "tipo": "Nota fiscal não encontrada",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row.get('fornecedor_r189'),
                    "fornecedor_nfserv": row.get('fornecedor_nfserv'),
                    "valor_r189": row.get('valor_total_r189'),
                    "valor_nfserv": row.get('valor_total_nfserv')
                })
            elif abs(row['valor_total_r189'] - row['valor_total_nfserv']) > 0.01:
                divergences.append({
                    "tipo": "Divergência de valores",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row['fornecedor_r189'],
                    "fornecedor_nfserv": row['fornecedor_nfserv'],
                    "valor_r189": row['valor_total_r189'],
                    "valor_nfserv": row['valor_total_nfserv'],
                    "diferenca": row['valor_total_r189'] - row['valor_total_nfserv']
                })

        return divergences

    def _find_divergences_spb(self, r189_data: List[Dict], spb_data: List[Dict]) -> List[Dict]:
        """
        Encontra divergências entre os dados do R189 e SPB
        """
        divergences = []
        r189_df = pd.DataFrame(r189_data)
        spb_df = pd.DataFrame(spb_data)

        # Merge dos dados
        merged = pd.merge(
            r189_df,
            spb_df,
            on=['empresa', 'nota_fiscal'],
            how='outer',
            suffixes=('_r189', '_spb')
        )

        for _, row in merged.iterrows():
            if pd.isna(row.get('fornecedor_r189')) or pd.isna(row.get('fornecedor_spb')):
                divergences.append({
                    "tipo": "Nota fiscal não encontrada",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row.get('fornecedor_r189'),
                    "fornecedor_spb": row.get('fornecedor_spb'),
                    "valor_r189": row.get('valor_total_r189'),
                    "valor_spb": row.get('valor_total_spb')
                })
            elif abs(row['valor_total_r189'] - row['valor_total_spb']) > 0.01:
                divergences.append({
                    "tipo": "Divergência de valores",
                    "empresa": row['empresa'],
                    "nota_fiscal": row['nota_fiscal'],
                    "fornecedor_r189": row['fornecedor_r189'],
                    "fornecedor_spb": row['fornecedor_spb'],
                    "valor_r189": row['valor_total_r189'],
                    "valor_spb": row['valor_total_spb'],
                    "diferenca": row['valor_total_r189'] - row['valor_total_spb']
                })

        return divergences

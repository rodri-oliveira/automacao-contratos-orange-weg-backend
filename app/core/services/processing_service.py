from typing import Dict, Any, List
from io import BytesIO
import pandas as pd
import os
import logging

from ..extractors.r189_extractor import R189Extractor
from ..extractors.qpe_extractor import QPEExtractor
from ..extractors.nfserv_extractor import NFServExtractor
from ..extractors.spb_extractor import SPBExtractor
from ..extractors.municipality_code_extractor import MunicipalityCodeExtractor
from ..sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self):
        self.r189_extractor = R189Extractor()
        self.qpe_extractor = QPEExtractor()
        self.nfserv_extractor = NFServExtractor()
        self.spb_extractor = SPBExtractor()
        self.municipality_code_extractor = MunicipalityCodeExtractor()
        self.sharepoint_client = SharePointClient()
        
        # Mapeamento de CNPJ para sites aceitos - poderá ser carregado de um arquivo de configuração
        self.cnpj_site_mapping = {}

    async def process_r189(self, file_content: BytesIO, file_name: str) -> Dict[str, Any]:
        try:
            logger.info(f"Iniciando processamento do arquivo: {file_name}")
            
            result = await self.r189_extractor.process_file(file_content)
            
            if not result["success"]:
                logger.error(f"Falha no processamento do R189: {result.get('error')}")
                return result

            # Verificar se temos o arquivo consolidado
            if "consolidated_file" not in result:
                logger.error("Arquivo consolidado não foi gerado")
                return {
                    "success": False,
                    "error": "Arquivo consolidado não foi gerado"
                }

            logger.info("Enviando arquivo consolidado para o SharePoint")
            try:
                await self.sharepoint_client.upload_file(
                    file_content=result["consolidated_file"],
                    destination_name=f"R189_consolidado_{file_name}",
                    folder_path="/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
                )
                logger.info(f"Arquivo enviado com sucesso para o SharePoint: R189_consolidado_{file_name}")
            except Exception as upload_error:
                logger.error(f"Erro ao enviar para SharePoint: {str(upload_error)}")
                return {
                    "success": False,
                    "error": f"Erro ao enviar para SharePoint: {str(upload_error)}"
                }

            return {
                "success": True,
                "message": "Arquivo processado e enviado com sucesso",
                "data": result["data"]
            }

        except Exception as e:
            logger.error(f"Erro no processamento: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def process_files(self, files: Dict[str, BytesIO]) -> Dict[str, Any]:
        """
        Processa os arquivos enviados e gera relatório de divergências
        """
        try:
            # Processar R189
            if 'r189' not in files:
                logger.error("Arquivo R189 não encontrado")
                return {
                    "success": False,
                    "error": "Arquivo R189 não encontrado"
                }
                
            logger.info("Iniciando processamento do arquivo R189")
            # Extrair dados do R189 usando o novo método process_file
            r189_result = await self.r189_extractor.process_file(files.get('r189'))
            if not r189_result['success']:
                logger.error(f"Erro no processamento do R189: {r189_result.get('error')}")
                return r189_result
                
            # Formatar dados do R189 para compatibilidade
            r189_data = []
            for item in r189_result['data']:
                r189_data.append({
                    'empresa': item['cnpj_fornecedor'],
                    'nota_fiscal': item['nota_fiscal'],
                    'site': item['site_name'],
                    'valor_total': item['valor_total'],
                    'fornecedor_r189': item['cnpj_fornecedor']
                })

            # Determinar tipo de verificação
            if 'qpe' in files:
                qpe_result = await self.qpe_extractor.extract(files.get('qpe'))
                if not qpe_result['success']:
                    return qpe_result
                divergences = self._find_divergences_qpe(r189_data, qpe_result['data'])
            elif 'nfserv' in files:
                nfserv_result = await self.nfserv_extractor.extract(files.get('nfserv'))
                if not nfserv_result['success']:
                    return nfserv_result
                divergences = self._find_divergences_nfserv(r189_data, nfserv_result['data'])
            elif 'spb' in files:
                spb_result = await self.spb_extractor.extract(files.get('spb'))
                if not spb_result['success']:
                    return spb_result
                divergences = self._find_divergences_spb(r189_data, spb_result['data'])
            else:
                # Verificar apenas o R189 (sites e CNPJs)
                divergences = self._check_r189_consistency(r189_data)

            logger.info("Processamento concluído com sucesso")
            return {
                "success": True,
                "divergences": divergences
            }

        except Exception as e:
            logger.error(f"Erro durante o processamento: {str(e)}")
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
        
        # Se o mapeamento não estiver carregado, carregá-lo
        if not self.cnpj_site_mapping:
            self._load_cnpj_mapping()
        
        for _, row in df.iterrows():
            cnpj = row['empresa']
            if cnpj in self.cnpj_site_mapping:
                expected_sites = self.cnpj_site_mapping[cnpj]
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
        
    def _load_cnpj_mapping(self):
        """
        Carrega o mapeamento de CNPJ para sites aceitos.
        Pode ser implementado para carregar de um arquivo Excel, banco de dados, etc.
        """
        # Exemplo simples - em produção deve ser carregado de uma fonte externa
        self.cnpj_site_mapping = {
            "12345678000190": ["SITE1", "SITE2"],
            "98765432000190": ["SITE3", "SITE4"],
            # Adicionar outros mapeamentos conforme necessário
        }

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
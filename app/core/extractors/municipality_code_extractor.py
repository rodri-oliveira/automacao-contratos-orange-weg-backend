import os
from io import BytesIO
import pandas as pd
import logging
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class MunicipalityCodeExtractor:
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa um arquivo Municipality Code.
        """
        try:
            logger.info("Iniciando processamento do arquivo Municipality Code")
            resultado = await self.consolidar_municipality_code(file_content)
            
            return {
                "success": True,
                "data": {
                    "arquivo_consolidado": resultado
                }
            }
        except Exception as e:
            logger.error(f"Erro ao processar arquivo Municipality Code: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def consolidar_municipality_code(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida o arquivo Municipality Code com colunas específicas e trata valores vazios.
        """
        try:
            logger.info("Iniciando consolidação do Municipality Code")
            
            # Lê o arquivo Excel
            df = pd.read_excel(
                conteudo,
                sheet_name=None,
                na_values=['', ' '],
                keep_default_na=True,
                header=12
            )

            if 'BRASIL' not in df:
                raise ValueError("Aba 'BRASIL' não encontrada no arquivo")
            
            df_brasil = df['BRASIL']

            # Colunas necessárias
            colunas_necessarias = [
                'CNPJ - WEG',
                'Invoice number',
                'Municipality Code',
                'Invoice Type',
                'Site Name - WEG 2',
                'Total Geral'
            ]
            
            # Validação das colunas
            colunas_faltantes = [col for col in colunas_necessarias if col not in df_brasil.columns]
            if colunas_faltantes:
                raise ValueError(f"Colunas faltantes: {colunas_faltantes}")
            
            df_consolidado = df_brasil[colunas_necessarias].copy()

            # Tratamento dos dados
            df_consolidado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']] = \
                df_consolidado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']].ffill()

            df_resultado = df_consolidado[df_consolidado['Invoice Type'] == 'SRV'].copy()
            df_resultado = df_resultado.dropna(subset=[
                'CNPJ - WEG', 'Invoice number', 'Municipality Code', 'Total Geral'
            ])
            df_resultado = df_resultado.drop('Invoice Type', axis=1)

            # Gerar arquivo consolidado
            arquivo_consolidado = BytesIO()
            with pd.ExcelWriter(arquivo_consolidado, engine='xlsxwriter') as writer:
                df_resultado.to_excel(writer, index=False, sheet_name='Municipality_Code_consolidado')
            
            arquivo_consolidado.seek(0)
            logger.info("Consolidação do Municipality Code concluída com sucesso")
            
            return arquivo_consolidado
            
        except Exception as e:
            logger.error(f"Erro na consolidação do Municipality Code: {str(e)}")
            raise

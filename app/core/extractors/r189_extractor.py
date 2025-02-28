import os
import tempfile
from io import BytesIO
import pandas as pd
from pyxlsb import open_workbook
from app.core.auth import SharePointAuth  # Importa a classe SharePointAuth
import uuid
import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class R189Extractor:
    def __init__(self):
        # Instancia a classe SharePointAuth uma vez
        self.sharepoint_auth = SharePointAuth()

    async def process_file(self, file_content: BytesIO) -> Dict[str, Any]:
        """Processa um arquivo R189"""
        try:
            self.logger.info("Iniciando processamento do arquivo R189")
            consolidated_data = await self.consolidar_r189(file_content)
            
            if consolidated_data is None:
                return {
                    "success": False,
                    "error": "Falha ao consolidar arquivo R189"
                }

            # Gera o arquivo consolidado em formato BytesIO
            arquivo_consolidado = BytesIO()
            with pd.ExcelWriter(arquivo_consolidado, engine='xlsxwriter') as writer:
                consolidated_data.to_excel(writer, index=False, sheet_name='Consolidado_R189')
            
            arquivo_consolidado.seek(0)

            return {
                "success": True,
                "data": consolidated_data,
                "consolidated_file": arquivo_consolidado
            }

        except Exception as e:
            self.logger.error(f"Erro no processamento do arquivo R189: {str(e)}")
            return {
                "success": False,
                "error": f"Erro ao processar arquivo: {str(e)}"
            }

    async def extract_data(self, file_content: BytesIO) -> Dict[str, Any]:
        """
        Extrai dados do arquivo R189 consolidado
        
        Args:
            file_content: BytesIO contendo o arquivo Excel consolidado
            
        Returns:
            Dicionário com status de sucesso e dados extraídos ou mensagem de erro
        """
        try:
            logger.info("Iniciando extração de dados do arquivo consolidado")
            # Lê o arquivo consolidado
            df = pd.read_excel(file_content, sheet_name='Consolidado_R189')
            
            # Converte os dados para o formato esperado
            dados = []
            for _, row in df.iterrows():
                dados.append({
                    'cnpj_fornecedor': str(row['CNPJ - WEG']),
                    'nota_fiscal': str(row['Invoice number']),
                    'site_name': str(row['Site Name - WEG 2']),
                    'valor_total': float(row.iloc[3]) if pd.notna(row.iloc[3]) else 0.0,
                })
            
            logger.info(f"Dados extraídos com sucesso: {len(dados)} registros")
            return {
                "success": True,
                "data": dados,
                "count": len(dados)
            }
            
        except Exception as e:
            logger.error(f"Erro na extração de dados: {str(e)}")
            return {
                "success": False,
                "error": f"Erro ao extrair dados: {str(e)}",
                "details": str(e)
            }

    async def consolidar_r189(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida o arquivo R189 com colunas específicas e trata valores vazios de CNPJ.
        
        Args:
            conteudo: BytesIO contendo o arquivo Excel
            
        Returns:
            BytesIO contendo o arquivo consolidado
        """
        try:
            logger.info("Iniciando consolidação do arquivo R189")
            # Lê o arquivo diretamente do BytesIO
            df = pd.read_excel(
                conteudo,
                sheet_name=None,  # Lê todas as abas
                na_values=['', ' '],
                keep_default_na=True,
                header=12  # Linha 13 como cabeçalho
            )

            # Verifica se a aba 'BRASIL' existe
            if 'BRASIL' not in df:
                raise ValueError("A aba 'BRASIL' não foi encontrada no arquivo Excel.")
            
            # Obtém os dados apenas da aba 'BRASIL'
            df_brasil = df['BRASIL']

            # Combina todas as abas em um único DataFrame
            df_consolidado = df_brasil.copy()

            # Seleciona apenas as colunas necessárias
            colunas_necessarias = [
                'CNPJ - WEG',
                'Invoice number',
                'Site Name - WEG 2',
                'Total Geral',
                'Account number'
            ]
            
            # Verifica se todas as colunas necessárias existem
            colunas_faltantes = [col for col in colunas_necessarias if col not in df_consolidado.columns]
            if colunas_faltantes:
                raise ValueError(f"Colunas faltantes no arquivo Excel: {colunas_faltantes}")
            
            # Seleciona apenas as colunas necessárias
            df_resultado = df_consolidado[colunas_necessarias].copy()
            
            # Identifica linhas onde Account number NÃO contém a string 'Total'
            linhas_sem_total = ~df_resultado['Account number'].astype(str).str.contains('Total', na=True)
            
            # Aplica o ffill apenas nas linhas onde Account number NÃO contém 'Total'
            df_resultado.loc[linhas_sem_total, 'Invoice number'] = df_resultado.loc[linhas_sem_total, 'Invoice number'].ffill()
            
            # Preenche outros valores vazios
            df_resultado[['CNPJ - WEG', 'Site Name - WEG 2']] = df_resultado[['CNPJ - WEG', 'Site Name - WEG 2']].ffill()
            
            # Remove linhas que ainda possuem valores NaN nas colunas principais
            df_resultado = df_resultado.dropna(subset=['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2', 'Total Geral'])

            # Remove a coluna Account number antes do agrupamento
            df_resultado = df_resultado.drop('Account number', axis=1)

            # Agrupa por todas as colunas exceto 'Total Geral' e soma os valores
            df_resultado = df_resultado.groupby(['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2'], as_index=False)['Total Geral'].sum()

            # Gera o arquivo consolidado em formato BytesIO
            arquivo_consolidado = BytesIO()
            with pd.ExcelWriter(arquivo_consolidado, engine='xlsxwriter') as writer:
                df_resultado.to_excel(writer, index=False, sheet_name='Consolidado_R189')
            
            arquivo_consolidado.seek(0)
            
            return arquivo_consolidado
            
        except Exception as e:
            logger.error(f"❌ Erro ao consolidar arquivo R189: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def _process_dataframe(self, df: pd.DataFrame, total_column: str) -> pd.DataFrame:
        # Processamento do DataFrame
        df['Invoice number'] = df['Invoice number'].ffill()
        df[['CNPJ - WEG', 'Site Name - WEG 2']] = df[['CNPJ - WEG', 'Site Name - WEG 2']].ffill()
        
        # Remover linhas com valores ausentes
        df = df.dropna(subset=['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2', total_column])
        
        # Agrupar e somar
        return df.groupby(
            ['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2'],
            as_index=False
        )[total_column].sum()


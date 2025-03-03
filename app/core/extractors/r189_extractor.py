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
        self.sharepoint_auth = SharePointAuth()
        logger.info("R189Extractor inicializado")

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

    def consolidar_r189(self, conteudo: BytesIO) -> BytesIO:
        """Consolida um arquivo R189."""
        try:
            logger.info("Iniciando consolidação do arquivo R189")
            
            # Lê o arquivo Excel
            df = pd.read_excel(
                conteudo,
                sheet_name=None,
                na_values=['', ' '],
                keep_default_na=True,
                header=12
            )
            
            logger.info("Arquivo lido com sucesso")

            # Verifica se a aba 'BRASIL' existe
            if 'BRASIL' not in df:
                raise ValueError("Aba 'BRASIL' não encontrada")

            # Processa os dados
            df_brasil = df['BRASIL']
            df_consolidado = df_brasil.copy()
            
            # Seleciona e verifica colunas
            colunas_necessarias = [
                'CNPJ - WEG',
                'Invoice number',
                'Site Name - WEG 2',
                'Total Geral',
                'Account number'
            ]
            
            colunas_faltantes = [col for col in colunas_necessarias if col not in df_consolidado.columns]
            if colunas_faltantes:
                raise ValueError(f"Colunas faltantes: {colunas_faltantes}")
            
            # Processa o DataFrame
            df_resultado = df_consolidado[colunas_necessarias].copy()
            df_resultado = df_resultado.groupby(
                ['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2'], 
                as_index=False
            )['Total Geral'].sum()
            
            # Gera arquivo Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_resultado.to_excel(writer, index=False, sheet_name='Consolidado_R189')
            
            output.seek(0)
            logger.info("Consolidação concluída com sucesso")
            return output

        except Exception as e:
            logger.error(f"Erro ao consolidar R189: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def process_selected_files(self, selected_files: List[str]) -> Dict[str, Any]:
        try:
            logger.info(f"Iniciando processamento de {len(selected_files)} arquivos R189")
            
            if not selected_files:
                return {
                    "success": False,
                    "error": "Nenhum arquivo selecionado para processamento"
                }

            arquivos_processados = []
            for arquivo in selected_files:
                try:
                    logger.info(f"Processando arquivo: {arquivo}")
                    
                    # Download do arquivo
                    content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                        arquivo,
                        "/teams/BR-TI-TIN/AutomaoFinanas/R189"
                    )
                    
                    if not content:
                        logger.error(f"Falha ao baixar arquivo: {arquivo}")
                        continue

                    # Consolida o arquivo
                    arquivo_consolidado = self.consolidar_r189(content)
                    
                    if arquivo_consolidado:
                        # Nome do arquivo consolidado
                        nome_consolidado = f"R189_consolidado_{uuid.uuid4().hex[:8]}.xlsx"
                        logger.info(f"Arquivo consolidado gerado: {nome_consolidado}")
                        
                        # Converte BytesIO para bytes
                        arquivo_bytes = arquivo_consolidado.getvalue()
                        logger.info(f"Tamanho do arquivo consolidado: {len(arquivo_bytes)} bytes")
                        
                        # Configuração para upload
                        destino = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
                        logger.info(f"Enviando para: {destino}/{nome_consolidado}")
                        
                        # Envia para o SharePoint
                        success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                            arquivo_bytes,
                            nome_consolidado,
                            destino
                        )
                        
                        if success:
                            logger.info(f"Arquivo {nome_consolidado} enviado com sucesso")
                            arquivos_processados.append({
                                "nome_original": arquivo,
                                "nome_consolidado": nome_consolidado,
                                "status": "Processado com sucesso"
                            })
                        else:
                            raise Exception(f"Falha ao enviar arquivo {nome_consolidado}")
                        
                except Exception as e:
                    logger.error(f"Erro ao processar arquivo {arquivo}: {str(e)}")
                    logger.error(traceback.format_exc())
                    arquivos_processados.append({
                        "nome": arquivo,
                        "status": f"Erro: {str(e)}"
                    })

            return {
                "success": True,
                "message": f"Processados {len(arquivos_processados)} arquivos",
                "arquivos": arquivos_processados
            }

        except Exception as e:
            logger.error(f"Erro no processamento em lote: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

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


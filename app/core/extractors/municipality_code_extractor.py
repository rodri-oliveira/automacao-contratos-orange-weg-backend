import os
from io import BytesIO
import pandas as pd
import logging
import traceback
from app.core.auth import SharePointAuth
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MunicipalityCodeExtractor:
    def __init__(self):
        logger.info("=== INICIALIZANDO MUNICIPALITY CODE EXTRACTOR ===")
        self.sharepoint_auth = SharePointAuth()
        logger.info("SharePointAuth inicializado no MunicipalityCodeExtractor")

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa o arquivo Excel e extrai os dados necessários.
        """
        try:
            logger.info("Iniciando processamento do arquivo Municipality Code")
            resultado = await self.consolidar_municipality_code(file_content)
            
            if not resultado:
                logger.error("Falha ao consolidar arquivo Municipality Code")
                raise ValueError("Falha ao consolidar arquivo Municipality Code")
                
            logger.info("Processamento concluído com sucesso")
            return {
                "success": True,
                "data": {
                    "arquivo_consolidado": resultado
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo Municipality Code: {str(e)}")
            logger.error(traceback.format_exc())
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
            
            # Enviar o arquivo consolidado para o SharePoint com sobrescrita
            nome_arquivo_consolidado = 'Municipality_Code_consolidado.xlsx'
            pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            
            logger.info(f"Enviando arquivo consolidado para o SharePoint: {nome_arquivo_consolidado}")
            logger.info(f"Pasta destino: {pasta_consolidado}")
            logger.info(f"Tamanho do arquivo: {arquivo_consolidado.getbuffer().nbytes} bytes")
            
            try:
                # Usar o método enviar_arquivo_sharepoint com parâmetro de sobrescrita
                success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    arquivo_consolidado.getvalue(),
                    nome_arquivo_consolidado,
                    pasta_consolidado
                )
                
                if success:
                    logger.info("Arquivo consolidado enviado com sucesso para o SharePoint")
                else:
                    logger.error("Falha ao enviar arquivo consolidado para o SharePoint")
            except Exception as e:
                logger.error(f"Exceção ao enviar arquivo para SharePoint: {str(e)}")
                logger.error(traceback.format_exc())
            
            arquivo_consolidado.seek(0)
            return arquivo_consolidado
            
        except Exception as e:
            logger.error(f"Erro na consolidação do Municipality Code: {str(e)}")
            raise

    async def process_selected_files(self, selected_files: List[str]) -> Dict[str, Any]:
        """
        Processa os arquivos Municipality Code selecionados, consolida e envia para o SharePoint.
        """
        try:
            logger.info(f"=== INICIANDO PROCESSAMENTO DE {len(selected_files)} ARQUIVOS MUNICIPALITY CODE ===")
            logger.info(f"Arquivos selecionados: {selected_files}")
            
            if not selected_files:
                logger.error("Nenhum arquivo selecionado para processamento")
                return {
                    "success": False,
                    "error": "Nenhum arquivo selecionado para processamento"
                }

            # Obter o conteúdo de cada arquivo do SharePoint
            excel_files = []
            for arquivo in selected_files:
                try:
                    logger.info(f"Baixando arquivo: {arquivo}")
                    
                    # Baixar arquivo - IMPORTANTE: Não use await aqui
                    content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                        arquivo,
                        "/teams/BR-TI-TIN/AutomaoFinanas/R189"  # MUN_CODE usa a mesma pasta do R189
                    )
                    
                    if content:
                        logger.info(f"Arquivo {arquivo} baixado com sucesso: {len(content)} bytes")
                        excel_files.append(BytesIO(content))
                    else:
                        logger.error(f"Falha ao baixar arquivo: {arquivo}")
                except Exception as e:
                    logger.error(f"Erro ao baixar arquivo {arquivo}: {str(e)}")
                    logger.error(traceback.format_exc())

            if not excel_files:
                logger.error("Nenhum arquivo foi baixado com sucesso")
                return {
                    "success": False,
                    "error": "Nenhum arquivo foi baixado com sucesso"
                }

            # Processar o primeiro arquivo (ou combinar múltiplos se necessário)
            try:
                logger.info(f"Processando arquivo Municipality Code")
                excel_output = await self.consolidar_municipality_code(excel_files[0])
                
                if not excel_output:
                    logger.error("Falha ao consolidar arquivo Municipality Code - retorno nulo")
                    raise ValueError("Falha ao consolidar arquivo Municipality Code")
                    
                logger.info("Consolidação concluída com sucesso")
                
                # Enviar para o SharePoint com sobrescrita explícita
                nome_consolidado = "Municipality_Code_consolidado.xlsx"
                destino = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
                
                logger.info(f"Enviando arquivo consolidado para o SharePoint: {nome_consolidado}")
                logger.info(f"Pasta destino: {destino}")
                
                # Enviar para o SharePoint - IMPORTANTE: Use await aqui
                success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    excel_output.getvalue(),
                    nome_consolidado,
                    destino
                )
                
                if success:
                    logger.info("Arquivo consolidado enviado com sucesso para o SharePoint")
                    return {
                        "success": True,
                        "message": "Arquivos Municipality Code processados e consolidados com sucesso",
                        "file_name": nome_consolidado
                    }
                else:
                    logger.error("Falha ao enviar arquivo consolidado para o SharePoint")
                    return {
                        "success": False,
                        "error": "Falha ao enviar arquivo consolidado para o SharePoint"
                    }
                    
            except Exception as e:
                logger.error(f"Erro na consolidação: {str(e)}")
                logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "error": str(e)
                }
                
        except Exception as e:
            logger.error(f"Erro no processamento: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

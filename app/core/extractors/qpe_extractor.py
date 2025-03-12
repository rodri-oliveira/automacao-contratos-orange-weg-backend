import os
from io import BytesIO
import pandas as pd
import PyPDF2
import re
import traceback
import logging
from app.core.auth import SharePointAuth
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class QPEExtractor:
    def __init__(self):
        logger.info("=== INICIALIZANDO QPE EXTRACTOR ===")
        self.sharepoint_auth = SharePointAuth()
        logger.info("SharePointAuth inicializado no QPEExtractor")

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa o arquivo PDF e extrai os dados necessários.
        """
        try:
            logger.info("Iniciando processamento do arquivo QPE")
            dados = self.extrair_dados_pdf(file_content)
            
            if not dados:
                logger.error("Não foi possível extrair dados do PDF")
                raise ValueError("Não foi possível extrair dados do PDF")
            
            logger.info(f"Dados extraídos com sucesso: {dados}")
            return {
                "success": True,
                "data": dados
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo QPE: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    def extrair_dados_pdf(self, pdf_file: BytesIO) -> dict:
        """
        Extrai os dados necessários do arquivo PDF.
        """
        try:
            logger.info("Iniciando extração de dados do PDF")
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extrair texto da primeira página
            texto_pagina1 = pdf_reader.pages[0].extract_text()
            
            # Extrair texto da segunda página (se existir)
            texto_pagina2 = pdf_reader.pages[1].extract_text() if len(pdf_reader.pages) > 1 else ""
            
            # Texto combinado para busca
            texto_combinado = texto_pagina1 + "\n" + texto_pagina2

            logger.info("=== TEXTO EXTRAÍDO DO PDF ===")
            logger.info(texto_combinado[:500] + "..." if len(texto_combinado) > 500 else texto_combinado)
            logger.info("============================")
            
            # Extrair CNPJ do Tomador de Serviços
            padrao_cnpj = r'TOMADOR DE SERVIÇOS.*?\n.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'
            cnpj_match = re.search(padrao_cnpj, texto_combinado, re.DOTALL)
            cnpj = cnpj_match.group(1) if cnpj_match else None
            logger.info(f"CNPJ extraído: {cnpj}")
            
            # Extrair Cidade
            padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
            cidade_match = re.search(padrao_cidade, texto_combinado)
            cidade = cidade_match.group(1).strip() if cidade_match else None
            logger.info(f"Cidade extraída: {cidade}")
            
            # Extrair QPE_ID 
            padrao_qpe = r'(QPE-\d+)'
            qpe_match = re.search(padrao_qpe, texto_combinado)
            qpe_id = qpe_match.group(1) if qpe_match else None
            logger.info(f"QPE_ID extraído: {qpe_id}")
            
            # Extrair Valor Total
            padrao_valor = r'VALOR DO DOCUMENTO\s*([\d.,]+)'
            valor_match = re.search(padrao_valor, texto_combinado)
            valor_total = valor_match.group(1).replace('.', '').replace(',', '.') if valor_match else 0.00
            logger.info(f"Valor Total extraído: {valor_total}")
            
            # Extrair Número da Nota Fiscal
            padrao_nota_fiscal = r'GERADOR(\d{7})'
            nota_fiscal_match = re.search(padrao_nota_fiscal, texto_combinado)
            nota_fiscal = nota_fiscal_match.group(1) if nota_fiscal_match else None
            logger.info(f"Nota Fiscal extraída: {nota_fiscal}")
            
            dados = {
                'CNPJ': cnpj,
                'QPE_ID': qpe_id,
                'NOTA_FISCAL': nota_fiscal,
                'VALOR_TOTAL': float(valor_total),
                'CIDADE': cidade
            }
            
            logger.info(f"Dados extraídos com sucesso: {dados}")
            return dados
            
        except Exception as e:
            logger.error(f"Erro ao extrair dados do PDF: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def consolidar_qpe(self, pdf_files: list) -> BytesIO:
        """
        Consolida os dados dos PDFs selecionados em um novo arquivo Excel.
        """
        logger.info(f"=== INICIANDO CONSOLIDAÇÃO DE {len(pdf_files)} ARQUIVOS QPE ===")
        dados_consolidados = []
        pasta_qpe = '/teams/BR-TI-TIN/AutomaoFinanas/QPE'
        pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
        
        for i, pdf_file in enumerate(pdf_files):
            try:
                logger.info(f"Processando arquivo {i+1}/{len(pdf_files)}")
                
                # Se for string, é um nome de arquivo para baixar
                if isinstance(pdf_file, str):
                    logger.info(f"Arquivo é uma string: {pdf_file}")
                    token = self.sharepoint_auth.acquire_token()
                    if not token:
                        logger.error("Falha ao obter token para download")
                        raise Exception("Falha ao obter token para download")

                    # Download do arquivo usando SharePointAuth
                    logger.info(f"Baixando arquivo do SharePoint: {pdf_file}")
                    pdf_content = await self.sharepoint_auth.baixar_arquivo_sharepoint(
                        pdf_file,
                        pasta_qpe
                    )
                    
                    if not pdf_content:
                        logger.error(f"Falha ao baixar arquivo: {pdf_file}")
                        continue
                        
                    logger.info(f"Arquivo baixado com sucesso: {len(pdf_content)} bytes")
                    pdf_content_io = BytesIO(pdf_content)
                else:
                    # Já é um BytesIO
                    logger.info("Arquivo já é um BytesIO")
                    pdf_content_io = pdf_file
                
                # Extrair dados
                logger.info("Extraindo dados do PDF")
                dados = self.extrair_dados_pdf(pdf_content_io)
                if dados:
                    logger.info(f"Dados extraídos com sucesso: {dados}")
                    dados_consolidados.append(dados)
                else:
                    logger.warning("Nenhum dado extraído deste PDF")
                
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {i+1}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        if not dados_consolidados:
            logger.error("Nenhum dado foi extraído dos PDFs")
            raise ValueError("Nenhum dado foi extraído dos PDFs")

        # Criar DataFrame e arquivo Excel
        logger.info(f"Criando DataFrame com {len(dados_consolidados)} registros")
        df = pd.DataFrame(dados_consolidados)
        excel_output = BytesIO()
        
        logger.info("Criando arquivo Excel")
        with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='QPE_Consolidado')
        
        excel_output.seek(0)
        logger.info(f"Arquivo Excel criado: {excel_output.getbuffer().nbytes} bytes")
        
        # Enviar o arquivo consolidado para o SharePoint
        nome_arquivo_consolidado = 'QPE_consolidado.xlsx'
        logger.info(f"Enviando arquivo consolidado para o SharePoint: {nome_arquivo_consolidado}")
        logger.info(f"Pasta destino: {pasta_consolidado}")
        logger.info(f"Tamanho do arquivo: {excel_output.getbuffer().nbytes} bytes")
        
        try:
            success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                excel_output.getvalue(),
                nome_arquivo_consolidado,
                pasta_consolidado
            )
            
            if success:
                logger.info("Arquivo consolidado enviado com sucesso para o SharePoint")
            else:
                logger.error("Falha ao enviar arquivo consolidado para o SharePoint")
                logger.error("Retorno da função enviar_arquivo_sharepoint: False")
        except Exception as e:
            logger.error(f"Exceção ao enviar arquivo para SharePoint: {str(e)}")
            logger.error(traceback.format_exc())
        
        excel_output.seek(0)
        return excel_output

    async def process_selected_files(self, selected_files: List[str]) -> Dict[str, Any]:
        """
        Processa os arquivos QPE selecionados, consolida e envia para o SharePoint.
        """
        try:
            logger.info(f"=== INICIANDO PROCESSAMENTO DE {len(selected_files)} ARQUIVOS QPE ===")
            logger.info(f"Arquivos selecionados: {selected_files}")
            
            if not selected_files:
                logger.error("Nenhum arquivo selecionado para processamento")
                return {
                    "success": False,
                    "error": "Nenhum arquivo selecionado para processamento"
                }

            # Obter o conteúdo de cada arquivo do SharePoint
            pdf_files = []
            for arquivo in selected_files:
                try:
                    logger.info(f"Baixando arquivo: {arquivo}")
                    
                    # Baixar arquivo - IMPORTANTE: Não use await aqui
                    content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                        arquivo,
                        "/teams/BR-TI-TIN/AutomaoFinanas/QPE"
                    )
                    
                    if content:
                        logger.info(f"Arquivo {arquivo} baixado com sucesso: {len(content)} bytes")
                        pdf_files.append(BytesIO(content))
                    else:
                        logger.error(f"Falha ao baixar arquivo: {arquivo}")
                except Exception as e:
                    logger.error(f"Erro ao baixar arquivo {arquivo}: {str(e)}")
                    logger.error(traceback.format_exc())

            if not pdf_files:
                logger.error("Nenhum arquivo foi baixado com sucesso")
                return {
                    "success": False,
                    "error": "Nenhum arquivo foi baixado com sucesso"
                }

            # Consolidar os arquivos
            try:
                logger.info(f"Consolidando {len(pdf_files)} arquivos QPE")
                excel_output = await self.consolidar_qpe(pdf_files)
                
                if not excel_output:
                    logger.error("Falha ao consolidar arquivos QPE - retorno nulo")
                    raise ValueError("Falha ao consolidar arquivos QPE")
                    
                logger.info("Consolidação concluída com sucesso")
                
                # Enviar para o SharePoint
                nome_consolidado = "QPE_consolidado.xlsx"
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
                        "message": "Arquivos QPE processados e consolidados com sucesso",
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

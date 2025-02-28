import os
from io import BytesIO
import pandas as pd
import PyPDF2
import re
import traceback
from app.core.sharepoint import SharePointClient
from typing import Dict, Any
import logging
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class NFServExtractor:
    def __init__(self, input_file: str = None, output_dir: str = None):
        self.input_file = input_file
        self.output_dir = output_dir or (os.path.dirname(input_file) if input_file else None)
        self.sharepoint = SharePointClient()
        self.sharepoint_auth = SharePointAuth()

    async def extract(self, file_content: BytesIO) -> Dict[str, Any]:
        """
        Extrai dados do arquivo NFSERV
        """
        try:
            dados = self.extrair_dados_pdf(file_content)
            return {
                "success": True,
                "data": [dados]  # Retorna uma lista para manter consistência com outros extractors
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao processar arquivo NFSERV: {str(e)}"
            }

    def extrair_dados_pdf(self, pdf_file: BytesIO) -> dict:
        """
        Extrai os dados necessários do arquivo PDF.
        """
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extrair texto da primeira página
            texto_pagina1 = pdf_reader.pages[0].extract_text()
            
            # Extrair texto da segunda página (se existir)
            texto_pagina2 = pdf_reader.pages[1].extract_text() if len(pdf_reader.pages) > 1 else ""
            
            # Texto combinado para busca
            texto_combinado = texto_pagina1 + "\n" + texto_pagina2

            # Extrair NFSERV_ID
            padrao_nfserv = r'N\.\s*CONTROLE:\s*(?:[A-Z]{3}_)?([A-Z]{3}-\d{6})'  # Ajustado para capturar somente XXX-000000
            nfserv_match = re.search(padrao_nfserv, texto_combinado)
            nfserv_id = nfserv_match.group(1) if nfserv_match else "ID NÃO ENCONTRADO"
            
            # Extrair CNPJ
            padrao_cnpj = r'CNPJ:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'
            cnpj_match = re.search(padrao_cnpj, texto_combinado, re.DOTALL)
            cnpj = cnpj_match.group(1) if cnpj_match else None
            
            # Extrair Cidade
            padrao_cidade = r'CIDADE\s+([A-ZÀ-Ú\s]+)\s+ESTADO'  # Capturar apenas CIDADE seguido do nome
            cidade_match = re.search(padrao_cidade, texto_combinado)
            cidade = cidade_match.group(1).strip() if cidade_match else None
            
            # Extrair Valor Total
            padrao_valor = r'VALOR DO DOCUMENTO\s*([\d.,]+)'
            valor_match = re.search(padrao_valor, texto_combinado)
            valor_total = float(valor_match.group(1).replace('.', '').replace(',', '.')) if valor_match else 0.00
            
            dados = {
                'cnpj_fornecedor': cnpj,  # Ajustado para manter consistência com outros extractors
                'nota_fiscal': nfserv_id,  # Ajustado para manter consistência com outros extractors
                'valor_total': valor_total,
                'cidade': cidade
            }
            
            # Debug prints
            print(f"CNPJ: {cnpj}")
            print(f"NFSERV_ID: {nfserv_id}")
            print(f"Valor Total: {valor_total}")
            print(f"Cidade: {cidade}")
            
            return dados
            
        except Exception as e:
            print(f"❌ Erro ao extrair dados do PDF: {str(e)}")
            print(traceback.format_exc())
            raise

    async def consolidar_nfserv(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida os dados do NFSERV em um novo arquivo.
        """
        try:
            logger.info("Iniciando consolidação do NFSERV")
            output = BytesIO()
            return output
        except Exception as e:
            logger.error(f"Erro na consolidação do NFSERV: {str(e)}")
            raise

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa um arquivo NFSERV.
        """
        try:
            logger.info("Iniciando processamento do arquivo NFSERV")
            resultado = await self.consolidar_nfserv(file_content)
            
            return {
                "success": True,
                "data": {
                    "arquivo_consolidado": resultado
                }
            }
        except Exception as e:
            logger.error(f"Erro ao processar arquivo NFSERV: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

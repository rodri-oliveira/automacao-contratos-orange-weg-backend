import os
from io import BytesIO
import pandas as pd
import PyPDF2
import re
import traceback
from app.core.sharepoint import SharePointClient
import logging
from app.core.auth import SharePointAuth

logger = logging.getLogger(__name__)

class SPBExtractor:
    def __init__(self, input_file: str = None, output_dir: str = None):
        self.input_file = input_file
        self.output_dir = output_dir or (os.path.dirname(input_file) if input_file else None)
        self.sharepoint = SharePointClient()
        self.sharepoint_auth = SharePointAuth()

    def extrair_dados_pdf(self, pdf_file: BytesIO) -> dict:
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            texto_pagina1 = pdf_reader.pages[0].extract_text()
            texto_pagina2 = pdf_reader.pages[1].extract_text() if len(pdf_reader.pages) > 1 else ""
            texto_combinado = texto_pagina1 + "\n" + texto_pagina2
            
            print("=== TEXTO EXTRAÍDO DO PDF ===")
            print(texto_combinado)
            print("============================")
            
            # Extrair CNPJ
            padrao_cnpj = r'TOMADOR DE SERVIÇOS.*?\n.*?CPF/CNPJ:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'
            cnpj_match = re.search(padrao_cnpj, texto_combinado, re.DOTALL)
            cnpj = cnpj_match.group(1) if cnpj_match else None
            
            # Extrair SPB_ID
            padrao_spb = r'(SPB-\d+)'
            spb_match = re.search(padrao_spb, texto_combinado)
            spb_id = spb_match.group(1) if spb_match else None
            
            # Extrair Número da Nota
            padrao_num_nota = r'Código de Verificação(0000\d{5})'
            num_nota_match = re.search(padrao_num_nota, texto_combinado)
            print(f"Testando padrão: {padrao_num_nota}")
            if num_nota_match:
                print(f"Match encontrado: {num_nota_match.group(1)}")
                num_nota = num_nota_match.group(1)  
            else:
                print("Nenhum match encontrado para o número da nota")
                num_nota = None
            
            # Extrair Valor Total
            padrao_valor = r'VALOR DO DOCUMENTO\s*([\d.,]+)'
            valor_match = re.search(padrao_valor, texto_combinado)
            valor_total = float(valor_match.group(1).replace('.', '').replace(',', '.')) if valor_match else 0.00
            
            # Extrair Cidade
            padrao_cidade = r"CEP:\s*\d{5}-\d{3}\s*(.*?)\s*INTERMEDIÁRIO DE SERVIÇOS"
            cidade_match = re.search(padrao_cidade, texto_combinado)
            # Remover o '----' e espaços extras no final
            cidade = re.sub(r'----$', '', cidade_match.group(1)).strip() if cidade_match else None
            
            dados = {
                'CNPJ': cnpj,
                'SPB_ID': spb_id,
                'Num_Nota': num_nota,  
                'VALOR_TOTAL': valor_total,
                'CIDADE': cidade
            }
            
            print(f"\nResultados finais:")
            print(f"CNPJ: {cnpj}")
            print(f"SPB_ID: {spb_id}")
            print(f"Número da Nota: {num_nota}")
            print(f"Valor Total: {valor_total}")
            print(f"Cidade: {cidade}")
            
            return dados
            
        except Exception as e:
            print(f"\u274c Erro ao extrair dados do PDF: {str(e)}")
            print(traceback.format_exc())
            raise
    
    async def consolidar_spb(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida os dados do SPB em um novo arquivo.
        """
        try:
            logger.info("Iniciando consolidação do SPB")
            output = BytesIO()
            return output
        except Exception as e:
            logger.error(f"Erro na consolidação do SPB: {str(e)}")
            raise

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa um arquivo SPB.
        """
        try:
            logger.info("Iniciando processamento do arquivo SPB")
            resultado = await self.consolidar_spb(file_content)
            
            return {
                "success": True,
                "data": {
                    "arquivo_consolidado": resultado
                }
            }
        except Exception as e:
            logger.error(f"Erro ao processar arquivo SPB: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

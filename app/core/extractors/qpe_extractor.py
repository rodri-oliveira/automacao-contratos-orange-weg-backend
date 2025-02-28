import os
from io import BytesIO
import pandas as pd
import PyPDF2
import re
import traceback
import logging
from app.core.auth import SharePointAuth  # Alterado para usar SharePointAuth diretamente

logger = logging.getLogger(__name__)

class QPEExtractor:
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()  # Usando SharePointAuth ao invés de SharePointClient

    async def process_file(self, file_content: BytesIO) -> dict:
        """
        Processa o arquivo PDF e extrai os dados necessários.
        """
        try:
            logger.info("Iniciando processamento do arquivo QPE")
            dados = self.extrair_dados_pdf(file_content)
            
            if not dados:
                raise ValueError("Não foi possível extrair dados do PDF")
            
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
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extrair texto da primeira página
            texto_pagina1 = pdf_reader.pages[0].extract_text()
            
            # Extrair texto da segunda página (se existir)
            texto_pagina2 = pdf_reader.pages[1].extract_text() if len(pdf_reader.pages) > 1 else ""
            
            # Texto combinado para busca
            texto_combinado = texto_pagina1 + "\n" + texto_pagina2

            print("\n=== TEXTO EXTRAÍDO DO PDF ===")
            print(texto_combinado)
            print("============================\n")
            
            # Extrair CNPJ do Tomador de Serviços
            padrao_cnpj = r'TOMADOR DE SERVIÇOS.*?\n.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'
            cnpj_match = re.search(padrao_cnpj, texto_combinado, re.DOTALL)
            cnpj = cnpj_match.group(1) if cnpj_match else None
            
            # Extrair Cidade
            padrao_cidade = r'.*,\s*([A-Z\s]+)\s*-'
            cidade_match = re.search(padrao_cidade, texto_combinado)
            cidade = cidade_match.group(1).strip() if cidade_match else None
            
            # Extrair QPE_ID 
            padrao_qpe = r'(QPE-\d+)'
            qpe_match = re.search(padrao_qpe, texto_combinado)
            qpe_id = qpe_match.group(1) if qpe_match else None
            
            # Extrair Valor Total
            padrao_valor = r'VALOR DO DOCUMENTO\s*([\d.,]+)'
            valor_match = re.search(padrao_valor, texto_combinado)
            valor_total = valor_match.group(1).replace('.', '').replace(',', '.') if valor_match else 0.00
            
            # Extrair Número da Nota Fiscal
            padrao_nota_fiscal = r'GERADOR(\d{7})'
            nota_fiscal_match = re.search(padrao_nota_fiscal, texto_combinado)
            nota_fiscal = nota_fiscal_match.group(1) if nota_fiscal_match else None
            
            dados = {
                'CNPJ': cnpj,
                'QPE_ID': qpe_id,
                'NOTA_FISCAL': nota_fiscal,
                'VALOR_TOTAL': float(valor_total),
                'CIDADE': cidade
            }
            
            # Debug prints
            print(f"CNPJ: {cnpj}")
            print(f"Cidade: {cidade}")
            print(f"QPE_ID: {qpe_id}")
            print(f"Valor Total: {valor_total}")
            print(f"Nota Fiscal: {nota_fiscal}")
            
            return dados
            
        except Exception as e:
            logger.error(f"Erro ao extrair dados do PDF: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def consolidar_qpe(self, pdf_files: list) -> BytesIO:
        """
        Consolida os dados dos PDFs selecionados em um novo arquivo Excel.
        """
        dados_consolidados = []
        pasta_qpe = '/teams/BR-TI-TIN/AutomaoFinanas/QPE'
        pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
        
        for pdf_file in pdf_files:
            try:
                token = self.sharepoint_auth.acquire_token()
                if not token:
                    raise Exception("Falha ao obter token para download")

                # Download do arquivo usando SharePointAuth
                pdf_content = await self.sharepoint_auth.baixar_arquivo_sharepoint(
                    pdf_file,
                    pasta_qpe
                )
                
                if pdf_content:
                    dados = self.extrair_dados_pdf(pdf_content)
                    if dados:
                        dados_consolidados.append(dados)
                
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {pdf_file}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        if not dados_consolidados:
            raise ValueError("Nenhum dado foi extraído dos PDFs")

        # Criar DataFrame e arquivo Excel
        df = pd.DataFrame(dados_consolidados)
        excel_output = BytesIO()
        
        with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='QPE_Consolidado')
        
        excel_output.seek(0)
        return excel_output

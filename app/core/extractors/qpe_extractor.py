import os
from io import BytesIO
import pandas as pd
import PyPDF2
import re
import traceback
from app.core.sharepoint import SharePointClient

class QPEExtractor:
    def __init__(self, input_file: str = None, output_dir: str = None):
        self.input_file = input_file
        self.output_dir = output_dir or (os.path.dirname(input_file) if input_file else None)
        self.sharepoint = SharePointClient()

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
            print(f"❌ Erro ao extrair dados do PDF: {str(e)}")
            print(traceback.format_exc())
            raise

    async def consolidar_qpe(self, pdf_files: list) -> BytesIO:
        """
        Consolida os dados dos PDFs selecionados em um novo arquivo Excel.
        Cada PDF selecionado gera uma nova linha no consolidado.
        """
        dados_consolidados = []
        pasta_qpe = '/teams/BR-TI-TIN/AutomaoFinanas/QPE'
        pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
        nome_arquivo = 'QPE_consolidado.xlsx'
        
        # Processa cada PDF selecionado
        for pdf_file in pdf_files:
            try:
                # Se for string, é um arquivo do SharePoint
                if isinstance(pdf_file, str):
                    print(f"Baixando arquivo {pdf_file}...")
                    pdf_content = await self.sharepoint.download_file(pdf_file, pasta_qpe)
                else:
                    pdf_content = pdf_file
                
                # Extrai os dados do PDF
                dados = self.extrair_dados_pdf(pdf_content)
                if dados:
                    dados_consolidados.append(dados)
                
            except Exception as e:
                print(f"❌ Erro ao processar arquivo {pdf_file}: {str(e)}")
                print(traceback.format_exc())
                continue
        
        if not dados_consolidados:
            raise ValueError("Nenhum dado foi extraído dos PDFs")
        
        # Criar DataFrame com os dados consolidados
        df = pd.DataFrame(dados_consolidados)
        
        # Criar arquivo Excel em memória
        excel_output = BytesIO()
        with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='QPE_Consolidado')
        
        excel_output.seek(0)
        
        # Upload do arquivo consolidado para o SharePoint
        await self.sharepoint.upload_file(excel_output, nome_arquivo, pasta_consolidado)
        
        excel_output.seek(0)
        return excel_output

import os
import tempfile
from io import BytesIO
import pandas as pd
from pyxlsb import open_workbook
from app.core.sharepoint import SharePointClient
from typing import Dict, Any
from app.core.auth import SharePointAuth

class R189Extractor:
    def __init__(self, input_file: str = None, output_dir: str = None):
        self.input_file = input_file
        # Se o output_dir não for fornecido, usa o diretório do arquivo de entrada
        self.output_dir = output_dir or (os.path.dirname(input_file) if input_file else None)
        # Instancia o SharePointClient
        self.sharepoint = SharePointClient()
        self.sharepoint_auth = SharePointAuth()

    async def extract(self, file_content: BytesIO) -> Dict[str, Any]:
        """
        Extrai dados do arquivo R189
        """
        try:
            # Lê o arquivo diretamente do BytesIO
            df = pd.read_excel(
                file_content,
                sheet_name=None,  # Lê todas as abas
                na_values=['', ' '],
                keep_default_na=True,
                header=12  # Linha 13 como cabeçalho
            )

            # Verifica se a aba 'BRASIL' existe
            if 'BRASIL' not in df:
                return {
                    "success": False,
                    "error": "A aba 'BRASIL' não foi encontrada no arquivo Excel."
                }
            
            # Obtém os dados apenas da aba 'BRASIL'
            df_brasil = df['BRASIL']

            # Seleciona apenas as colunas necessárias
            colunas_necessarias = [
                'CNPJ - WEG',
                'Invoice number',
                'Site Name - WEG 2',
                'Total Geral',
                'Account number'
            ]
            
            # Verifica se todas as colunas necessárias existem
            colunas_faltantes = [col for col in colunas_necessarias if col not in df_brasil.columns]
            if colunas_faltantes:
                return {
                    "success": False,
                    "error": f"Colunas faltantes no arquivo Excel: {colunas_faltantes}"
                }
            
            # Seleciona apenas as colunas necessárias
            df_resultado = df_brasil[colunas_necessarias].copy()
            
            # Preenche valores vazios com o valor mais próximo acima
            df_resultado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']] = df_resultado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']].ffill()
            
            # Remove linhas que ainda possuem valores NaN nas colunas principais
            df_resultado = df_resultado.dropna(subset=['CNPJ - WEG', 'Invoice number', 'Total Geral'])

            # Converte os dados para o formato esperado
            dados = []
            for _, row in df_resultado.iterrows():
                dados.append({
                    'cnpj_fornecedor': str(row['CNPJ - WEG']),
                    'nota_fiscal': str(row['Invoice number']),
                    'valor_total': float(row['Total Geral']) if pd.notna(row['Total Geral']) else 0.0,
                    'site_name': str(row['Site Name - WEG 2']),
                    'account_number': str(row['Account number'])
                })

            return {
                "success": True,
                "data": dados
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao processar arquivo R189: {str(e)}"
            }

    def processar_arquivo(self) -> str:
        """
        Processa o arquivo .xlsb e o converte para .xlsx.
        
        Returns:
            Caminho do arquivo .xlsx convertido.
        """
        if self.input_file and self.input_file.lower().endswith('.xlsb'):
            xlsx_file = self._convert_xlsb_to_xlsx(self.input_file)
            return xlsx_file
        else:
            raise ValueError("O arquivo de entrada não é um arquivo .xlsb")

    def _convert_xlsb_to_xlsx(self, xlsb_file: str) -> str:
        """
        Converte um arquivo .xlsb para .xlsx
        
        Args:
            xlsb_file: Caminho do arquivo .xlsb
            
        Returns:
            Caminho do arquivo .xlsx convertido
        """
        # Cria um arquivo temporário para o xlsx
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            xlsx_path = temp_file.name

        # Lê o arquivo xlsb e converte para xlsx
        with open_workbook(xlsb_file) as wb:
            with pd.ExcelWriter(xlsx_path, engine='xlsxwriter') as writer:
                for sheet in wb.sheets:
                    data = []
                    for row in sheet.rows():
                        data.append([item.v for item in row])
                    df = pd.DataFrame(data[1:], columns=data[0])
                    df.to_excel(writer, sheet_name=sheet.name, index=False)

        return xlsx_path

    def consolidar_r189(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida o arquivo R189 com colunas específicas e trata valores vazios de CNPJ.
        
        Args:
            conteudo: BytesIO contendo o arquivo Excel
            
        Returns:
            BytesIO contendo o arquivo consolidado
        """
        try:
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

            # Define o nome do arquivo e o caminho da pasta CONSOLIDADO
            nome_arquivo_excel = "R189_consolidado.xlsx"
            pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            
            # Envia apenas para a pasta CONSOLIDADO
            self.sharepoint_auth.enviar_para_sharepoint(
                arquivo_consolidado, 
                nome_arquivo_excel, 
                pasta_consolidado
            )

            # Retorna ao início do BytesIO para que possa ser lido novamente
            arquivo_consolidado.seek(0)
            return arquivo_consolidado
            
        except Exception as e:
            print(f"❌ Erro ao consolidar arquivo R189: {str(e)}")
            raise

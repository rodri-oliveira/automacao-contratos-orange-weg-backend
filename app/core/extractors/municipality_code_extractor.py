import os
import tempfile
from io import BytesIO
import pandas as pd
from pyxlsb import open_workbook
from app.core.sharepoint import SharePointClient

class MunicipalityCodeExtractor:
    def __init__(self, input_file: str = None, output_dir: str = None):
        self.input_file = input_file
        # Se o output_dir não for fornecido, usa o diretório do arquivo de entrada
        self.output_dir = output_dir or (os.path.dirname(input_file) if input_file else None)
        # Instancia o SharePointClient
        self.sharepoint = SharePointClient()

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

    async def consolidar_municipality_code(self, conteudo: BytesIO) -> BytesIO:
        """
        Consolida o arquivo Municipality Code com colunas específicas e trata valores vazios.
        
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

            # Seleciona apenas as colunas necessárias
            colunas_necessarias = [
                'CNPJ - WEG',
                'Invoice number',
                'Municipality Code',
                'Invoice Type',
                'Site Name - WEG 2',
                'Total Geral'
            ]
            
            # Verifica se todas as colunas necessárias existem
            colunas_faltantes = [col for col in colunas_necessarias if col not in df_brasil.columns]
            if colunas_faltantes:
                raise ValueError(f"Colunas faltantes no arquivo Excel: {colunas_faltantes}")
            
            # Seleciona apenas as colunas necessárias
            df_consolidado = df_brasil[colunas_necessarias].copy()

            # Preenche valores vazios com o valor mais próximo acima para todas as colunas exceto Municipality Code
            df_consolidado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']] = df_consolidado[['CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2']].ffill()

            # Filtra apenas as linhas onde Invoice Type é 'SRV'
            df_resultado = df_consolidado[df_consolidado['Invoice Type'] == 'SRV'].copy()
            
            # Remove linhas que ainda possuem valores NaN nas colunas principais
            df_resultado = df_resultado.dropna(subset=['CNPJ - WEG', 'Invoice number', 'Municipality Code', 'Total Geral'])

            # Remove a coluna Invoice Type pois já filtramos por SRV
            df_resultado = df_resultado.drop('Invoice Type', axis=1)

            # Gera o arquivo consolidado em formato BytesIO
            arquivo_consolidado = BytesIO()
            with pd.ExcelWriter(arquivo_consolidado, engine='xlsxwriter') as writer:
                df_resultado.to_excel(writer, index=False, sheet_name='Municipality_Code_consolidado')
            
            arquivo_consolidado.seek(0)

            # Define o nome do arquivo e o caminho da pasta CONSOLIDADO
            nome_arquivo_excel = "Municipality_Code_consolidado.xlsx"
            pasta_consolidado = '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
            
            # Upload do arquivo consolidado para o SharePoint
            await self.sharepoint.upload_file(arquivo_consolidado, nome_arquivo_excel, pasta_consolidado)
            
            arquivo_consolidado.seek(0)
            return arquivo_consolidado
            
        except Exception as e:
            print(f"❌ Erro ao consolidar arquivo Municipality Code: {str(e)}")
            raise

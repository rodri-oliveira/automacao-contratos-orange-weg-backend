# Fluxograma da Aplicação - Automação Finanças

Este documento descreve as principais funcionalidades da aplicação, focando nas regras de negócio de cada processo, incluindo extração de dados e validações.

## Abas (Extração e Processamento Inicial de Dados)

### Aba R189 (`r189_extractor.py`)

**Regras de Negócio:**
* Processa arquivos R189 no formato `.xlsb` da aba 'BRASIL'
* Extrai colunas específicas: 'CNPJ - WEG', 'Invoice number', 'Site Name - WEG 2', 'Total Geral'/'Grand Total', 'Account number', 'Invoice Type'
* Aceita variações do nome da coluna de total ('Total Geral' ou 'Grand Total')
* Preenche valores vazios usando a técnica de forward fill (ffill) para garantir consistência
* Remove linhas onde Account number contém a string 'Total' para evitar duplicação
* Agrupa os dados por CNPJ, Invoice number, Site Name e Invoice Type, somando os valores totais
* Gera um arquivo consolidado em formato Excel para uso nas validações posteriores

### Aba NF_SERV (`qpe_extractor.py`)

**Regras de Negócio:**
* Processa arquivos QPE (Quadro de Pessoal) 
* Extrai informações como CNPJ, QPE_ID, NOTA_FISCAL e valores totais
* Identifica registros com tipo 'REN' (Renovação) que devem ser validados contra NFSERV
* Agrupa dados por identificadores relevantes para garantir valores únicos
* Consolida as informações em um arquivo Excel para comparações futuras

### Aba NF_SPB (`spb_extractor.py`)

**Regras de Negócio:**
* Processa arquivos SPB (Sistema de Pagamentos Brasileiro)
* Extrai dados como SPB_ID, CNPJ, Num_Nota e valores totais
* Identifica registros com tipo 'SRV' (Serviço) que devem ser validados de forma específica
* Registros sem tipo 'SRV' devem ser validados contra NFSERV
* Consolida as informações para uso nas validações cruzadas

### Aba Faturas (`nfserv_extractor.py`)

**Regras de Negócio:**
* Processa arquivos de Notas Fiscais de Serviço (NFSERV)
* Extrai dados como NFSERV_ID, CNPJ, VALOR_TOTAL
* Identifica a origem do documento (QPE ou SPB) através do prefixo do ID
* Consolida as informações para validação cruzada com R189

### Aba SRV_CODE (`municipality_code_extractor.py`)

**Regras de Negócio:**
* Processa arquivos com códigos de serviço por município
* Extrai colunas: 'CNPJ - WEG', 'Invoice number', 'Municipality Code', 'Invoice Type', 'Site Name - WEG 2', 'Total Geral'/'Grand Total'
* Aceita variações do nome da coluna de total ('Total Geral' ou 'Grand Total')
* Filtra apenas registros com 'Invoice Type' = 'SRV'
* Valida se os CNPJs estão autorizados para os códigos de serviço específicos
* Consolida as informações para uso nas validações

## Validações (Relatórios de Divergência)

### Botão Verificar Divergências R189 (`divergence_report_r189.py`)

**Regras de Negócio:**
* Analisa inconsistências internas no R189
* Verifica se todos os campos obrigatórios estão preenchidos
* Valida formatos de CNPJ e valores numéricos
* Identifica possíveis duplicações de Invoice number
* Verifica se os valores totais são coerentes
* Gera relatório com as inconsistências encontradas

### Botão Verificar Divergências SRV_CODE vs R189 (Simples) (`report_mun_code_r189_simple.py`)

**Regras de Negócio:**
* Versão simplificada da validação entre códigos de serviço e R189
* Verifica apenas se os códigos de município (Municipality Code) estão presentes no R189
* Não valida a coluna NF nem realiza verificações detalhadas de CNPJ
* Gera relatório básico de divergências para análise rápida

### Botão Verificar Divergências SRV_CODE vs R189 (`report_mun_code_r189.py`)

**Regras de Negócio:**
* Versão completa da validação entre códigos de serviço e R189
* Verifica se os CNPJs estão autorizados para os códigos de serviço específicos usando mapeamentos predefinidos:
  - Códigos como "14.02", "17.01", "14.01", etc. são mapeados para materiais e tipos específicos
  - Cada combinação de serviço tem uma lista de CNPJs autorizados
* Agrupa os dados por Municipality Code, CNPJ e Invoice number
* Adiciona informações de Nota Fiscal quando disponíveis em QPE ou SPB
* Compara valores totais entre as fontes de dados
* Gera relatório detalhado com todas as divergências encontradas

### Botão Verificar Divergências NF_QPE vs R189 (`divergence_report_qpe_r189.py`)

**Regras de Negócio:**
* Compara dados do QPE com R189
* Verifica se todos os QPEs com tipo 'REN' no R189 estão presentes no QPE consolidado
* Valida se os CNPJs e valores totais coincidem entre as duas fontes
* Identifica QPEs presentes em uma fonte mas ausentes na outra
* Gera relatório detalhado das divergências

### Botão Verificar Divergência NF_SPB vs R189 (`divergence_report_spb_r189.py`)

**Regras de Negócio:**
* Compara dados do SPB com R189
* Foca apenas nos SPBs com tipo 'SRV' no R189
* Verifica se todos os SPBs com tipo 'SRV' no R189 estão presentes no SPB consolidado
* Valida se os CNPJs e valores totais coincidem entre as duas fontes
* Identifica SPBs presentes em uma fonte mas ausentes na outra
* Verifica se há SPBs no consolidado que não estão marcados como 'SRV' no R189
* Gera relatório detalhado das divergências

### Botão Verificar Divergências Faturas vs R189 (`divergence_report_nfserv_r189.py`)

**Regras de Negócio:**
* Compara dados das Faturas/NFSERV com R189
* Verifica duas categorias principais:
  1. QPEs com tipo 'REN' no R189 vs QPEs no NFSERV
  2. SPBs sem tipo 'SRV' no R189 vs SPBs no NFSERV
* Valida se os registros estão presentes em ambas as fontes
* Compara CNPJs e valores totais
* Identifica registros presentes em uma fonte mas ausentes na outra
* Gera relatório detalhado das divergências

### Botão Consolidar Relatório (`consolidated_report.py`)

**Regras de Negócio:**
* Reúne os resultados de todos os relatórios de divergência mais recentes
* Combina as informações em um único arquivo Excel
* Organiza as divergências por tipo e gravidade
* Facilita a análise conjunta de todas as inconsistências encontradas
* Gera estatísticas sobre o número total de divergências por categoria

## Outras Funções Relevantes

### Organização Inicial de Arquivos (`file_processor.py`)

**Regras de Negócio:**
* Monitora a pasta `ENTRADA` para novos arquivos
* Identifica o tipo de cada arquivo (PDF, XLSB) baseado em seu conteúdo e nome
* Renomeia os arquivos seguindo regras específicas:
  - Adiciona prefixos como QPE-, SPB-, R189- conforme o tipo
  - Inclui informações como cidade e tipo de serviço quando disponíveis
* Move os arquivos para as pastas correspondentes:
  - `/R189` para arquivos R189
  - `/QPE` para arquivos QPE
  - `/SPB` para arquivos SPB
  - `/NFSERV` para notas fiscais de serviço
* Registra todas as operações realizadas para auditoria

### Verificação de Email Orange (`orange_email.py` / Power Automate)

**Regras de Negócio:**
* Um serviço externo (Power Automate) verifica a chegada de emails específicos (Orange)
* A URL do Power Automate é: https://prod-56.westus.logic.azure.com:443/workflows/3d9aba09a8e44e749fb2a2dd9d94e38a/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=GXqnWZyH4DMZTl98u1-gQDacjYxZRQeQ8Uj93_pASiY
* O serviço requer requisições GET (não POST)
* Verifica se o número de emails retornados é maior que 0
* Se houver notificações, aciona o backend para iniciar o download dos anexos para a pasta `ENTRADA`
* Disponibiliza dois endpoints:
  1. `/check-orange-email-notifications` - Verifica diretamente no Power Automate se há emails disponíveis
  2. `/validate-orange-email-notifications` - Endpoint adicional para validação com parâmetros opcionais

# Fluxograma da Aplicação - Automação Finanças

Este documento descreve as principais funcionalidades da aplicação, focando na extração de dados por "aba" e nas validações realizadas.

## Abas (Extração e Processamento Inicial de Dados)

*   **Aba R189 (`r189_extractor.py`):** Responsável por processar os arquivos R189 (formato `.xlsb`). Extrai os dados relevantes desses arquivos, provavelmente para consolidá-los ou prepará-los para validação cruzada.

*   **Aba NF_SERV (Processada por `qpe_extractor.py`):** Embora a aba seja chamada de "NF_SERV", o processamento é feito pelo `qpe_extractor.py`. Este componente é responsável por processar os arquivos QPE (Quadro de Pessoal?), extraindo e tratando os dados específicos desses documentos.

*   **Aba NF_SPB (`spb_extractor.py`):** Responsável por processar os arquivos SPB, extraindo as informações contidas neles para uso posterior nas validações ou relatórios.

*   **Aba Faturas (Processada por `nfserv_extractor.py`):** Similar à aba NF_SERV, a aba "Faturas" é processada pelo `nfserv_extractor.py`. Este componente extrai dados de arquivos classificados como NFSERV (Notas Fiscais de Serviço?), tratando as informações de faturas de serviços.

*   **Aba SRV_CODE (`municipality_code_extractor.py`):** Responsável por processar arquivos ou fontes de dados que contêm os códigos de serviço por município (MUN_CODE), extraindo essa relação para ser usada nas validações.

## Validações (Relatórios de Divergência)

Os botões de validação acionam a geração de relatórios que comparam dados de diferentes fontes:

*   **Botão Verificar Divergências R189 (`DivergenceReportR189`):** Gera um relatório que analisa os dados dentro do próprio R189, buscando por inconsistências internas ou problemas específicos desse conjunto de dados.

*   **Botão Verificar Divergências SRV_CODE vs R189 (Simples) (`report_mun_code_r189_simple.py`):** Gera um relatório comparando os Códigos de Serviço (SRV_CODE) com os dados do R189. Esta é uma versão "simples" da validação, possivelmente omitindo algumas colunas ou verificações complexas (como a coluna NF mencionada no código).

*   **Botão Verificar Divergências SRV_CODE vs R189 (`report_mun_code_r189.py`):** Gera a versão completa do relatório de comparação entre os Códigos de Serviço (SRV_CODE) e os dados do R189, incluindo todas as verificações relevantes.

*   **Botão Verificar Divergências NF_QPE vs R189 (Processado por `divergence_report_nfserv_r189.py`):** Embora o botão mencione "NF_QPE", o relatório gerado (`divergence_report_nfserv_r189.py`) compara os dados extraídos das **Faturas/NFSERV** com os dados do R189, identificando divergências entre essas duas fontes. *Nota: Existe também um `divergence_report_qpe_r189.py` no projeto que compara QPE vs R189, que pode ser o alvo pretendido para um botão com nome "NF_QPE vs R189".*

*   **Botão Verificar Divergência NF_SPB vs R189 (`divergence_report_spb_r189.py`):** Gera um relatório que compara os dados extraídos dos arquivos SPB com os dados do R189, apontando as diferenças encontradas.

*   **Botão Verificar Divergências Faturas vs R189 (`divergence_report_nfserv_r189.py`):** Gera um relatório que compara os dados extraídos das Faturas/NFSERV com os dados do R189, identificando divergências (este parece ser o mesmo relatório acionado pelo botão "NF_QPE vs R189" conforme o arquivo vinculado).

*   **Botão Consolidar Relatório (`consolidated_report.py`):** Reúne os resultados dos relatórios de divergência mais recentes gerados pelas validações anteriores em um único arquivo consolidado (provavelmente Excel), facilitando a análise conjunta das inconsistências.

## Outras Funções Relevantes

*   **Organização Inicial de Arquivos (`file_processor.py`):** Antes das extrações e validações, este componente monitora a pasta `ENTRADA`, identifica o tipo de cada arquivo (PDF, XLSB), renomeia-os seguindo regras específicas (adicionando cidade, tipo de serviço, etc.) e move-os para as pastas correspondentes (`/R189`, `/QPE`, `/SPB`, `/NFSERV`).
*   **Verificação de Email Orange (`orange_email.py` / Power Automate):** Um serviço externo (Power Automate) verifica a chegada de emails específicos (Orange) e, se houver notificações, aciona o backend (provavelmente para iniciar o download dos anexos para a pasta `ENTRADA`).

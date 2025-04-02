from typing import Dict, Any, Tuple
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging
from app.core.auth import SharePointAuth
from app.core.sharepoint import SharePointClient

logger = logging.getLogger(__name__)

class DivergenceReportNFSERVR189:
    """
    Classe responsável por verificar divergências entre os arquivos consolidados NFSERV e R189.
    """
    
    def __init__(self):
        self.sharepoint_auth = SharePointAuth()
        self.sharepoint_client = SharePointClient()
        # Lista de possíveis nomes para a coluna de total
        self.colunas_total = ['Total Geral', 'Grand Total', 'Total Gera', 'Total', 'Valor Total']

    async def check_divergences(self, nfserv_data, r189_data):
        """
        Verifica divergências entre os dados consolidados do NFSERV e R189.
        
        Args:
            nfserv_data: DataFrame com os dados consolidados do NFSERV
            r189_data: DataFrame com os dados consolidados do R189
            
        Returns:
            tuple: (sucesso, mensagem, DataFrame com divergências)
        """
        try:
            logger.info("Iniciando verificação de divergências entre NFSERV e R189")
            
            # Validação inicial dos DataFrames
            if nfserv_data is None or r189_data is None:
                logger.error("DataFrames não podem ser None")
                return False, "Erro: DataFrames não podem ser None", pd.DataFrame()
                
            if nfserv_data.empty or r189_data.empty:
                logger.error("DataFrames não podem estar vazios")
                return False, "Erro: DataFrames não podem estar vazios", pd.DataFrame()
            
            logger.info(f"NFSERV: {len(nfserv_data)} linhas, R189: {len(r189_data)} linhas")
            
            divergences = []
            
            # Verifica qual coluna de total está presente no DataFrame do R189
            coluna_total_encontrada = None
            for col in self.colunas_total:
                if col in r189_data.columns:
                    coluna_total_encontrada = col
                    logger.info(f"Coluna de total encontrada no R189: {col}")
                    break
                    
            if not coluna_total_encontrada:
                logger.error(f"Nenhuma das colunas de total foi encontrada no R189: {self.colunas_total}")
                return False, f"Erro: Nenhuma das colunas de total foi encontrada no R189. Esperado uma das seguintes: {self.colunas_total}", pd.DataFrame()
            
            # Extrai as siglas dos IDs
            def extract_sigla(id_value):
                if pd.isna(id_value):
                    return None
                parts = str(id_value).split('-')
                return parts[0] if len(parts) > 1 else None
            
            # Adiciona coluna de sigla em ambos os DataFrames
            logger.info("Extraindo siglas dos IDs")
            nfserv_data['SIGLA'] = nfserv_data['NFSERV_ID'].apply(extract_sigla)
            r189_data['SIGLA'] = r189_data['Invoice number'].apply(extract_sigla)
            
            # Verificação para Invoice Type
            if 'Invoice Type' not in r189_data.columns:
                logger.warning("Coluna 'Invoice Type' não encontrada no R189. Esta coluna é necessária para comparação correta.")
                r189_data['Invoice Type'] = None  # Adiciona coluna vazia para evitar erros
            
            # CORREÇÃO IMPORTANTE: Dividir os QPE e SPB do R189 em grupos baseados no Invoice Type
            logger.info("Separando os QPEs e SPBs do R189 em grupos baseados no Invoice Type")
            
            # Criar máscaras para identificar cada tipo de registro
            qpe_ren_mask = (r189_data['SIGLA'] == 'QPE') & (r189_data['Invoice Type'] == 'REN')
            qpe_srv_mask = (r189_data['SIGLA'] == 'QPE') & (r189_data['Invoice Type'] == 'SRV')
            spb_srv_mask = (r189_data['SIGLA'] == 'SPB') & (r189_data['Invoice Type'] == 'SRV')
            spb_outros_mask = (r189_data['SIGLA'] == 'SPB') & (r189_data['Invoice Type'] != 'SRV')
            
            # Log para debug
            qpe_ren_count = qpe_ren_mask.sum()
            qpe_srv_count = qpe_srv_mask.sum()
            spb_srv_count = spb_srv_mask.sum()
            spb_outros_count = spb_outros_mask.sum()
            
            logger.info(f"Encontrados {qpe_ren_count} registros QPE+REN e {qpe_srv_count} registros QPE+SRV no R189")
            logger.info(f"Encontrados {spb_srv_count} registros SPB+SRV e {spb_outros_count} registros SPB+outros no R189")
            
            # Verificar os registros QPE no NFSERV
            qpe_nfserv_mask = (nfserv_data['SIGLA'] == 'QPE')
            qpe_nfserv_count = qpe_nfserv_mask.sum()
            logger.info(f"Encontrados {qpe_nfserv_count} registros QPE no NFSERV")
            
            # Verificar os registros SPB no NFSERV
            spb_nfserv_mask = (nfserv_data['SIGLA'] == 'SPB')
            spb_nfserv_count = spb_nfserv_mask.sum()
            logger.info(f"Encontrados {spb_nfserv_count} registros SPB no NFSERV")
            
            # Obtém listas de IDs para cada categoria
            qpe_ren_ids = set(r189_data.loc[qpe_ren_mask, 'Invoice number'])
            qpe_srv_ids = set(r189_data.loc[qpe_srv_mask, 'Invoice number'])
            spb_srv_ids = set(r189_data.loc[spb_srv_mask, 'Invoice number'])
            spb_outros_ids = set(r189_data.loc[spb_outros_mask, 'Invoice number'])
            qpe_nfserv_ids = set(nfserv_data.loc[qpe_nfserv_mask, 'NFSERV_ID'])
            spb_nfserv_ids = set(nfserv_data.loc[spb_nfserv_mask, 'NFSERV_ID'])
            
            logger.info(f"IDs de QPE+REN no R189: {len(qpe_ren_ids)} itens")
            logger.info(f"IDs de QPE+SRV no R189: {len(qpe_srv_ids)} itens")
            logger.info(f"IDs de SPB+SRV no R189: {len(spb_srv_ids)} itens")
            logger.info(f"IDs de SPB+outros no R189: {len(spb_outros_ids)} itens")
            logger.info(f"IDs de QPE no NFSERV: {len(qpe_nfserv_ids)} itens")
            logger.info(f"IDs de SPB no NFSERV: {len(spb_nfserv_ids)} itens")
            
            # VERIFICAÇÃO 1: QPE+REN do R189 vs QPE do NFSERV
            # Estes são os QPEs que devem estar no NFSERV
            logger.info("Verificando QPE+REN do R189 vs QPE do NFSERV")
            
            # Adicione a contagem nas estatísticas
            divergences.append({
                'Tipo': 'CONTAGEM_QPE_REN',
                'NFSERV_ID': 'N/A',
                'CNPJ NFSERV': 'N/A',
                'CNPJ R189': 'N/A',
                'Valor NFSERV': qpe_nfserv_count,
                'Valor R189': qpe_ren_count,
                'Detalhes': f'QPEs com Type=REN: NFSERV={qpe_nfserv_count}, R189={qpe_ren_count}'
            })
            
            # VERIFICAÇÃO 2: SPB+outros (não SRV) do R189 vs SPB do NFSERV
            # Apenas os SPBs que NÃO são SRV devem estar no NFSERV
            logger.info("Verificando SPB+outros (não SRV) do R189 vs SPB do NFSERV")
            
            divergences.append({
                'Tipo': 'CONTAGEM_SPB_TEL',
                'NFSERV_ID': 'N/A',
                'CNPJ NFSERV': 'N/A',
                'CNPJ R189': 'N/A',
                'Valor NFSERV': spb_nfserv_count,
                'Valor R189': spb_outros_count,
                'Detalhes': f'SPBs sem Type=SRV: NFSERV={spb_nfserv_count}, R189={spb_outros_count}'
            })
            
            # Verificar divergências item a item para QPE+REN
            qpe_ren_missing = qpe_ren_ids - qpe_nfserv_ids
            if qpe_ren_missing:
                logger.warning(f"Encontrados {len(qpe_ren_missing)} QPE+REN no R189 que estão ausentes no NFSERV")
                for missing_id in qpe_ren_missing:
                    row = r189_data[r189_data['Invoice number'] == missing_id].iloc[0]
                    divergences.append({
                        'Tipo': 'QPE_REN ausente no NFSERV',
                        'NFSERV_ID': missing_id,
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': row['CNPJ - WEG'],
                        'Valor NFSERV': 'N/A',
                        'Valor R189': row[coluna_total_encontrada],
                        'Detalhes': f'Invoice Type=REN não encontrado no NFSERV'
                    })
            
            qpe_nfserv_missing = qpe_nfserv_ids - qpe_ren_ids
            if qpe_nfserv_missing:
                logger.warning(f"Encontrados {len(qpe_nfserv_missing)} QPE no NFSERV que não são QPE+REN no R189")
                for missing_id in qpe_nfserv_missing:
                    # Verificar se existe como outro tipo (ex: QPE+SRV)
                    if missing_id in qpe_srv_ids:
                        logger.info(f"ID {missing_id} encontrado como QPE+SRV no R189, não é divergência real")
                        continue
                    
                    row = nfserv_data[nfserv_data['NFSERV_ID'] == missing_id].iloc[0]
                    divergences.append({
                        'Tipo': 'QPE do NFSERV ausente como REN no R189',
                        'NFSERV_ID': missing_id,
                        'CNPJ NFSERV': row['CNPJ'],
                        'CNPJ R189': 'N/A',
                        'Valor NFSERV': row['VALOR_TOTAL'],
                        'Valor R189': 'N/A',
                        'Detalhes': f'QPE existe no NFSERV mas não como Type=REN no R189'
                    })
            
            # Verificar divergências item a item para SPB+outros (não SRV)
            spb_outros_missing = spb_outros_ids - spb_nfserv_ids
            if spb_outros_missing:
                logger.warning(f"Encontrados {len(spb_outros_missing)} SPB sem Type=SRV no R189 que estão ausentes no NFSERV")
                for missing_id in spb_outros_missing:
                    row = r189_data[r189_data['Invoice number'] == missing_id].iloc[0]
                    divergences.append({
                        'Tipo': 'SPB_TEL ausente no NFSERV',
                        'NFSERV_ID': missing_id,
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': row['CNPJ - WEG'],
                        'Valor NFSERV': 'N/A',
                        'Valor R189': row[coluna_total_encontrada],
                        'Detalhes': f'SPB sem Type=SRV não encontrado no NFSERV'
                    })
            
            spb_nfserv_missing = spb_nfserv_ids - spb_outros_ids
            if spb_nfserv_missing:
                logger.warning(f"Encontrados {len(spb_nfserv_missing)} SPB no NFSERV que não estão no R189 ou são SPB+SRV")
                for missing_id in spb_nfserv_missing:
                    # Verificar se existe como outro tipo (ex: SPB+SRV)
                    if missing_id in spb_srv_ids:
                        logger.info(f"ID {missing_id} encontrado como SPB+SRV no R189, não é divergência real")
                        continue
                    
                    row = nfserv_data[nfserv_data['NFSERV_ID'] == missing_id].iloc[0]
                    divergences.append({
                        'Tipo': 'SPB_TEL do NFSERV ausente ou como SRV no R189',
                        'NFSERV_ID': missing_id,
                        'CNPJ NFSERV': row['CNPJ'],
                        'CNPJ R189': 'N/A',
                        'Valor NFSERV': row['VALOR_TOTAL'],
                        'Valor R189': 'N/A',
                        'Detalhes': f'SPB existe no NFSERV mas não está ou é Type=SRV no R189'
                    })
            
            # Agora proceda com a verificação normal para outras siglas (excluindo QPE e SPB)
            # Obtém siglas únicas (excluindo QPE e SPB que já tratamos separadamente, e valores nulos)
            siglas_sem_qpe_spb = set(nfserv_data['SIGLA'].unique()) - {'QPE', 'SPB', None}
            logger.info(f"Siglas únicas para verificação padrão: {siglas_sem_qpe_spb}")
            
            # Verificar cada uma das outras siglas
            for sigla in siglas_sem_qpe_spb:
                logger.info(f"Analisando sigla: {sigla}")
                
                # Contagem no NFSERV
                nfserv_count = len(nfserv_data[nfserv_data['SIGLA'] == sigla])
                
                # Contagem no R189
                r189_count = len(r189_data[r189_data['SIGLA'] == sigla])
                    
                logger.info(f"Contagem para sigla {sigla}: NFSERV={nfserv_count}, R189={r189_count}")
                
                # Adiciona contagem para todas as siglas
                divergences.append({
                    'Tipo': f'CONTAGEM_{sigla}',
                    'NFSERV_ID': 'N/A',
                    'CNPJ NFSERV': 'N/A',
                    'CNPJ R189': 'N/A',
                    'Valor NFSERV': nfserv_count,
                    'Valor R189': r189_count,
                    'Detalhes': f'Total de notas {sigla}: NFSERV={nfserv_count}, R189={r189_count}'
                })
                
                # Se houver diferença nas contagens, registra a divergência
                if nfserv_count != r189_count:
                    logger.warning(f"Divergência na contagem para sigla {sigla}: NFSERV={nfserv_count}, R189={r189_count}")
                    divergences.append({
                        'Tipo': 'CONTAGEM_NFSERV',
                        'NFSERV_ID': 'N/A',
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': 'N/A',
                        'Valor NFSERV': nfserv_count,
                        'Valor R189': r189_count
                    })
                
                # Verifica IDs específicos da sigla
                nfserv_ids = set(nfserv_data[nfserv_data['SIGLA'] == sigla]['NFSERV_ID'])
                r189_ids = set(r189_data[r189_data['SIGLA'] == sigla]['Invoice number'])
                
                # IDs no NFSERV mas não no R189
                missing_in_r189 = nfserv_ids - r189_ids
                logger.info(f"IDs no NFSERV mas não no R189 para sigla {sigla}: {len(missing_in_r189)}")
                
                for nfserv_id in missing_in_r189:
                    nfserv_rows = nfserv_data[nfserv_data['NFSERV_ID'] == nfserv_id]
                    if nfserv_rows.empty:
                        continue
                    
                    nfserv_row = nfserv_rows.iloc[0]
                    divergences.append({
                        'Tipo': 'Nota não encontrada no R189',
                        'NFSERV_ID': nfserv_id,
                        'CNPJ NFSERV': nfserv_row['CNPJ'],
                        'CNPJ R189': 'Não encontrado',
                        'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                        'Valor R189': 'N/A',
                        'Detalhes': f'Nota {nfserv_id} existe no NFSERV mas não foi encontrada no R189'
                    })
                
                # IDs no R189 mas não no NFSERV
                missing_in_nfserv = r189_ids - nfserv_ids
                logger.info(f"IDs no R189 mas não no NFSERV para sigla {sigla}: {len(missing_in_nfserv)}")
                
                for r189_id in missing_in_nfserv:
                    r189_rows = r189_data[r189_data['Invoice number'] == r189_id]
                    if r189_rows.empty:
                        continue
                    
                    r189_row = r189_rows.iloc[0]
                    divergences.append({
                        'Tipo': 'Nota não encontrada no NFSERV',
                        'NFSERV_ID': r189_id,
                        'CNPJ NFSERV': 'N/A',
                        'CNPJ R189': r189_row['CNPJ - WEG'],
                        'Valor NFSERV': 'N/A',
                        'Valor R189': r189_row[coluna_total_encontrada],
                        'Detalhes': f'Nota {r189_id} existe no R189 mas não foi encontrada no NFSERV'
                    })
                
                # Verifica divergências para IDs que existem em ambos
                common_ids = nfserv_ids & r189_ids
                logger.info(f"IDs presentes em ambos os sistemas para sigla {sigla}: {len(common_ids)}")
                
                for nfserv_id in common_ids:
                    nfserv_rows = nfserv_data[nfserv_data['NFSERV_ID'] == nfserv_id]
                    r189_rows = r189_data[r189_data['Invoice number'] == nfserv_id]
                    
                    if nfserv_rows.empty or r189_rows.empty:
                        continue
                    
                    nfserv_row = nfserv_rows.iloc[0]
                    r189_row = r189_rows.iloc[0]
                    
                    # Verifica CNPJ - Normaliza removendo espaços e pontuação
                    nfserv_cnpj = str(nfserv_row['CNPJ']).strip().replace('.', '').replace('-', '').replace('/', '')
                    r189_cnpj = str(r189_row['CNPJ - WEG']).strip().replace('.', '').replace('-', '').replace('/', '')
                    
                    if nfserv_cnpj != r189_cnpj:
                        logger.warning(f"CNPJ divergente para {nfserv_id}: NFSERV={nfserv_row['CNPJ']}, R189={r189_row['CNPJ - WEG']}")
                        divergences.append({
                            'Tipo': 'CNPJ divergente',
                            'NFSERV_ID': nfserv_id,
                            'CNPJ NFSERV': nfserv_row['CNPJ'],
                            'CNPJ R189': r189_row['CNPJ - WEG'],
                            'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                            'Valor R189': r189_row[coluna_total_encontrada],
                            'Detalhes': f'CNPJ diferente para nota {nfserv_id}: NFSERV={nfserv_row["CNPJ"]}, R189={r189_row["CNPJ - WEG"]}'
                        })
                    
                    # Verifica Valor
                    try:
                        # Trata valores com vírgula ou ponto
                        nfserv_valor = str(nfserv_row['VALOR_TOTAL']).strip().replace(',', '.')
                        r189_valor = str(r189_row[coluna_total_encontrada]).strip().replace(',', '.')
                        
                        # Remove caracteres não numéricos exceto ponto
                        nfserv_valor = ''.join(c for c in nfserv_valor if c.isdigit() or c == '.')
                        r189_valor = ''.join(c for c in r189_valor if c.isdigit() or c == '.')
                        
                        # Converte para float
                        nfserv_valor_float = float(nfserv_valor)
                        r189_valor_float = float(r189_valor)
                        
                        # Se os valores forem diferentes (com margem de tolerância)
                        if abs(nfserv_valor_float - r189_valor_float) > 0.01:
                            logger.warning(f"Valor divergente para {nfserv_id}: NFSERV={nfserv_valor_float}, R189={r189_valor_float}")
                            divergences.append({
                                'Tipo': 'VALOR',
                                'NFSERV_ID': nfserv_id,
                                'CNPJ NFSERV': nfserv_row['CNPJ'],
                                'CNPJ R189': r189_row['CNPJ - WEG'],
                                'Valor NFSERV': nfserv_row['VALOR_TOTAL'],
                                'Valor R189': r189_row[coluna_total_encontrada],
                                'Detalhes': f'Valor diferente para nota {nfserv_id}: NFSERV={nfserv_row["VALOR_TOTAL"]}, R189={r189_row[coluna_total_encontrada]}'
                            })
                    except (ValueError, TypeError) as e:
                        # Se houver erro na conversão, registra como divergência
                        logger.warning(f"Erro na validação de valor para {nfserv_id}: {str(e)}")
                        divergences.append({
                            'Tipo': 'Erro na validação de valor',
                            'NFSERV_ID': nfserv_id,
                            'CNPJ NFSERV': nfserv_row['CNPJ'],
                            'CNPJ R189': r189_row['CNPJ - WEG'],
                            'Valor NFSERV': str(nfserv_row['VALOR_TOTAL']),
                            'Valor R189': str(r189_row[coluna_total_encontrada]),
                            'Detalhes': f'Erro ao comparar valores para nota {nfserv_id}: Formato inválido'
                        })
            
            if divergences:
                df_divergences = pd.DataFrame(divergences)
                logger.info(f"Encontradas {len(divergences)} divergências")
                logger.info(f"Resumo por tipo: {df_divergences['Tipo'].value_counts().to_dict()}")
                return True, f"Encontradas {len(divergences)} divergências:\n" + \
                           f"- {df_divergences['Tipo'].value_counts().to_string()}", df_divergences
            
            logger.info("Nenhuma divergência encontrada")
            return True, "Nenhuma divergência encontrada nos dados analisados", pd.DataFrame()
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao verificar divergências: {str(e)}")
            return False, f"Erro inesperado ao verificar divergências: {str(e)}\n" + \
                         "Por favor, verifique se os arquivos estão no formato correto.", pd.DataFrame()

    async def generate_excel_report(self, divergences_df):
        """
        Gera um relatório Excel com as divergências encontradas, com descrições claras e organizadas.
        """
        try:
            logger.info("Iniciando geração do relatório Excel simplificado e objetivo")
            
            if divergences_df is None:
                logger.error("DataFrame de divergências é None")
                return {"success": False, "error": "DataFrame de divergências é None"}
                
            if divergences_df.empty:
                logger.info("Nenhuma divergência para gerar relatório")
                return {"success": True, "message": "Nenhuma divergência para gerar relatório"}
            
            # Validação das colunas necessárias
            required_columns = ['Tipo', 'NFSERV_ID', 'CNPJ NFSERV', 'CNPJ R189', 'Valor NFSERV', 'Valor R189']
            missing_columns = [col for col in required_columns if col not in divergences_df.columns]
            if missing_columns:
                logger.error(f"Colunas necessárias não encontradas: {missing_columns}")
                return {"success": False, "error": f"Colunas necessárias não encontradas: {', '.join(missing_columns)}"}
            
            # Adiciona data e hora ao DataFrame
            now = datetime.now()
            divergences_df['Data Verificação'] = now.strftime('%Y-%m-%d')
            divergences_df['Hora Verificação'] = now.strftime('%H:%M:%S')
            
            # Vamos melhorar a organização e clareza das divergências
            
            # 1. Remover linha redundante de "CONTAGEM_NFSERV"
            divergences_df = divergences_df[divergences_df['Tipo'] != 'CONTAGEM_NFSERV']
            
            # 2. Organizar por tipo de divergência de maneira lógica
            # Define ordem de prioridade para os tipos
            tipo_ordem = {
                'CONTAGEM_': 0,  # Contagens vêm primeiro
                'Nota não encontrada': 1,  # Seguido por notas faltantes
                'ausente': 1,  # Também são notas faltantes
                'CNPJ': 2,  # Depois vêm divergências de CNPJ
                'VALOR': 3,  # Por fim divergências de valor
            }
            
            # Função para obter o valor de ordenação por tipo
            def get_order_value(tipo):
                for key, value in tipo_ordem.items():
                    if key in tipo:
                        return value
                return 999  # Valor alto para tipos não mapeados
            
            # Adicionar coluna de ordenação
            divergences_df['ordem'] = divergences_df['Tipo'].apply(get_order_value)
            
            # 3. Adicionar uma descrição mais clara
            def melhorar_descricao(row):
                tipo = row['Tipo']
                detalhes = row['Detalhes'] if pd.notna(row['Detalhes']) else ""
                
                # Para contagens, já temos boas descrições mas vamos remover casas decimais
                if tipo.startswith('CONTAGEM_'):
                    # Extrair os valores e convertê-los para inteiros
                    partes = detalhes.split('=')
                    if len(partes) >= 3:  # Formato típico: "... NFSERV=X, R189=Y"
                        prefixo = partes[0] + "="
                        valor_nfserv_texto = partes[1].split(',')[0].strip()
                        resto = "," + partes[1].split(',', 1)[1] if ',' in partes[1] else ""
                        
                        try:
                            # Converter para inteiro
                            valor_nfserv = int(float(valor_nfserv_texto))
                            valor_r189 = int(float(partes[2].strip()))
                            
                            # Reconstruir a string com valores inteiros
                            return f"{prefixo}{valor_nfserv}{resto} R189={valor_r189}"
                        except (ValueError, IndexError):
                            # Se falhar, retorna o original
                            return detalhes
                    return detalhes
                    
                # Para notas faltantes
                if 'não encontrada no' in tipo or 'ausente' in tipo:
                    if 'ausente no NFSERV' in tipo or 'não encontrada no NFSERV' in tipo:
                        return f"DIVERGÊNCIA: Nota {row['NFSERV_ID']} presente no R189 mas não encontrada no NFSERV"
                    elif 'ausente no R189' in tipo or 'não encontrada no R189' in tipo:
                        return f"DIVERGÊNCIA: Nota {row['NFSERV_ID']} presente no NFSERV mas não encontrada no R189"
                    else:
                        return f"DIVERGÊNCIA: Nota {row['NFSERV_ID']} ausente em um dos sistemas"
                
                # Para CNPJs diferentes
                if 'CNPJ' in tipo:
                    return f"DIVERGÊNCIA: CNPJ diferente para nota {row['NFSERV_ID']} - NFSERV: {row['CNPJ NFSERV']}, R189: {row['CNPJ R189']}"
                    
                # Para valores diferentes
                if tipo == 'VALOR':
                    # Formatar valores para exibição adequada
                    valor_nfserv = row['Valor NFSERV']
                    valor_r189 = row['Valor R189']
                    
                    # Converter para string se ainda forem números
                    if isinstance(valor_nfserv, (int, float)):
                        valor_nfserv = f"{valor_nfserv:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                    if isinstance(valor_r189, (int, float)):
                        valor_r189 = f"{valor_r189:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                        
                    return f"DIVERGÊNCIA: Valor diferente para nota {row['NFSERV_ID']} - NFSERV: {valor_nfserv}, R189: {valor_r189}"
                
                # Para outros casos
                return detalhes
            
            # Aplicar a função para criar descrições mais claras
            divergences_df['Descrição Clara'] = divergences_df.apply(melhorar_descricao, axis=1)
            
            # 4. Ordenar o DataFrame
            divergences_df = divergences_df.sort_values(['ordem', 'Tipo', 'NFSERV_ID'])
            
            # 5. Criar versão final e remover colunas desnecessárias
            relatorio_final = divergences_df.drop(['ordem', 'Detalhes'], axis=1, errors='ignore')
            
            # 6. Reordenar colunas para melhor visualização
            ordem_colunas = [
                'Tipo', 'NFSERV_ID', 'Descrição Clara', 
                'CNPJ NFSERV', 'CNPJ R189', 
                'Valor NFSERV', 'Valor R189',
                'Data Verificação', 'Hora Verificação'
            ]
            
            # Manter apenas colunas que existem
            ordem_colunas = [col for col in ordem_colunas if col in relatorio_final.columns]
            relatorio_final = relatorio_final[ordem_colunas]
            
            # 7. Formatar valores monetários para exibição
            for col in ['Valor NFSERV', 'Valor R189']:
                # Cópia temporária do DataFrame para evitar avisos
                temp_df = relatorio_final.copy()
                
                # Processar cada linha individualmente para decidir a formatação
                for idx, row in temp_df.iterrows():
                    valor = row[col]
                    tipo = row['Tipo']
                    
                    # Se for um número e for uma linha de contagem, formatar como inteiro
                    if (isinstance(valor, (int, float)) or 
                       (isinstance(valor, str) and valor.replace('.', '').replace(',', '').isdigit())):
                        try:
                            valor_numerico = float(str(valor).replace(',', '.'))
                            
                            # Contagens (sem casas decimais)
                            if tipo.startswith('CONTAGEM_'):
                                relatorio_final.at[idx, col] = f"{int(valor_numerico)}"
                            # Outros valores (com casas decimais)
                            else:
                                relatorio_final.at[idx, col] = f"{valor_numerico:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                        except (ValueError, TypeError):
                            # Mantém o valor original se não conseguir converter
                            pass
            
            try:
                logger.info("Criando arquivo Excel na memória com formato simplificado")
                # Cria o arquivo Excel na memória
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    relatorio_final.to_excel(writer, index=False, sheet_name='Divergências NFSERV-R189')
                    
                    # Ajusta a largura das colunas
                    workbook = writer.book
                    worksheet = writer.sheets['Divergências NFSERV-R189']
                    
                    # Ajustar larguras das colunas
                    for i, col in enumerate(relatorio_final.columns):
                        if 'Descrição' in col:
                            # Coluna de descrição mais larga
                            worksheet.set_column(i, i, 60)
                        elif 'CNPJ' in col:
                            # CNPJs têm tamanho padrão
                            worksheet.set_column(i, i, 20)
                        elif 'Valor' in col:
                            # Valores financeiros
                            worksheet.set_column(i, i, 15)
                        else:
                            # Outras colunas com base no conteúdo
                            max_length = max(
                                relatorio_final[col].astype(str).apply(len).max(),
                                len(str(col))
                            )
                            worksheet.set_column(i, i, max_length + 2)
            
                output.seek(0)
                logger.info("Arquivo Excel criado com sucesso")
                
                # Nome do arquivo com timestamp
                timestamp = now.strftime('%Y%m%d_%H%M%S')
                report_name = f'{timestamp}_divergencias_nfserv_r189.xlsx'
                
                return {
                    "success": True,
                    "file_content": output,
                    "filename": report_name
                }
                
            except Exception as e:
                logger.exception(f"Erro ao criar arquivo Excel: {str(e)}")
                return {"success": False, "error": f"Erro ao criar arquivo Excel: {str(e)}"}
                
        except Exception as e:
            logger.exception(f"Erro inesperado ao gerar relatório Excel: {str(e)}")
            return {"success": False, "error": f"Erro inesperado ao gerar relatório Excel: {str(e)}"}

    async def generate_report(self):
        """
        Gera o relatório de divergências comparando NFSERV e R189.
        """
        try:
            logger.info("=== INICIANDO GERAÇÃO DE RELATÓRIO NFSERV vs R189 ===")
            
            # Caminhos dos arquivos no SharePoint
            consolidado_path = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"
            
            # Busca os arquivos consolidados no SharePoint
            logger.info("Baixando arquivo NFSERV_consolidado.xlsx")
            nfserv_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'NFSERV_consolidado.xlsx',
                consolidado_path
            )
            
            if nfserv_content is None:
                logger.error("Não foi possível baixar o arquivo NFSERV_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo NFSERV_consolidado.xlsx",
                    "show_popup": True
                }
            
            logger.info("Baixando arquivo R189_consolidado.xlsx")
            r189_content = self.sharepoint_auth.baixar_arquivo_sharepoint(
                'R189_consolidado.xlsx',
                consolidado_path
            )
            
            if r189_content is None:
                logger.error("Não foi possível baixar o arquivo R189_consolidado.xlsx")
                return {
                    "success": False,
                    "error": "Não foi possível baixar o arquivo R189_consolidado.xlsx",
                    "show_popup": True
                }
            
            # Lê os arquivos em DataFrames
            logger.info("Lendo arquivos Excel")
            try:
                nfserv_io = BytesIO(nfserv_content)
                r189_io = BytesIO(r189_content)
                
                # Listar todas as planilhas disponíveis nos arquivos
                nfserv_excel = pd.ExcelFile(nfserv_io)
                nfserv_sheets = nfserv_excel.sheet_names
                logger.info(f"Planilhas disponíveis em NFSERV_consolidado.xlsx: {nfserv_sheets}")
                
                r189_excel = pd.ExcelFile(r189_io)
                r189_sheets = r189_excel.sheet_names
                logger.info(f"Planilhas disponíveis em R189_consolidado.xlsx: {r189_sheets}")
                
                # Reabrir os BytesIO pois foram consumidos pelo ExcelFile
                nfserv_io = BytesIO(nfserv_content)
                r189_io = BytesIO(r189_content)
                
                # Usar a primeira planilha disponível para NFSERV e R189 se as específicas não existirem
                if 'NFSERV_consolidado' in nfserv_sheets:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name='NFSERV_consolidado')
                    logger.info("Usando planilha 'NFSERV_consolidado'")
                elif 'Consolidado_NFSERV' in nfserv_sheets:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name='Consolidado_NFSERV')
                    logger.info("Usando planilha 'Consolidado_NFSERV'")
                else:
                    df_nfserv = pd.read_excel(nfserv_io, sheet_name=nfserv_sheets[0])
                    logger.info(f"Usando primeira planilha disponível para NFSERV: {nfserv_sheets[0]}")
                
                if 'Consolidado_R189' in r189_sheets:
                    df_r189 = pd.read_excel(r189_io, sheet_name='Consolidado_R189')
                    logger.info("Usando planilha 'Consolidado_R189'")
                else:
                    df_r189 = pd.read_excel(r189_io, sheet_name=r189_sheets[0])
                    logger.info(f"Usando primeira planilha disponível para R189: {r189_sheets[0]}")
                
                logger.info(f"Linhas em NFSERV: {len(df_nfserv)}")
                logger.info(f"Linhas em R189: {len(df_r189)}")
            except Exception as e:
                logger.error(f"Erro ao ler arquivos Excel: {str(e)}")
                return {
                    "success": False,
                    "error": f"Erro ao ler arquivos Excel: {str(e)}",
                    "show_popup": True
                }
            
            if df_nfserv.empty:
                logger.error("Arquivo NFSERV_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo NFSERV_consolidado.xlsx está vazio",
                    "show_popup": True
                }
                
            if df_r189.empty:
                logger.error("Arquivo R189_consolidado.xlsx está vazio")
                return {
                    "success": False,
                    "error": "Erro: Arquivo R189_consolidado.xlsx está vazio",
                    "show_popup": True
                }
            
            # Verifica divergências
            logger.info("Verificando divergências")
            success, message, divergences_df = await self.check_divergences(df_nfserv, df_r189)
            
            if not success:
                logger.error(f"Erro na verificação: {message}")
                return {
                    "success": False,
                    "error": message,
                    "show_popup": True
                }
            
            # Se encontrou divergências, gera o relatório Excel
            if not divergences_df.empty:
                logger.info(f"Gerando relatório Excel com {len(divergences_df)} divergências")
                report_result = await self.generate_excel_report(divergences_df)
                
                if not report_result.get("success", False):
                    error_msg = report_result.get("error", "Erro desconhecido ao gerar relatório")
                    logger.error(f"Erro ao gerar relatório: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "show_popup": True
                    }
                
                # Nome do arquivo de relatório
                report_filename = report_result.get("filename")
                if not report_filename:
                    logger.error("Nome do arquivo de relatório não encontrado no resultado")
                    return {
                        "success": False,
                        "error": "Nome do arquivo de relatório não encontrado",
                        "show_popup": True
                    }
                
                file_content = report_result.get("file_content")
                if not file_content:
                    logger.error("Conteúdo do arquivo de relatório não encontrado no resultado")
                    return {
                        "success": False,
                        "error": "Conteúdo do arquivo de relatório não encontrado",
                        "show_popup": True
                    }
                
                # Envia o relatório para o SharePoint
                logger.info(f"Enviando relatório {report_filename} para o SharePoint")
                relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS/NFSERV_R189"
                
                # Usar o método assíncrono do SharePointAuth
                upload_success = await self.sharepoint_auth.enviar_arquivo_sharepoint(
                    conteudo=file_content.getvalue(),
                    nome_arquivo=report_filename,
                    pasta=relatorios_path
                )
                
                if not upload_success:
                    logger.error("Erro ao enviar relatório para o SharePoint")
                    return {
                        "success": False,
                        "error": "Erro ao enviar relatório para o SharePoint",
                        "show_popup": True
                    }
                
                logger.info("Relatório enviado com sucesso")
                return {
                    "success": True,
                    "message": f"Relatório de divergências gerado e salvo com sucesso!\n\nResumo das divergências encontradas:\n{message}\n\nO arquivo foi salvo na pasta RELATÓRIOS/NFSERV_R189 no SharePoint.",
                    "show_popup": True
                }
            
            logger.info("Nenhuma divergência encontrada, não é necessário gerar relatório")
            return {
                "success": True,
                "message": message,
                "show_popup": True
            }
            
        except Exception as e:
            logger.exception(f"Erro inesperado ao gerar relatório: {str(e)}")
            return {
                "success": False,
                "error": f"Erro inesperado ao gerar relatório: {str(e)}\nPor favor, verifique:\n1. Se os arquivos consolidados existem no SharePoint\n2. Se você tem permissão de acesso\n3. Se a conexão com o SharePoint está funcionando",
                "show_popup": True
            }
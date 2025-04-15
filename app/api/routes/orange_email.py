from fastapi import APIRouter, HTTPException
import httpx
import logging
from typing import Dict, Any, Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# URL do fluxo do Power Automate
POWER_AUTOMATE_URL = "https://prod-56.westus.logic.azure.com:443/workflows/3d9aba09a8e44e749fb2a2dd9d94e38a/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=GXqnWZyH4DMZTl98u1-gQDacjYxZRQeQ8Uj93_pASiY"

@router.get("/check-orange-email-notifications")
async def check_orange_email_notifications(skip_validation: bool = False) -> Dict[str, Any]:
    """
    Verifica notificações de email do Orange através do Power Automate e determina se o processo pode continuar.
    
    Este endpoint consulta o fluxo do Power Automate para verificar se existem notificações de email do Orange
    que precisam ser processadas. O fluxo retorna a quantidade de emails disponíveis, e o endpoint determina
    se o processo de atualização pode continuar com base nessa quantidade.
    
    Args:
        skip_validation (bool, optional): Se True, ignora a validação do número de emails. Default é False.
    
    Returns:
        Dict[str, Any]: Resultado da operação contendo:
            - success (bool): Se a operação foi bem-sucedida
            - message (str): Mensagem descritiva do resultado
            - data (Optional[Dict]): Dados retornados pelo Power Automate, se disponíveis
            - email_count (int): Número de emails encontrados
            - can_proceed (bool): Se o processo pode continuar (email_count > 0)
    """
    try:
        logger.info("Iniciando chamada ao fluxo do Power Automate para obter emails do Orange")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Usando GET em vez de POST, conforme exigido pelo Power Automate
            response = await client.get(POWER_AUTOMATE_URL)
            
            if response.status_code != 200:
                logger.error(f"Erro ao chamar o Power Automate: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "message": f"Erro ao chamar o Power Automate: {response.status_code}",
                    "email_count": 0,
                    "can_proceed": False
                }
            
            # Processar a resposta
            try:
                response_data = response.json()
            except Exception as e:
                logger.error(f"Erro ao fazer parse do JSON da resposta: {str(e)}")
                response_data = None

            # Logar a resposta recebida para troubleshooting
            logger.debug(f"Resposta do Power Automate: {response_data}")

            # Extrair o número de emails da resposta
            email_count = 0
            try:
                if isinstance(response_data, int):
                    # Caso a resposta já seja um inteiro
                    email_count = response_data
                elif isinstance(response_data, dict):
                    # Estrutura esperada: outputs > Get_emails_(V3) > body > value
                    outputs = response_data.get('outputs')
                    if outputs and isinstance(outputs, dict):
                        get_emails = outputs.get('Get_emails_(V3)')
                        if get_emails and isinstance(get_emails, dict):
                            body = get_emails.get('body', {})
                            value = body.get('value', [])
                            if isinstance(value, list):
                                email_count = len(value)
                            elif isinstance(value, int):
                                email_count = value
                logger.info(f"Encontrados {email_count} emails do Orange")
            except Exception as e:
                logger.error(f"Erro ao extrair contagem de emails da resposta: {str(e)}")

            # Determinar se o processo pode continuar
            can_proceed = skip_validation or email_count > 0
            
            return {
                "success": True,
                "message": f"Encontrados {email_count} emails do Orange" + 
                           (". Processo pode continuar." if can_proceed else ". Processo não deve continuar."),
                "email_count": email_count,
                "can_proceed": can_proceed
            }
    
    except Exception as e:
        logger.exception(f"Erro ao processar requisição de emails do Orange: {str(e)}")
        return {
            "success": False,
            "message": f"Erro ao processar requisição: {str(e)}",
            "email_count": 0,
            "can_proceed": False
        }


@router.post("/validate-orange-email-notifications")
async def validate_orange_email_notifications(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Valida se existem notificações de email do Orange e determina se o processo pode continuar.
    Este endpoint pode receber um payload opcional com parâmetros adicionais para personalizar a validação.
    
    Args:
        payload (Dict[str, Any], optional): Parâmetros adicionais para a validação, como:
            - skip_validation (bool): Se True, ignora a validação do número de emails.
    
    Returns:
        Dict[str, Any]: Resultado da validação contendo:
            - success (bool): Se a operação foi bem-sucedida
            - message (str): Mensagem descritiva do resultado
            - can_proceed (bool): Se o processo pode continuar
            - email_count (int): Número de emails encontrados
    """
    try:
        logger.info("Validando notificações de email do Orange")
        
        # Obter o resultado do endpoint de verificação de notificações
        email_result = await check_orange_email_notifications(
            skip_validation=payload.get("skip_validation", False) if payload else False
        )
        
        if not email_result["success"]:
            return {
                "success": False,
                "message": f"Falha ao verificar emails: {email_result['message']}",
                "can_proceed": False
            }
        
        return {
            "success": True,
            "message": email_result["message"],
            "can_proceed": email_result["can_proceed"],
            "email_count": email_result["email_count"]
        }
    
    except Exception as e:
        logger.exception(f"Erro ao validar emails do Orange: {str(e)}")
        return {
            "success": False,
            "message": f"Erro ao validar emails: {str(e)}",
            "can_proceed": False
        }

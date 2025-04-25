from fastapi import APIRouter, HTTPException
import httpx
import logging
from typing import Dict, Any, Optional
import asyncio
import time
import loguru
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

router = APIRouter()
logger = logging.getLogger(__name__)

POWER_AUTOMATE_URL = "https://prod-56.westus.logic.azure.com:443/workflows/3d9aba09a8e44e749fb2a2dd9d94e38a/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=GXqnWZyH4DMZTl98u1-gQDacjYxZRQeQ8Uj93_pASiY"

def _extract_email_count_from_pa_output(output_data: Any) -> int:
    try:
        if isinstance(output_data, int):
            logger.info(f"Extracted count (direct int): {output_data}")
            return output_data
        elif isinstance(output_data, dict):
            if 'email_count' in output_data and isinstance(output_data['email_count'], int):
                 count = output_data['email_count']
                 logger.info(f"Extracted count from 'email_count' key: {count}")
                 return count
            elif 'value' in output_data and isinstance(output_data['value'], list):
                 count = len(output_data['value'])
                 logger.info(f"Extracted count from length of 'value' list: {count}")
                 return count
            else:
                 logger.warning(f"Could not find expected key/structure for count in dict: {output_data}")
                 return 0
        else:
             logger.warning(f"Unexpected PA output format for count extraction: {type(output_data)}")
             return 0
    except Exception as e:
        logger.error(f"Error extracting email count from PA output: {e}")
        return 0

@router.get("/check-orange-email-notifications")
async def check_orange_email_notifications(skip_validation: bool = False) -> Dict[str, Any]:
    email_count = 0
    can_proceed = False
    start_time = time.monotonic()
    REQUEST_TIMEOUT = 30.0  
    POLLING_INTERVAL_SECONDS = 15 
    MAX_POLLING_DURATION_SECONDS = 600 

    if not POWER_AUTOMATE_URL or "DEFINIR_URL" in POWER_AUTOMATE_URL: 
         logger.error("Power Automate URL (POWER_AUTOMATE_URL) is not configured correctly.")
         raise HTTPException(status_code=500, detail="Internal config error: Power Automate URL missing.")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        location_url = None
        final_output = None
        flow_status = "Initiating"

        try:
            logger.info(f"Initiating GET to Power Automate: {POWER_AUTOMATE_URL}")
            initial_response = await client.get(POWER_AUTOMATE_URL)

            if initial_response.status_code == 202: 
                # Log ALL headers from the initial 202 response
                logger.info(f"Initial 202 Response Headers: {initial_response.headers}")
                # Log the body of the initial 202 response
                try:
                    initial_body = await initial_response.aread()
                    logger.info(f"Initial 202 Response Body: {initial_body.decode()}")
                except Exception as read_err:
                    logger.warning(f"Could not read initial 202 response body: {read_err}")

                run_id = initial_response.headers.get("x-ms-workflow-run-id")
                location_url = initial_response.headers.get("Location") # Operation status URL
                logger.info(f"PA flow started (async). Run ID: {run_id}")
                logger.info(f"Status URL from Location header: {location_url}")

                if not location_url:
                    logger.error("Could not find 'Location' header in 202 response.")
                    raise HTTPException(status_code=500, detail="Failed to get status URL from Power Automate.")

                # Usar diretamente a URL do cabeçalho Location para polling
                logger.info(f"Usando URL do cabeçalho Location para polling: {location_url}")

                # --- Start Polling Loop using Location URL --- 
                start_time = time.monotonic()
                while time.monotonic() - start_time < MAX_POLLING_DURATION_SECONDS:
                    logger.info(f"Polling PA status at: {location_url}")
                    try:
                        # Use a separate timeout for polling requests
                        async with httpx.AsyncClient(timeout=15.0) as poll_client:
                            status_response = await poll_client.get(location_url)
                        logger.debug(f"Polling response status code: {status_response.status_code}")

                        if status_response.status_code == 200:
                            # Processar resposta 200 OK
                            try:
                                run_details = status_response.json()
                                logger.info(f"Polling response 200 OK. Content: {run_details}")
                                
                                # Tentar extrair status e resultado
                                flow_status = None
                                email_count = None
                                
                                # Verificar se é uma resposta direta com email_count
                                if isinstance(run_details, dict) and "email_count" in run_details:
                                    email_count = run_details.get("email_count")
                                    flow_status = "Succeeded"
                                    logger.info(f"Resultado direto encontrado: email_count={email_count}")
                                elif isinstance(run_details, dict) and "emailCount" in run_details:
                                    email_count = run_details.get("emailCount")
                                    flow_status = "Succeeded"
                                    logger.info(f"Resultado direto encontrado: emailCount={email_count}")
                                else:
                                    # Verificar estrutura padrão do Power Automate
                                    properties = run_details.get("properties", {})
                                    flow_status = properties.get("status")
                                    logger.info(f"PA flow status: {flow_status}")
                                
                                # Se o fluxo foi concluído com sucesso
                                if flow_status == "Succeeded" or email_count is not None:
                                    # Se já temos email_count, retornar resultado
                                    if email_count is not None:
                                        if isinstance(email_count, str):
                                            try:
                                                email_count = int(email_count)
                                            except:
                                                email_count = 0
                                        
                                        if email_count > 0:
                                            logger.info(f"Flow concluído com sucesso. {email_count} emails encontrados.")
                                            return {
                                                "status": "success",
                                                "message": f"{email_count} emails encontrados.",
                                                "email_count": email_count,
                                                "can_proceed": True
                                            }
                                        else:
                                            logger.info("Flow concluído com sucesso. Nenhum email encontrado.")
                                            return {
                                                "status": "no_emails",
                                                "message": "Nenhum email encontrado.",
                                                "email_count": 0,
                                                "can_proceed": False
                                            }
                                    
                                    # Tentar extrair outputs
                                    outputs = properties.get("outputs", {})
                                    if outputs:
                                        logger.info(f"Outputs encontrados: {outputs}")
                                        if isinstance(outputs, dict):
                                            email_count = outputs.get("emailCount") or outputs.get("email_count")
                                            if email_count is not None:
                                                logger.info(f"Email count extraído dos outputs: {email_count}")
                                                
                                                if isinstance(email_count, str):
                                                    try:
                                                        email_count = int(email_count)
                                                    except:
                                                        email_count = 0
                                                
                                                if email_count > 0:
                                                    logger.info(f"Flow concluído com sucesso. {email_count} emails encontrados.")
                                                    return {
                                                        "status": "success",
                                                        "message": f"{email_count} emails encontrados.",
                                                        "email_count": email_count,
                                                        "can_proceed": True
                                                    }
                                                else:
                                                    logger.info("Flow concluído com sucesso. Nenhum email encontrado.")
                                                    return {
                                                        "status": "no_emails",
                                                        "message": "Nenhum email encontrado.",
                                                        "email_count": 0,
                                                        "can_proceed": False
                                                    }
                                    
                                    # Se não encontrou email_count, mas o fluxo foi concluído com sucesso,
                                    # retornar um valor padrão
                                    logger.warning("Flow concluído com sucesso, mas não foi possível extrair a contagem de emails.")
                                    return {
                                        "status": "success",
                                        "message": "Fluxo concluído com sucesso, mas não foi possível determinar a contagem de emails.",
                                        "email_count": 0,
                                        "can_proceed": False
                                    }
                                elif flow_status in ["Failed", "Cancelled", "TimedOut", "Aborted"]:
                                    logger.error(f"PA flow did not succeed. Final status: {flow_status}")
                                    error_info = properties.get("error", "No error details provided.")
                                    return {
                                        "status": "error",
                                        "message": f"Power Automate flow {flow_status}. Error: {error_info}",
                                        "email_count": 0,
                                        "can_proceed": False
                                    }
                                elif flow_status == "Running":
                                    logger.info("PA flow still running...")
                                    # Continue polling after interval
                                else:
                                    logger.warning(f"Unknown PA flow status encountered: {flow_status}")
                                    # Continue polling, but log warning
                            except Exception as parse_err:
                                logger.error(f"Error parsing 200 OK response: {parse_err}", exc_info=True)
                                # Log the raw response for debugging
                                try:
                                    raw_text = await status_response.atext()
                                    logger.info(f"Raw 200 OK response: {raw_text}")
                                    
                                    # Tenta extrair qualquer número da resposta como último recurso
                                    import re
                                    numbers = re.findall(r'\d+', raw_text)
                                    if numbers:
                                        email_count = int(numbers[0])
                                        logger.info(f"Extraído número da resposta como email_count: {email_count}")
                                        
                                        if email_count > 0:
                                            return {
                                                "status": "success",
                                                "message": f"{email_count} emails encontrados.",
                                                "email_count": email_count,
                                                "can_proceed": True
                                            }
                                        else:
                                            return {
                                                "status": "no_emails",
                                                "message": "Nenhum email encontrado.",
                                                "email_count": 0,
                                                "can_proceed": False
                                            }
                                except:
                                    pass
                                # Continue polling
                        elif status_response.status_code == 202:
                            logger.info("Polling response 202 Accepted. PA flow still running.")
                            # Continue polling
                        elif status_response.status_code == 401:
                            # Ignorar erro 401 e continuar o polling
                            logger.warning("Polling response 401 Unauthorized. Ignorando e continuando polling.")
                            # Continue polling
                        else:
                            logger.error(f"Unexpected status code during polling: {status_response.status_code}")
                            try:
                                error_text = await status_response.atext()
                                logger.error(f"Error response: {error_text}")
                            except:
                                pass
                            # Continue polling instead of raising an exception
                    
                    except httpx.RequestError as poll_exc:
                        logger.error(f"HTTP error during polling: {poll_exc}", exc_info=True)
                        # Continue polling
                    except Exception as poll_parse_err:
                        logger.error(f"Error during polling: {poll_parse_err}", exc_info=True)
                        # Continue polling

                    # Wait before the next poll
                    await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                
                # If the loop finishes without returning (timeout)
                logger.error(f"Polling timed out after {MAX_POLLING_DURATION_SECONDS} seconds.")
                return {
                    "status": "timeout",
                    "message": f"Tempo limite excedido ao aguardar a conclusão do fluxo do Power Automate.",
                    "email_count": 0,
                    "can_proceed": False
                }

            elif initial_response.status_code == 200: 
                logger.info("PA responded synchronously (200 OK).")
                try:
                    final_output = initial_response.json()
                    flow_status = 'Succeeded'
                    email_count = _extract_email_count_from_pa_output(final_output)
                    logger.info(f"Processed sync response. Count: {email_count}")
                except Exception as e:
                    logger.error(f"Error parsing sync 200 OK response: {e}")
                    flow_status = 'Failed' 

            else: 
                logger.error(f"Initial call to PA failed: {initial_response.status_code} - {initial_response.text}")
                initial_response.raise_for_status() 

            can_proceed = success and (skip_validation or email_count > 0)

            # Melhorar a construção da mensagem final
            if flow_status == 'TimedOut':
                final_message = f"A verificação excedeu o tempo limite ({MAX_POLLING_DURATION_SECONDS}s). Status: Timeout. Verificação parcial encontrou {email_count} emails."
                can_proceed = False # Timeout impede o prosseguimento
            elif success:
                if email_count > 0:
                    final_message = f"Verificação concluída com sucesso. {email_count} emails encontrados."
                    # can_proceed já foi definido corretamente acima
                else: # success is True, email_count is 0
                    final_message = "Verificação concluída com sucesso. Nenhum email novo encontrado."
                    can_proceed = False # Não prosseguir se não houver emails (a menos que skip_validation seja True, já tratado)
            else: # Not success and not TimedOut (e.g., Failed, Cancelled)
                final_message = f"Falha na verificação. Status final: {flow_status}. Emails encontrados: {email_count}."
                can_proceed = False # Falha impede o prosseguimento

            log_message = (
                f"Resultado final: success={success}, status='{flow_status}', "
                f"email_count={email_count}, can_proceed={can_proceed}, "
                f"skip_validation={skip_validation}, message='{final_message}'"
            )
            logger.info(log_message)

            return {
                "success": success,
                "message": final_message,
                "email_count": email_count,
                "can_proceed": can_proceed
            }

        except httpx.RequestError as exc:
            logger.error(f"HTTP request failed: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to communicate with Power Automate: {exc}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

@router.post("/validate-orange-email-notifications")
async def validate_orange_email_notifications(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        logger.info("Attempting to validate Orange email notifications...") # Log ajustado

        email_result = await check_orange_email_notifications(
            skip_validation=payload.get("skip_validation", False) if payload else False
        )

        # Case 1: The underlying check failed completely (e.g., API error, flow failed)
        if email_result.get("status") != "success":
            logger.warning(f"Underlying email check failed. Result: {email_result}")
            # Return a specific failure message indicating the check itself failed
            return {
                "success": False,
                "message": f"Falha ao verificar emails no Power Automate. Detalhes: {email_result['message']}",
                "can_proceed": False,
                "email_count": email_result.get("email_count", 0) # Include count if available
            }

        # Case 2: The check succeeded, but we cannot proceed (emails found, but validation not skipped OR no emails found)
        if not email_result["can_proceed"]:
            logger.info(f"Email check succeeded, but cannot proceed. Result: {email_result}")
            # Return success=True because the check *worked*, but indicate why we can't proceed.
            # Use the message from the check result as it should already be informative.
            return {
                "success": True, # The check operation itself succeeded
                "message": email_result["message"], # e.g., "101 emails encontrados" or "Nenhum email novo"
                "can_proceed": False, # Explicitly state we cannot proceed
                "email_count": email_result["email_count"]
            }

        # Case 3: The check succeeded AND we can proceed (emails found AND skip_validation=True)
        logger.info(f"Email check succeeded and can proceed. Result: {email_result}")
        return {
            "success": True,
            "message": email_result["message"], # e.g., "101 emails encontrados."
            "can_proceed": True,
            "email_count": email_result["email_count"]
        }

    except Exception as e:
        logger.exception(f"Unexpected error during email validation endpoint: {str(e)}")
        return {
            "success": False,
            "message": f"Erro interno no servidor ao tentar validar emails: {str(e)}",
            "can_proceed": False
        }

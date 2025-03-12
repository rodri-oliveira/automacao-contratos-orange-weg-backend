import logging
import sys

def configure_logging():
    """
    Configura o logging para exibir informações detalhadas no console
    """
    # Configuração básica
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')
        ]
    )
    
    # Configurar loggers específicos
    validation_logger = logging.getLogger('app.api.routes.validation')
    validation_logger.setLevel(logging.DEBUG)
    
    reports_logger = logging.getLogger('app.core.reports')
    reports_logger.setLevel(logging.DEBUG)
    
    # Adicionar handler para console com formatação colorida
    try:
        import colorlog
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
        validation_logger.addHandler(handler)
        reports_logger.addHandler(handler)
    except ImportError:
        # Se colorlog não estiver disponível, usar formatação padrão
        pass 
# import msal
# import json
# import os
# from pathlib import Path
# from dotenv import load_dotenv

# # Carregar variáveis de ambiente
# load_dotenv()

# # Configurações de autenticação
# tenant_id = os.getenv("TENANT_ID")
# client_id = os.getenv("EMAIL_CLIENT_ID")
# client_secret = os.getenv("EMAIL_CLIENT_SECRET")

# # Caminho para o arquivo de cache
# token_cache_path = Path("token_cache.json")

# # Definir escopo para permissões delegadas
# scopes = ["Mail.Read", "Mail.Read.Shared", "User.Read"]

# def authenticate_interactive():
#     """
#     Inicia um fluxo de autenticação interativa e salva o token
#     """
#     print("Iniciando processo de autenticação interativa...")
    
#     # Criar aplicativo MSAL
#     app = msal.PublicClientApplication(
#         client_id=client_id,
#         authority=f"https://login.microsoftonline.com/{tenant_id}"
#     )
    
#     # Iniciar fluxo de dispositivo
#     flow = app.initiate_device_flow(scopes=scopes)
    
#     if "user_code" not in flow:
#         print(f"Falha ao iniciar fluxo de dispositivo: {flow.get('error')}")
#         print(f"Descrição: {flow.get('error_description')}")
#         return None
    
#     # Exibir instruções para o usuário
#     print("\n" + "=" * 40)
#     print(flow["message"])
#     print("=" * 40 + "\n")
    
#     # Aguardar autenticação do usuário
#     result = app.acquire_token_by_device_flow(flow)
    
#     if "access_token" in result:
#         print("Token obtido com sucesso via autenticação interativa!")
        
#         # Salvar token para uso futuro
#         cache_data = {
#             "access_token": result.get("access_token"),
#             "refresh_token": result.get("refresh_token"),
#             "expires_on": result.get("expires_on", 0),
#             "scope": result.get("scope", "")
#         }
        
#         with open(token_cache_path, 'w') as f:
#             json.dump(cache_data, f)
            
#         print(f"Token salvo em {token_cache_path}")
        
#         # Mostrar quando expira
#         if "expires_in" in result:
#             print(f"O token expira em {result['expires_in']/3600:.2f} horas")
        
#         return result["access_token"]
#     else:
#         print(f"Falha ao obter token: {result.get('error')}")
#         print(f"Descrição: {result.get('error_description')}")
#         return None

# if __name__ == "__main__":
#     print(f"Iniciando autenticação para Microsoft Graph API")
#     print(f"Client ID: {client_id}")
#     print(f"Tenant ID: {tenant_id}")
#     print(f"Escopos solicitados: {', '.join(scopes)}")
    
#     # Verificar se já existe um cache
#     if token_cache_path.exists():
#         choice = input("Já existe um token em cache. Deseja substituí-lo? (s/n): ")
#         if choice.lower() != "s":
#             print("Operação cancelada pelo usuário")
#             exit(0)
    
#     # Iniciar autenticação
#     token = authenticate_interactive()
    
#     if token:
#         print("\nAutenticação bem-sucedida! O sistema agora pode acessar emails da sua conta.")
#         print(f"Arquivo de cache: {token_cache_path}")
#         print("\nSugestão: Execute o aplicativo principal agora para processar os emails")
#     else:
#         print("\nFalha na autenticação. Por favor, tente novamente ou verifique as configurações.") 
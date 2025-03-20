# Definir a imagem base - substitua pela versão Python correta
FROM python:3.12-slim

# Definir diretório de trabalho
WORKDIR /opt/app

# Copiar arquivos de dependências
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código da aplicação
COPY . .

# Expor a porta (substitua pela porta que sua aplicação usa)
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 
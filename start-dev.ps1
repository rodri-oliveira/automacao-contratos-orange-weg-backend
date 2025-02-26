# Configurar PYTHONPATH
$env:PYTHONPATH = "C:\weg\Aline-Contratos\automacaofinancasbackend"

# Iniciar o backend
Write-Host "Iniciando o backend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command cd C:\weg\Aline-Contratos\automacaofinancasbackend; python run_server.py"

# Aguardar um pouco para o backend iniciar
Start-Sleep -Seconds 3

# Iniciar o frontend
Write-Host "Iniciando o frontend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command cd C:\weg\Aline-Contratos\automacaofinancasfrontend; npm start"
import React, { useState, useCallback } from 'react';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('R189');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState({
    R189: 'Aguardando processamento',
    QPE: 'Aguardando processamento',
    SPB: 'Aguardando processamento',
    NFSERV: 'Aguardando processamento',
    MUN_CODE: 'Aguardando processamento'
  });
  const [selectedFiles, setSelectedFiles] = useState([]);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
  };

  const handleSearchFiles = useCallback(async () => {
    try {
        setLoading(true);
        console.log('Buscando arquivos para a aba:', activeTab);
        
        const response = await fetch(`http://localhost:8000/r189/api/arquivos/${activeTab}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
        });

        console.log('Status da resposta:', response.status);
        const data = await response.json();
        console.log('Dados recebidos:', data);
        
        if (data.success) {
            setFiles(data.arquivos);
        } else {
            throw new Error(data.detail || 'Erro ao buscar arquivos');
        }
    } catch (error) {
        console.error('Erro detalhado:', error);
        setError(`Erro ao buscar arquivos: ${error.message}`);
    } finally {
        setLoading(false);
    }
}, [activeTab]);

  const handleProcessFiles = async () => {
    try {
        setLoading(true);
        console.log('Iniciando processamento dos arquivos:', selectedFiles);

        const response = await fetch('/r189/process', { // Note o novo caminho
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ files: selectedFiles }) // Alterado para match com o backend
        });

        console.log('Status da resposta:', response.status);
        const data = await response.json();
        console.log('Resposta completa:', data);

        if (!response.ok) {
            throw new Error(data.detail || JSON.stringify(data));
        }

        // Atualizar status baseado nos resultados
        const sucessos = data.results.filter(p => p.status === "success").length;
        const total = data.results.length;
        
        setStatus(prevStatus => ({
            ...prevStatus,
            [activeTab]: `Processado ${sucessos}/${total} arquivos`
        }));

    } catch (error) {
        console.error('Erro detalhado:', error);
        setError(`Erro ao processar arquivos: ${error.message}`);
        setStatus(prevStatus => ({
            ...prevStatus,
            [activeTab]: 'Erro no processamento'
        }));
    } finally {
        setLoading(false);
    }
};

  const handleResetProcess = () => {
    setFiles([]);
    setStatus({
      R189: 'Aguardando processamento',
      QPE: 'Aguardando processamento',
      SPB: 'Aguardando processamento',
      NFSERV: 'Aguardando processamento',
      MUN_CODE: 'Aguardando processamento'
    });
  };

  const handleFileSelection = (fileName) => {
    if (selectedFiles.includes(fileName)) {
      setSelectedFiles(selectedFiles.filter((file) => file !== fileName));
    } else {
      setSelectedFiles([...selectedFiles, fileName]);
    }
  };

  return (
    <div className="App">
      <div className="app-header">
        <h1>Automação de Contratos - Finanças</h1>
        <button className="reset-button" onClick={handleResetProcess}>
          Resetar Processo
        </button>
      </div>

      <div className="tab-container">
        <div className="tabs">
          {['R189', 'QPE', 'SPB', 'NFSERV', 'MUN_CODE'].map(tab => (
            <button
              key={tab}
              className={`tab-button ${activeTab === tab ? 'active' : ''}`}
              onClick={() => handleTabChange(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="tab-content">
          <div className="section-container">
            <div className="section-header">Arquivos</div>
            <div className="section-content">
              <div className="button-container">
                <button className="action-button" onClick={handleSearchFiles}>
                  Buscar Arquivos
                </button>
                <button className="action-button" onClick={handleProcessFiles}>
                  Processar Arquivos
                </button>
              </div>
              
              {loading && <p>Carregando...</p>}
              {error && <p className="error-message">{error}</p>}
              
              <div className="files-section">
                {files && files.length > 0 ? (
                  <ul className="file-list">
                    {files.map((file, index) => (
                      <li
                        key={index}
                        className={`file-item ${selectedFiles.includes(file.nome) ? 'selected' : ''}`}
                        onClick={() => handleFileSelection(file.nome)}
                      >
                        {file.nome}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-files">Nenhum arquivo encontrado</p>
                )}
              </div>
            </div>
          </div>

          <div className="section-container">
            <div className="section-header">Validações</div>
            <div className="section-content">
              {activeTab === 'R189' && (
                <>
                  <button className="validation-button" disabled>
                    1. Verificar Divergências R189
                  </button>
                  <button className="validation-button" disabled>
                    2. Verificar Divergências QPE vs R189
                  </button>
                  <button className="validation-button" disabled>
                    3. Verificar Divergências SPB vs R189
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="status-bar">
        {Object.entries(status).map(([key, value]) => (
          <div key={key} className="status-item">
            Status {key}: {value}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;

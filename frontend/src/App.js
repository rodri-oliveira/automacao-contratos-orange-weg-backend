import React, { useState, useEffect } from 'react';
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

  const handleSearchFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      console.log(`Buscando arquivos para a aba: ${activeTab}`);
      
      const response = await fetch(`/api/arquivos/${activeTab}`);
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Dados recebidos da API:', data);
      
      const arquivos = data.arquivos || [];
      setFiles(arquivos);
      
      // Seleciona todos os arquivos por padrão
      setSelectedFiles(arquivos.map(file => file.nome));
      
      console.log('Estado files após atualização:', data.arquivos);
    } catch (error) {
      console.error('Erro detalhado:', error);
      setError('Erro ao buscar arquivos. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleProcessFiles = async () => {
    if (!selectedFiles.length) {
      setError('Selecione pelo menos um arquivo para processar.');
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      console.log('Arquivos selecionados para processamento:', selectedFiles);
      
      const response = await fetch(`/api/processar/${activeTab}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(selectedFiles)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      console.log('Resultado do processamento:', result);

      if (result.status === 'success') {
        // Atualiza o status do processamento
        setStatus(prev => ({
          ...prev,
          [activeTab]: 'Processamento concluído com sucesso'
        }));

        // Se for R189 e processado com sucesso, habilita a próxima aba
        if (activeTab === 'R189') {
          setStatus(prev => ({
            ...prev,
            QPE: true
          }));
        }

        // Mostra mensagem de sucesso
        alert('Arquivos processados com sucesso!');
      } else {
        throw new Error(result.mensagem || 'Erro no processamento dos arquivos');
      }

    } catch (error) {
      console.error('Erro ao processar arquivos:', error);
      setError(error.message);
      setStatus(prev => ({
        ...prev,
        [activeTab]: 'Erro no processamento'
      }));
      alert(`Erro no processamento: ${error.message}`);
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

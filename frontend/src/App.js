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
        setError(null);
        console.log('Iniciando busca para:', activeTab);
        
        const response = await fetch(`http://localhost:8000/api/arquivos/${activeTab}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        });

        console.log('Status:', response.status);
        const data = await response.json();
        console.log('Dados:', data);

        if (response.ok) {
            if (data.success && data.arquivos) {
                setFiles(data.arquivos);
            } else {
                throw new Error(data.detail || 'Erro desconhecido');
            }
        } else {
            throw new Error(data.detail || 'Erro na requisição');
        }
    } catch (error) {
        console.error('Erro completo:', error);
        setError(`Erro ao buscar arquivos: ${error.message}`);
        setFiles([]);
    } finally {
        setLoading(false);
    }
}, [activeTab]);

  const handleProcessFiles = async () => {
    try {
        if (selectedFiles.length === 0) {
            setError("Por favor, selecione pelo menos um arquivo para processar.");
            return;
        }

        setLoading(true);
        console.log('=== INICIANDO PROCESSAMENTO DOS ARQUIVOS ===');
        console.log('Tipo de arquivo:', activeTab);
        console.log('Arquivos selecionados:', selectedFiles);

        // Endpoint diferente dependendo do tipo de arquivo
        const endpoint = activeTab === 'QPE' 
            ? 'http://localhost:8000/qpe/process'
            : 'http://localhost:8000/api/processar/r189';
        
        console.log('Usando endpoint:', endpoint);
        console.log('Payload:', JSON.stringify(selectedFiles));

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(selectedFiles)
        });

        console.log('Status da resposta:', response.status);
        const data = await response.json();
        console.log('Dados da resposta:', data);
        
        if (data.success) {
            console.log('Processamento concluído com sucesso');
            setStatus(prevStatus => ({
                ...prevStatus,
                [activeTab]: 'Processamento concluído'
            }));
            setSelectedFiles([]);
            alert('Arquivos processados com sucesso!');
        } else {
            console.error('Erro na resposta:', data);
            throw new Error(data.error || 'Erro no processamento');
        }
    } catch (error) {
        console.error('Erro completo:', error);
        setStatus(prevStatus => ({
            ...prevStatus,
            [activeTab]: 'Erro no processamento'
        }));
        setError(`Erro ao processar arquivos: ${error.message}`);
    } finally {
        setLoading(false);
        console.log('=== FIM DO PROCESSAMENTO ===');
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

  // Melhore a função handleSelectAll
const handleSelectAll = () => {
    if (selectedFiles.length === files.length) {
        // Se todos estão selecionados, desseleciona todos
        setSelectedFiles([]);
    } else {
        // Seleciona todos os arquivos disponíveis
        const allFileNames = files.map(file => file.nome);
        setSelectedFiles(allFileNames);
    }
};

  const FileList = () => {
    if (error) return <div style={{color: 'red'}}>{error}</div>;
    if (files.length === 0 && !error && !loading) return null;
    if (files.length === 0) return <div>Nenhum arquivo encontrado</div>;

    return (
        <div className="file-list">
            <div className="selection-header">
                <label className="select-all-label">
                    <input
                        type="checkbox"
                        className="select-all-checkbox"
                        checked={selectedFiles.length === files.length}
                        onChange={handleSelectAll}
                    />
                    <span>Selecionar Todos</span>
                </label>
                <span className="selected-count">
                    ({selectedFiles.length} de {files.length} selecionados)
                </span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th className="checkbox-column"></th>
                        <th>Nome</th>
                        <th>Tamanho</th>
                        <th>Modificado</th>
                    </tr>
                </thead>
                <tbody>
                    {files.map((file, index) => (
                        <tr 
                            key={index}
                            className={selectedFiles.includes(file.nome) ? 'selected-row' : ''}
                        >
                            <td className="checkbox-column">
                                <input
                                    type="checkbox"
                                    checked={selectedFiles.includes(file.nome)}
                                    onChange={() => handleFileSelection(file.nome)}
                                />
                            </td>
                            <td>{file.nome}</td>
                            <td>{(file.tamanho / 1024).toFixed(2)} KB</td>
                            <td>{new Date(file.modificado).toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
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
              {!loading && error && <p className="error-message">{error}</p>}
              
              <div className="files-section">
                {!loading && <FileList />}
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

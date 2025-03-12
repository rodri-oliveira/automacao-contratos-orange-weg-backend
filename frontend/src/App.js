import React, { useState, useCallback, useEffect } from 'react';
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
  
  // Estado para controlar quais abas estão habilitadas
  const [enabledTabs, setEnabledTabs] = useState({
    R189: true,
    QPE: false,
    SPB: false,
    NFSERV: false,
    MUN_CODE: false
  });
  
  // Estado para controlar se os botões de validação estão habilitados
  const [validationEnabled, setValidationEnabled] = useState(false);
  
  // Estado para forçar a recriação do componente FileList
  const [fileListKey, setFileListKey] = useState(0);

  // Efeito para limpar os arquivos quando a aba mudar
  useEffect(() => {
    setFiles([]);
    setSelectedFiles([]);
    setError(null);
    console.log('Aba alterada para:', activeTab, 'Arquivos limpos');
  }, [activeTab]);

  const handleTabChange = (tab) => {
    if (enabledTabs[tab]) {
      // Limpar arquivos
      setFiles([]);
      setSelectedFiles([]);
      setError(null);
      
      // Mudar de aba
      setActiveTab(tab);
      
      // Forçar a recriação do componente FileList
      setFileListKey(prevKey => prevKey + 1);
      
      console.log('Aba alterada manualmente para:', tab);
    }
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
            if (data.arquivos) {
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
        let endpoint;
        let nextTab;
        
        switch(activeTab) {
            case 'QPE':
                endpoint = 'http://localhost:8000/qpe/process';
                nextTab = 'SPB';
                break;
            case 'SPB':
                endpoint = 'http://localhost:8000/spb/process';
                nextTab = 'NFSERV';
                break;
            case 'NFSERV':
                endpoint = 'http://localhost:8000/nfserv/process';
                nextTab = 'MUN_CODE';
                break;
            case 'MUN_CODE':
                endpoint = 'http://localhost:8000/mun_code/process';
                nextTab = 'R189'; // Volta para R189 após completar o ciclo
                break;
            default:
                endpoint = 'http://localhost:8000/api/processar/r189';
                nextTab = 'QPE';
        }
        
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
            
            // Limpar completamente os arquivos
            setFiles([]);
            setSelectedFiles([]);
            
            // Forçar a recriação do componente FileList
            setFileListKey(prevKey => prevKey + 1);
            
            // Atualizar as abas habilitadas e mudar para a próxima aba
            if (activeTab === 'MUN_CODE') {
                // Se completou o processamento da última aba, habilita os botões de validação
                setValidationEnabled(true);
                setActiveTab('R189'); // Volta para a aba R189
                console.log('Habilitando botões de validação e voltando para R189');
            } else {
                // Caso contrário, habilita a próxima aba
                setEnabledTabs(prevState => ({
                    ...prevState,
                    [nextTab]: true
                }));
                setActiveTab(nextTab);
                console.log('Habilitando próxima aba:', nextTab);
            }
            
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
    setSelectedFiles([]);
    setError(null);
    setStatus({
      R189: 'Aguardando processamento',
      QPE: 'Aguardando processamento',
      SPB: 'Aguardando processamento',
      NFSERV: 'Aguardando processamento',
      MUN_CODE: 'Aguardando processamento'
    });
    // Resetar as abas habilitadas para apenas R189
    setEnabledTabs({
      R189: true,
      QPE: false,
      SPB: false,
      NFSERV: false,
      MUN_CODE: false
    });
    // Desabilitar os botões de validação
    setValidationEnabled(false);
    // Voltar para a aba R189
    setActiveTab('R189');
    // Forçar a recriação do componente FileList
    setFileListKey(prevKey => prevKey + 1);
    
    console.log('Processo resetado');
  };

  const handleFileSelection = (fileName) => {
    if (selectedFiles.includes(fileName)) {
      setSelectedFiles(selectedFiles.filter((file) => file !== fileName));
    } else {
      setSelectedFiles([...selectedFiles, fileName]);
    }
  };

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

  // Funções de validação
  const handleValidationMunCodeR189 = async () => {
    try {
      console.log("Iniciando validação MUN_CODE vs R189");
      setLoading(true);
      setError(null);
      
      // Atualizar o status para indicar que está em processamento
      setStatus(prevStatus => ({
        ...prevStatus,
        MUN_CODE: 'Validando MUN_CODE vs R189...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/mun_code_r189', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na validação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        // Atualizar o status para indicar sucesso
        setStatus(prevStatus => ({
          ...prevStatus,
          MUN_CODE: 'Validação concluída com sucesso'
        }));
        
        // Exibir mensagem de sucesso
        alert(data.message || 'Validação concluída com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na validação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      // Atualizar o status para indicar erro
      setStatus(prevStatus => ({
        ...prevStatus,
        MUN_CODE: 'Erro na validação'
      }));
      
      setError(`Erro na validação MUN_CODE vs R189: ${error.message}`);
      alert(`Erro na validação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleValidationR189 = async () => {
    try {
      console.log("Iniciando validação R189");
      setLoading(true);
      setError(null);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        R189: 'Validando R189...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/r189', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na validação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        setStatus(prevStatus => ({
          ...prevStatus,
          R189: 'Validação concluída com sucesso'
        }));
        
        alert(data.message || 'Validação concluída com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na validação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        R189: 'Erro na validação'
      }));
      
      setError(`Erro na validação R189: ${error.message}`);
      alert(`Erro na validação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleValidationQpeR189 = async () => {
    try {
      console.log("Iniciando validação QPE vs R189");
      setLoading(true);
      setError(null);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        QPE: 'Validando QPE vs R189...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/qpe_r189', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na validação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        setStatus(prevStatus => ({
          ...prevStatus,
          QPE: 'Validação concluída com sucesso'
        }));
        
        alert(data.message || 'Validação concluída com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na validação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        QPE: 'Erro na validação'
      }));
      
      setError(`Erro na validação QPE vs R189: ${error.message}`);
      alert(`Erro na validação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleValidationSpbR189 = async () => {
    try {
      console.log("Iniciando validação SPB vs R189");
      setLoading(true);
      setError(null);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        SPB: 'Validando SPB vs R189...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/spb_r189', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na validação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        setStatus(prevStatus => ({
          ...prevStatus,
          SPB: 'Validação concluída com sucesso'
        }));
        
        alert(data.message || 'Validação concluída com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na validação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        SPB: 'Erro na validação'
      }));
      
      setError(`Erro na validação SPB vs R189: ${error.message}`);
      alert(`Erro na validação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleValidationNfservR189 = async () => {
    try {
      console.log("Iniciando validação NFSERV vs R189");
      setLoading(true);
      setError(null);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        NFSERV: 'Validando NFSERV vs R189...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/nfserv_r189', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na validação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        setStatus(prevStatus => ({
          ...prevStatus,
          NFSERV: 'Validação concluída com sucesso'
        }));
        
        alert(data.message || 'Validação concluída com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na validação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      setStatus(prevStatus => ({
        ...prevStatus,
        NFSERV: 'Erro na validação'
      }));
      
      setError(`Erro na validação NFSERV vs R189: ${error.message}`);
      alert(`Erro na validação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Adicione esta nova função de manipulação para consolidar relatórios
  const handleConsolidateReports = async () => {
    try {
      console.log("Iniciando consolidação de relatórios");
      setLoading(true);
      setError(null);
      
      // Atualizar o status para indicar que está em processamento
      setStatus(prevStatus => ({
        ...prevStatus,
        R189: 'Consolidando relatórios...'
      }));
      
      const response = await fetch('http://localhost:8000/api/validations/consolidate_reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      console.log('Status da resposta:', response.status);
      
      if (!response.ok) {
        throw new Error(`Erro na consolidação, ${response.status} (${response.statusText})`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta:', data);
      
      if (data.success) {
        // Atualizar o status para indicar sucesso
        setStatus(prevStatus => ({
          ...prevStatus,
          R189: 'Consolidação concluída com sucesso'
        }));
        
        // Exibir mensagem de sucesso
        alert(data.message || 'Relatórios consolidados com sucesso!');
      } else {
        throw new Error(data.error || 'Erro na consolidação');
      }
    } catch (error) {
      console.error('Erro completo:', error);
      
      // Atualizar o status para indicar erro
      setStatus(prevStatus => ({
        ...prevStatus,
        R189: 'Erro na consolidação'
      }));
      
      setError(`Erro na consolidação de relatórios: ${error.message}`);
      alert(`Erro na consolidação: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const FileList = () => {
    if (error) return <div style={{color: 'red'}}>{error}</div>;
    if (files.length === 0 && !error && !loading) {
      return (
        <div className="empty-files-message">
          <p>Nenhum arquivo carregado. Clique em "Buscar Arquivos" para listar os arquivos disponíveis para esta etapa.</p>
          <p>Aba atual: <strong>{activeTab}</strong></p>
        </div>
      );
    }
    if (files.length === 0) return <div>Nenhum arquivo encontrado</div>;

    return (
        <div className="file-list">
            <div className="selection-header">
                <label className="select-all-label">
                    <input
                        type="checkbox"
                        className="select-all-checkbox"
                        checked={selectedFiles.length === files.length && files.length > 0}
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
                            <td>{(file.tamanho / 1024).toFixed(2)} KB}</td>
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
              className={`tab-button ${activeTab === tab ? 'active' : ''} ${!enabledTabs[tab] ? 'disabled' : ''}`}
              onClick={() => handleTabChange(tab)}
              disabled={!enabledTabs[tab]}
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
                <button className="action-button" onClick={handleSearchFiles} disabled={loading}>
                  Buscar Arquivos
                </button>
                <button 
                  className="action-button" 
                  onClick={handleProcessFiles} 
                  disabled={loading || selectedFiles.length === 0}
                >
                  Processar Arquivos
                </button>
              </div>
              
              {loading && <p>Carregando...</p>}
              
              <div className="files-section">
                {!loading && <FileList key={fileListKey} />}
              </div>
            </div>
          </div>

          <div className="section-container">
            <div className="section-header">Validações</div>
            <div className="section-content">
              {validationEnabled ? (
                <>
                  <button className="validation-button" onClick={handleValidationMunCodeR189}>
                    1. Verificar Divergências MUN_CODE vs R189
                  </button>
                  <button className="validation-button" onClick={handleValidationR189}>
                    2. Verificar Divergências R189
                  </button>
                  <button className="validation-button" onClick={handleValidationQpeR189}>
                    3. Verificar Divergências QPE vs R189
                  </button>
                  <button className="validation-button" onClick={handleValidationSpbR189}>
                    4. Verificar Divergências SPB vs R189
                  </button>
                  <button className="validation-button" onClick={handleValidationNfservR189}>
                    5. Verificar Divergências NFSERV vs R189
                  </button>
                  
                  {/* Adicione uma divisão visual antes do botão de consolidação */}
                  <div className="validation-divider">
                    <span>Relatórios</span>
                  </div>
                  
                  {/* Novo botão de consolidação de relatórios */}
                  <button 
                    className="consolidate-button" 
                    onClick={handleConsolidateReports}
                    disabled={loading}
                  >
                    Consolidar Todos os Relatórios em um Único Arquivo
                  </button>
                </>
              ) : (
                <p>Complete o processamento de todos os arquivos para habilitar as validações.</p>
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
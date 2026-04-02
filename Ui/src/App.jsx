import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import './objects.css'; // 새로 만든 오브젝트 CSS

import AgentImg from './assets/human.png'; 
import MyDeskImg from './assets/desk.png';   
import MonitorImg from './assets/monitor.png';
import MonitorBackImg from './assets/monitor_back.png';
import KeyboardImg from './assets/keyboard.png';
import MouseImg from './assets/mouse.png'; 
import MouseBackImg from './assets/mouse_back.png'; 



function App() {
  const [currentAI, setCurrentAI] = useState(null); 
  const [input, setInput] = useState('');
  const [logs, setLogs] = useState({}); 
  const [progresses, setProgresses] = useState({});
  const [statuses, setStatuses] = useState({});
  const [models, setModels] = useState({});
  const [editingAI, setEditingAI] = useState(null);
  const [showNameModal, setShowNameModal] = useState(false);
  const [tempName, setTempName] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const ws = useRef(null);

  // 4대 배치 주소록 (1층 3명, 2층 중앙 1명)
  // 💡 [고급 주소록] 자리마다 책상, 모니터, 요원의 좌표를 개별적으로 통제합니다!
  const gridConfig = [
  { desk: "2 / 5 / 4 / 7", agent: "2 / 5 / 4 / 7" },  // 2행짜리로 통일
  { desk: "5 / 3 / 7 / 5", agent: "5 / 3 / 7 / 5" },
  { desk: "5 / 5 / 7 / 7", agent: "5 / 5 / 7 / 7" },
  { desk: "5 / 7 / 7 / 9", agent: "5 / 7 / 7 / 9" },
];

  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws');
    ws.current.onopen = () => console.log('서버와 연결되었습니다.');
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const aiName = data.aiName;
      if (!aiName) return;
      if (data.type === 'progress') setProgresses(prev => ({ ...prev, [aiName]: data.percent }));
      else if (data.type === 'log') setLogs(prev => ({ ...prev, [aiName]: [...(prev[aiName] || []), data.message] }));
      else if (data.type === 'status') setStatuses(prev => ({ ...prev, [aiName]: data.status }));
    };
    ws.current.onerror = (error) => console.error('웹소켓 에러 발생:', error);
    return () => { if (ws.current) ws.current.close(); };
  }, []);

  const handleAddAI = () => {
    if (Object.keys(logs).length >= 4) {
      alert('더 이상 자리가 없습니다! 관제 센터 인원이 꽉 찼습니다.');
      return; 
    }
    setTempName(`Agent_${Object.keys(logs).length + 1}`);
    setShowNameModal(true);
  };

  const confirmAddAI = () => {
    const newAIName = tempName.trim();
    if (!newAIName) { alert('이름을 입력해주세요!'); return; }
    if (logs[newAIName]) { alert('이미 존재하는 이름입니다.'); return; }

    setLogs({ ...logs, [newAIName]: [`[${newAIName}] 관제 센터 배치 완료.`] });
    setCurrentAI(newAIName);
    setProgresses(prev => ({ ...prev, [newAIName]: 0 }));
    setStatuses(prev => ({ ...prev, [newAIName]: 'READY' }));
    setModels(prev => ({ ...prev, [newAIName]: '미선택' })); 
    
    if (!isSidebarOpen) setIsSidebarOpen(true);
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'spawn', aiName: newAIName }));
    }
    setShowNameModal(false);
  };

  const handleRemoveAI = (aiNameToRemove, e) => {
    e.stopPropagation(); 
    if (window.confirm(`${aiNameToRemove} 요원을 해고하시겠습니까?`)) {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'kill', aiName: aiNameToRemove }));
      }
      const newLogs = { ...logs }; delete newLogs[aiNameToRemove]; setLogs(newLogs);
      setProgresses(prev => { const newP = { ...prev }; delete newP[aiNameToRemove]; return newP; });
      setStatuses(prev => { const newS = { ...prev }; delete newS[aiNameToRemove]; return newS; });
      setModels(prev => { const newM = { ...prev }; delete newM[aiNameToRemove]; return newM; });
      if (currentAI === aiNameToRemove) {
        const remainingAIs = Object.keys(newLogs);
        setCurrentAI(remainingAIs.length > 0 ? remainingAIs[0] : null);
      }
    }
  };

  const startTask = (aiName) => {
    if (models[aiName] === '미선택') { alert("맵에서 요원을 클릭해 모델을 할당하세요!"); return; }
    if (!aiName || statuses[aiName] === 'RUNNING' || progresses[aiName] >= 100) return;
    if (ws.current?.readyState === WebSocket.OPEN) {
      setStatuses(prev => ({ ...prev, [aiName]: 'RUNNING' }));
      setLogs(prev => ({ ...prev, [aiName]: [...prev[aiName], `> [시스템] ${models[aiName]} 모델 작업을 재개합니다.`] }));
      ws.current.send(JSON.stringify({ action: 'resume', aiName }));
    }
  };

  const stopTask = (aiName) => {
    if (!aiName || statuses[aiName] !== 'RUNNING') return;
    if (ws.current?.readyState === WebSocket.OPEN) {
      setStatuses(prev => ({ ...prev, [aiName]: 'STOPPED' }));
      setLogs(prev => ({ ...prev, [aiName]: [...prev[aiName], `> [시스템] 작업을 중지했습니다.`] }));
      ws.current.send(JSON.stringify({ action: 'pause', aiName }));
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && input.trim() !== '') {
      if (!currentAI || models[currentAI] === '미선택') return;
      setLogs(prev => ({ ...prev, [currentAI]: [...prev[currentAI], `> ${input}`] }));
      if (statuses[currentAI] === 'READY' || statuses[currentAI] === 'STOPPED') setStatuses(prev => ({ ...prev, [currentAI]: 'RUNNING' }));
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'prompt', aiName: currentAI, text: input }));
      }
      setInput('');
    }
  };

  const handleModelSelect = (modelName) => {
    setModels(prev => ({ ...prev, [editingAI]: modelName }));
    setLogs(prev => ({ ...prev, [editingAI]: [...prev[editingAI], `> [시스템] AI 모델이 [${modelName}]로 설정되었습니다.`] }));
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'set_model', aiName: editingAI, model: modelName }));
    }
    setEditingAI(null); 
  };

  return (
    <div className="layout">
      {showNameModal && (
        <div className="ai-modal-overlay" onClick={() => setShowNameModal(false)}>
          <div className="ai-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>새 요원 배치 (Enter)</h3>
            <input type="text" className="modal-input" value={tempName} onChange={(e) => setTempName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') confirmAddAI(); }} autoFocus />
            <button className="model-btn" onClick={confirmAddAI}>✔ 배치 승인</button>
            <button className="model-btn" style={{ borderColor: '#ff4444', color: '#ff4444' }} onClick={() => setShowNameModal(false)}>✖ 취소</button>
          </div>
        </div>
      )}
      {editingAI && (
        <div className="ai-modal-overlay" onClick={() => setEditingAI(null)}>
          <div className="ai-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>{editingAI} 모델 설정</h3>
            <button className="model-btn" onClick={() => handleModelSelect('GPT-4o')}>GPT-4o</button>
            <button className="model-btn" onClick={() => handleModelSelect('Claude 3.5')}>Claude 3.5</button>
            <button className="model-btn" onClick={() => handleModelSelect('Gemini Pro')}>Gemini Pro</button>
          </div>
        </div>
      )}

      <button className={`toggle-btn ${isSidebarOpen ? 'open' : 'closed'}`} onClick={() => setIsSidebarOpen(!isSidebarOpen)}>{isSidebarOpen ? '◀' : '▶'}</button>
      <div className={`sidebar-backdrop ${isSidebarOpen ? 'visible' : ''}`} onClick={() => setIsSidebarOpen(false)}></div>
      
      <div className={`sidebar ${isSidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-content">
          <div className="ai-tabs">
            {Object.keys(logs).map((aiName, index) => (
              <div key={aiName} className={`ai-tab ${currentAI === aiName ? 'active' : ''}`} onClick={() => setCurrentAI(aiName)}>
                <span className="tab-name">{index === 0 ? `👨‍💼 ${aiName}` : `🧑‍💻 ${aiName}`}</span>
                <span className="delete-btn" onClick={(e) => handleRemoveAI(aiName, e)}>X</span>
              </div>
            ))}
            <button className="ai-tab add-btn" onClick={handleAddAI}>+</button>
          </div>
          <div className="terminal">
            {currentAI ? (
              <>
                <div className="terminal-header">
                  <span className={`status-badge ${statuses[currentAI]}`}>[{statuses[currentAI]}]</span>
                  {statuses[currentAI] !== 'READY' && (
                    <div className="control-buttons">
                      <button className="control-btn start" onClick={() => startTask(currentAI)} disabled={statuses[currentAI] === 'RUNNING' || statuses[currentAI] === 'COMPLETED'}>▶ 재개</button>
                      <button className="control-btn stop" onClick={() => stopTask(currentAI)} disabled={statuses[currentAI] !== 'RUNNING'}>⏸ 중지</button>
                    </div>
                  )}
                </div>
                <div className="terminal-log">
                  {logs[currentAI] && logs[currentAI].map((log, index) => (
                    <div key={index} className="log-line">{log}</div>
                  ))}
                </div>
                <div className="terminal-input-line">
                  <span>{'>'}</span>
                  <input type="text" className="terminal-input" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} autoFocus />
                </div>
              </>
            ) : (
              <div className="terminal-log"><div className="log-line" style={{ color: '#555' }}>[시스템] 가동 중인 AI가 없습니다.</div></div>
            )}
          </div>
        </div>
      </div>

      <div className="pixel-floor"> 
        
        {/* 💡 1. 책상과 모니터 렌더링 (고급 주소록 적용) */}
        {gridConfig.map((config, index) => (
        <div key={index}
          className="desk-wrapper"
          style={{ gridArea: config.desk }}  // gridArea만 동적이라 인라인 유지
        >

          <div className="map-item desk-item"
            style={{ backgroundImage: `url(${MyDeskImg})` }} />
          <div className={`map-item ${index === 0 ? 'monitor-item-flipped' : 'monitor-item'}`}
            style={{ backgroundImage: `url(${index === 0 ? MonitorBackImg : MonitorImg})` }} />
          {index !== 0 && (
          <div className="map-item keyboard-item"
            style={{ backgroundImage: `url(${KeyboardImg})` }} />
          )}
          <div className={`map-item ${index === 0 ? 'mouse-item-flipped' : 'mouse-item'}`}
            style={{ backgroundImage: `url(${index === 0 ? MouseBackImg : MouseImg})` }} />
          </div>
          
))}
        
        {/* 💡 2. 요원(Agent) 렌더링 (고급 주소록 적용) */}
        {Object.keys(logs).map((aiName, index) => {
          const currentProg = progresses[aiName] || 0; 
          const isManager = index === 0;
          
          // 🎯 요원은 config.agent 주소를 봅니다 (만약 자리가 없으면 기본값 부여)
          const agentPos = gridConfig[index] ? gridConfig[index].agent : "1 / 1 / 2 / 2"; 

          return (
            <div 
              key={aiName}
              className="agent-container" 
              style={{ gridArea: agentPos }} /* 👈 여기가 변경되었습니다! */
            >
              <div className="agent-status-floating">
                <span className="progress-text" style={{ 
                    fontSize: '9px', fontWeight: isManager ? 'bold' : 'normal',
                    color: isManager ? '#00ffff' : '#aaa', marginBottom: '5px' 
                }}>
                  [{isManager ? '중간관리자👨‍💼' : '일반요원🧑‍💻'}]
                </span>

                <span className="progress-text" style={{ color: models[aiName] === '미선택' ? '#ffaa00' : '#00ffff' }}>
                  {models[aiName]}
                </span>
                <span className="progress-text">{currentProg}%</span>
                <div className="progress-bar-container">
                  <div className="progress-bar-fill" style={{ width: `${currentProg}%`, backgroundColor: statuses[aiName] === 'STOPPED' ? '#ff4444' : '#0f0' }}></div>
                </div>
              </div>
              
              <div 
                className="map-item agent-icon"
                style={{ backgroundImage: `url(${AgentImg})` }}
                onClick={() => { if (models[aiName] === '미선택') setEditingAI(aiName); }} 
              ></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default App;
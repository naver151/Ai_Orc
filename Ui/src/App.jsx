import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import './objects.css';

import AgentImg      from './assets/human.png';
import MyDeskImg     from './assets/desk.png';
import MonitorImg    from './assets/monitor.png';
import MonitorBackImg from './assets/monitor_back.png';
import KeyboardImg   from './assets/keyboard.png';
import MouseImg      from './assets/mouse.png';
import MouseBackImg  from './assets/mouse_back.png';

// 모델 표시명 → 백엔드 provider 키 매핑
const MODEL_TO_PROVIDER = {
  // GitHub Models (무료)
  'GitHub GPT-4o':       'github-gpt4o',
  'GitHub GPT-4o mini':  'github-gpt4o-mini',
  'GitHub Llama 70B':    'github-llama',
  'GitHub Llama 8B':     'github-llama-8b',
  'GitHub Mistral':      'github-mistral',
  'GitHub Phi':          'github-phi',
  // 유료 API
  'GPT-4o':              'gpt',
  'Claude 3.5':          'claude',
  'Gemini Pro':          'gemini',
  // 비전 AI
  'YOLO (객체탐지)':     'yolo',
};

// 요원 4자리 그리드 배치
const gridConfig = [
  { desk: "2 / 5 / 4 / 7", agent: "2 / 5 / 4 / 7" },  // 관리자 (중앙 상단)
  { desk: "5 / 3 / 7 / 5", agent: "5 / 3 / 7 / 5" },  // 요원 1 (좌측 하단)
  { desk: "5 / 5 / 7 / 7", agent: "5 / 5 / 7 / 7" },  // 요원 2 (중앙 하단)
  { desk: "5 / 7 / 7 / 9", agent: "5 / 7 / 7 / 9" },  // 요원 3 (우측 하단)
];

function App() {
  // ── 상태 관리 ──────────────────────────────────────────────
  const [currentAI, setCurrentAI] = useState(null);
  const [input, setInput] = useState('');
  const [logs, setLogs] = useState({});           // { aiName: [ string | {streaming, text} ] }
  const [progresses, setProgresses] = useState({});
  const [statuses, setStatuses] = useState({});
  const [models, setModels] = useState({});        // 표시용 모델명
  const [providers, setProviders] = useState({});  // 백엔드 provider 키
  const [currentTasks, setCurrentTasks] = useState({}); // 마우스오버 툴팁용

  // UI 상태
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [showNameModal, setShowNameModal] = useState(false);
  const [tempName, setTempName] = useState('');
  const [editingAI, setEditingAI] = useState(null); // 모델 선택 모달

  const ws = useRef(null);
  const fileInputRef = useRef(null);

  // ── 1. WebSocket 연결 및 실시간 메시지 처리 ───────────────
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws');

    ws.current.onopen = () => console.log('서버와 연결되었습니다.');

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const aiName = data.aiName;
      if (!aiName) return;

      if (data.type === 'progress') {
        setProgresses(prev => ({ ...prev, [aiName]: data.percent }));

      } else if (data.type === 'log') {
        // 스트리밍 텍스트: 마지막 항목에 이어붙이기
        setLogs(prev => {
          const prevLogs = prev[aiName] || [];
          const lastIdx = prevLogs.length - 1;
          if (lastIdx >= 0 && typeof prevLogs[lastIdx] === 'object' && prevLogs[lastIdx].streaming) {
            const updated = [...prevLogs];
            updated[lastIdx] = { streaming: true, text: updated[lastIdx].text + data.message };
            return { ...prev, [aiName]: updated };
          }
          return { ...prev, [aiName]: [...prevLogs, { streaming: true, text: data.message }] };
        });

      } else if (data.type === 'status') {
        if (data.status === 'RUNNING') {
          // 새 응답 슬롯 생성
          setLogs(prev => {
            const prevLogs = prev[aiName] || [];
            const last = prevLogs[prevLogs.length - 1];
            if (last && typeof last === 'object' && last.streaming) return prev;
            return { ...prev, [aiName]: [...prevLogs, { streaming: true, text: '' }] };
          });
        } else {
          // 스트리밍 종료 → 일반 문자열로 확정
          setLogs(prev => {
            const prevLogs = prev[aiName] || [];
            const updated = prevLogs.map(item =>
              typeof item === 'object' && item.streaming ? item.text : item
            );
            return { ...prev, [aiName]: updated };
          });
        }
        setStatuses(prev => ({ ...prev, [aiName]: data.status }));

      } else if (data.type === 'current_task') {
        setCurrentTasks(prev => ({ ...prev, [aiName]: data.task }));
      }
    };

    ws.current.onerror = (error) => console.error('웹소켓 에러 발생:', error);
    return () => { if (ws.current) ws.current.close(); };
  }, []);

  // ── 2. 요원 추가 (이름 입력 모달) ────────────────────────
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

    setLogs(prev => ({ ...prev, [newAIName]: [`[${newAIName}] 관제 센터 배치 완료. 요원을 클릭해 모델을 선택하세요.`] }));
    setCurrentAI(newAIName);
    setProgresses(prev => ({ ...prev, [newAIName]: 0 }));
    setStatuses(prev => ({ ...prev, [newAIName]: 'READY' }));
    setModels(prev => ({ ...prev, [newAIName]: '미선택' }));
    setProviders(prev => ({ ...prev, [newAIName]: '' }));

    if (!isSidebarOpen) setIsSidebarOpen(true);
    // 일단 spawn만 (provider는 모델 선택 시 재전송)
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'spawn', aiName: newAIName, provider: 'github' }));
    }
    setShowNameModal(false);
  };

  // ── 3. 요원 해고 ──────────────────────────────────────────
  const handleRemoveAI = (aiNameToRemove, e) => {
    e.stopPropagation();
    if (window.confirm(`${aiNameToRemove} 요원을 해고하시겠습니까?`)) {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'kill', aiName: aiNameToRemove }));
      }
      const cleanup = (obj) => { const n = { ...obj }; delete n[aiNameToRemove]; return n; };
      setLogs(cleanup);
      setProgresses(cleanup);
      setStatuses(cleanup);
      setModels(cleanup);
      setProviders(cleanup);
      setCurrentTasks(cleanup);
      if (currentAI === aiNameToRemove) {
        setCurrentAI(prev => {
          const remaining = Object.keys(logs).filter(k => k !== aiNameToRemove);
          return remaining.length > 0 ? remaining[0] : null;
        });
      }
    }
  };

  // ── 4. 모델 선택 (맵에서 요원 클릭 → 모달) ───────────────
  const handleModelSelect = (modelDisplayName) => {
    const providerKey = MODEL_TO_PROVIDER[modelDisplayName] || 'github';
    setModels(prev => ({ ...prev, [editingAI]: modelDisplayName }));
    setProviders(prev => ({ ...prev, [editingAI]: providerKey }));
    setLogs(prev => ({
      ...prev,
      [editingAI]: [...(prev[editingAI] || []), `> [시스템] 모델 [${modelDisplayName}] 설정 완료.`]
    }));
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'spawn', aiName: editingAI, provider: providerKey }));
    }
    setEditingAI(null);
  };

  // ── 5. YOLO 이미지 업로드 ─────────────────────────────────
  const handleImageUpload = async (e) => {
    const file = e.target.files[0];
    if (!file || !currentAI) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      setLogs(prev => ({ ...prev, [currentAI]: [...(prev[currentAI] || []), `> [이미지 업로드 중] ${file.name}`] }));
      const res = await fetch('http://localhost:8000/upload', { method: 'POST', body: formData });
      const data = await res.json();
      setLogs(prev => ({ ...prev, [currentAI]: [...(prev[currentAI] || []), `> [업로드 완료] ${data.original_name}`] }));
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'prompt', aiName: currentAI, text: data.path }));
      }
    } catch (err) {
      setLogs(prev => ({ ...prev, [currentAI]: [...(prev[currentAI] || []), `> [오류] 업로드 실패: ${err.message}`] }));
    }
    e.target.value = '';
  };

  // ── 6. 작업 재개 / 중지 ───────────────────────────────────
  const startTask = (aiName) => {
    if (models[aiName] === '미선택') { alert('요원을 클릭해 모델을 먼저 선택하세요!'); return; }
    if (!aiName || statuses[aiName] === 'RUNNING' || progresses[aiName] >= 100) return;
    if (ws.current?.readyState === WebSocket.OPEN) {
      setStatuses(prev => ({ ...prev, [aiName]: 'RUNNING' }));
      setLogs(prev => ({ ...prev, [aiName]: [...prev[aiName], `> [시스템] 작업을 재개합니다.`] }));
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

  // ── 7. 프롬프트 전송 (Enter) ──────────────────────────────
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && input.trim() !== '') {
      if (!currentAI || models[currentAI] === '미선택') return;
      setLogs(prev => ({ ...prev, [currentAI]: [...prev[currentAI], `> ${input}`] }));
      if (statuses[currentAI] === 'READY' || statuses[currentAI] === 'STOPPED') {
        setStatuses(prev => ({ ...prev, [currentAI]: 'RUNNING' }));
      }
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'prompt', aiName: currentAI, text: input }));
      } else {
        setLogs(prev => ({ ...prev, [currentAI]: [...prev[currentAI], `[오류] 서버와 연결되어 있지 않습니다!`] }));
      }
      setInput('');
    }
  };

  // ── 렌더링 ────────────────────────────────────────────────
  return (
    <div className="layout">

      {/* ── 이름 입력 모달 ── */}
      {showNameModal && (
        <div className="ai-modal-overlay" onClick={() => setShowNameModal(false)}>
          <div className="ai-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>새 요원 배치</h3>
            <input
              type="text"
              className="modal-input"
              value={tempName}
              onChange={(e) => setTempName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') confirmAddAI(); }}
              autoFocus
            />
            <button className="model-btn" onClick={confirmAddAI}>✔ 배치 승인</button>
            <button className="model-btn" style={{ borderColor: '#bc4749', color: '#bc4749' }} onClick={() => setShowNameModal(false)}>✖ 취소</button>
          </div>
        </div>
      )}

      {/* ── 모델 선택 모달 ── */}
      {editingAI && (
        <div className="ai-modal-overlay" onClick={() => setEditingAI(null)}>
          <div className="ai-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>{editingAI} — 모델 선택</h3>

            <p className="modal-section-label">── GitHub Models (무료, PAT 필요) ──</p>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub GPT-4o')}>⭐ GitHub GPT-4o</button>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub GPT-4o mini')}>GitHub GPT-4o mini</button>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub Llama 70B')}>GitHub Llama 3.1 70B</button>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub Llama 8B')}>GitHub Llama 3.1 8B</button>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub Mistral')}>GitHub Mistral Large</button>
            <button className="model-btn" onClick={() => handleModelSelect('GitHub Phi')}>GitHub Phi-3.5 Mini</button>

            <p className="modal-section-label">── 유료 API ──</p>
            <button className="model-btn" onClick={() => handleModelSelect('GPT-4o')}>GPT-4o (OpenAI)</button>
            <button className="model-btn" onClick={() => handleModelSelect('Claude 3.5')}>Claude 3.5 (Anthropic)</button>
            <button className="model-btn" onClick={() => handleModelSelect('Gemini Pro')}>Gemini Pro (Google)</button>

            <p className="modal-section-label">── 비전 AI ──</p>
            <button className="model-btn" onClick={() => handleModelSelect('YOLO (객체탐지)')}>📷 YOLO 객체탐지</button>
          </div>
        </div>
      )}

      {/* ── 사이드바 토글 버튼 ── */}
      <button
        className={`toggle-btn ${isSidebarOpen ? 'open' : 'closed'}`}
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
      >
        {isSidebarOpen ? '◀' : '▶'}
      </button>

      {/* ── 사이드바 백드롭 ── */}
      <div
        className={`sidebar-backdrop ${isSidebarOpen ? 'visible' : ''}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      {/* ── 사이드바 ── */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-content">

          {/* 요원 탭 목록 */}
          <div className="ai-tabs">
            {Object.keys(logs).map((aiName, index) => (
              <div
                key={aiName}
                className={`ai-tab ${currentAI === aiName ? 'active' : ''}`}
                onClick={() => setCurrentAI(aiName)}
              >
                <span className="tab-name">{index === 0 ? `👨‍💼 ${aiName}` : `🧑‍💻 ${aiName}`}</span>
                <span className="delete-btn" onClick={(e) => handleRemoveAI(aiName, e)}>X</span>
              </div>
            ))}
            <button className="ai-tab add-btn" onClick={handleAddAI}>+</button>
          </div>

          {/* 터미널 */}
          <div className="terminal">
            {currentAI ? (
              <>
                <div className="terminal-header">
                  {/* 모델 선택 행 */}
                  <div className="terminal-header-model">
                    <span className="model-label">AI 모델</span>
                    <button
                      className={`model-selector-btn ${models[currentAI] === '미선택' ? 'unselected' : ''}`}
                      onClick={() => setEditingAI(currentAI)}
                    >
                      {models[currentAI] === '미선택' ? '⚠ 모델 선택하기' : `◈ ${models[currentAI]}`}
                      <span className="model-selector-arrow">▼</span>
                    </button>
                  </div>

                  {/* 상태 뱃지 + 제어 버튼 행 */}
                  <div className="terminal-header-controls">
                    <span className={`status-badge ${statuses[currentAI]}`}>
                      [{statuses[currentAI]}]
                    </span>
                    {statuses[currentAI] !== 'READY' && (
                      <div className="control-buttons">
                        <button
                          className="control-btn start"
                          onClick={() => startTask(currentAI)}
                          disabled={statuses[currentAI] === 'RUNNING' || statuses[currentAI] === 'COMPLETED'}
                        >▶ 재개</button>
                        <button
                          className="control-btn stop"
                          onClick={() => stopTask(currentAI)}
                          disabled={statuses[currentAI] !== 'RUNNING'}
                        >⏸ 중지</button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="terminal-log">
                  {logs[currentAI] && logs[currentAI].map((log, index) => (
                    <div key={index} className="log-line">
                      {typeof log === 'object' ? log.text : log}
                    </div>
                  ))}
                </div>

                {/* YOLO면 이미지 업로드, 아니면 텍스트 입력 */}
                {providers[currentAI] === 'yolo' ? (
                  <div className="terminal-input-line">
                    <span>{'>'}</span>
                    <label className="yolo-upload-btn">
                      📷 이미지 선택
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        style={{ display: 'none' }}
                        onChange={handleImageUpload}
                      />
                    </label>
                  </div>
                ) : (
                  <div className="terminal-input-line">
                    <span>{'>'}</span>
                    <input
                      type="text"
                      className="terminal-input"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      autoFocus
                    />
                  </div>
                )}
              </>
            ) : (
              <div className="terminal-log">
                <div className="log-line" style={{ color: '#a67b5b' }}>
                  [시스템] 가동 중인 AI가 없습니다. '+' 버튼으로 요원을 배치하세요.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 우측 픽셀 맵 ── */}
      <div className="pixel-floor">

        {/* 책상 + 모니터 + 키보드 + 마우스 */}
        {gridConfig.map((config, index) => (
          <div key={index} className="desk-wrapper" style={{ gridArea: config.desk }}>
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

        {/* 요원 캐릭터 + 상태창 + 툴팁 */}
        {Object.keys(logs).map((aiName, index) => {
          const currentProg = progresses[aiName] || 0;
          const isManager = index === 0;
          const agentPos = gridConfig[index] ? gridConfig[index].agent : "1 / 1 / 2 / 2";
          const taskText = currentTasks[aiName] || '';

          return (
            <div key={aiName} className="agent-container" style={{ gridArea: agentPos }}>

              {/* 현재 작업 툴팁 (마우스오버) */}
              {taskText && (
                <div className="agent-task-tooltip">
                  <span className="tooltip-name">{aiName}</span>
                  <span className="tooltip-task">{taskText}</span>
                </div>
              )}

              {/* 상태창 */}
              <div className="agent-status-floating">
                <span className="progress-text" style={{
                  fontWeight: isManager ? 'bold' : 'normal',
                  color: isManager ? '#d4a373' : '#f4ebd0',
                  marginBottom: '3px'
                }}>
                  [{isManager ? '관리자' : '요원'}]
                </span>
                <span className="progress-text" style={{
                  color: models[aiName] === '미선택' ? '#bc4749' : '#d4a373'
                }}>
                  {models[aiName] || '미선택'}
                </span>
                <span className="progress-text">{currentProg}%</span>
                <div className="progress-bar-container">
                  <div className="progress-bar-fill" style={{
                    width: `${currentProg}%`,
                    backgroundColor: statuses[aiName] === 'STOPPED' ? '#bc4749' : '#d4a373'
                  }} />
                </div>
              </div>

              {/* 요원 아이콘 — 클릭하면 모델 선택 모달 */}
              <div
                className="map-item agent-icon"
                style={{ backgroundImage: `url(${AgentImg})` }}
                onClick={() => {
                  setCurrentAI(aiName);
                  setEditingAI(aiName);
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default App;

import React, { useState, useEffect, useRef } from 'react';
import './App.css';

import ComputerImg from './assets/computer.png';
import AgentImg from './assets/human.png'; 

function App() {
  // 상태 관리: 현재 탭, 입력값, 로그 목록, 각 AI의 진행률(%), 현재 상태(READY/RUNNING 등)
  const [currentAI, setCurrentAI] = useState(null); 
  const [input, setInput] = useState('');
  const [logs, setLogs] = useState({}); 
  const [progresses, setProgresses] = useState({});
  const [statuses, setStatuses] = useState({});

  const ws = useRef(null);

  // 요원 고정 좌표: 1번(왼쪽), 2번(가운데), 3번(오른쪽) 컴퓨터 앞자리
  const agentPositions = [
    "4 / 2 / 6 / 4", 
    "8 / 5 / 6 / 7", 
    "4 / 8 / 6 / 10" 
  ];

  // 1. 백엔드 통신: 앱 실행 시 파이썬 서버와 웹소켓을 연결하고, 실시간 데이터를 수신하여 화면에 반영
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws');

    ws.current.onopen = () => {
      console.log('서버와 연결되었습니다.');
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const aiName = data.aiName;

      if (!aiName) return;

      if (data.type === 'progress') {
        setProgresses(prev => ({ ...prev, [aiName]: data.percent }));
      }
      else if (data.type === 'log') {
        setLogs(prev => ({ ...prev, [aiName]: [...(prev[aiName] || []), data.message] }));
      }
      else if (data.type === 'status') {
        setStatuses(prev => ({ ...prev, [aiName]: data.status }));
      }
    };

    ws.current.onerror = (error) => {
      console.error('웹소켓 에러 발생:', error);
    };

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  // 2. 요원 생성 (+ 버튼): 최대 3명까지 요원을 맵에 배치하고 'READY(대기)' 상태로 초기화
  const handleAddAI = () => {
    if (Object.keys(logs).length >= 3) {
      alert('빈 자리가 없습니다! 최대 3대의 컴퓨터만 가동할 수 있습니다.');
      return; 
    }

    const newAIName = prompt('새로운 AI의 이름을 입력하세요:', `AI_${Object.keys(logs).length + 1}`);
    if (!newAIName) return;

    if (logs[newAIName]) {
      alert('이미 존재하는 AI 이름입니다.');
      return;
    }

    const provider = prompt('사용할 AI 모델을 입력하세요:\n- gpt (GPT-4o)\n- claude (Claude 3.5)\n- gemini (Gemini 1.5 Pro)', 'gpt');
    if (!provider) return;

    setLogs({ ...logs, [newAIName]: [`[${newAIName}] 요원 배치 완료. 명령을 대기합니다.`] });
    setCurrentAI(newAIName);
    setProgresses(prev => ({ ...prev, [newAIName]: 0 }));
    setStatuses(prev => ({ ...prev, [newAIName]: 'READY' }));

    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'spawn', aiName: newAIName, provider }));
    }
  };

  // 3. 요원 해고 (X 버튼): 화면에서 요원을 지우고 서버에 작업 강제 종료(kill) 명령 전송
  const handleRemoveAI = (aiNameToRemove, e) => {
    e.stopPropagation(); 
    if (window.confirm(`${aiNameToRemove} 요원을 해고하시겠습니까?`)) {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: 'kill', aiName: aiNameToRemove }));
      }

      const newLogs = { ...logs };
      delete newLogs[aiNameToRemove];
      setLogs(newLogs);

      setProgresses(prev => { const newP = { ...prev }; delete newP[aiNameToRemove]; return newP; });
      setStatuses(prev => { const newS = { ...prev }; delete newS[aiNameToRemove]; return newS; });

      if (currentAI === aiNameToRemove) {
        const remainingAIs = Object.keys(newLogs);
        setCurrentAI(remainingAIs.length > 0 ? remainingAIs[0] : null);
      }
    }
  };

  // 4. 작업 재개 (▶ 버튼): 서버 연결 상태를 확인한 후, 작업을 다시 실행하고 서버에 resume 명령 전송
  const startTask = (aiName) => {
    if (!aiName || statuses[aiName] === 'RUNNING' || progresses[aiName] >= 100) return;

    if (ws.current?.readyState === WebSocket.OPEN) {
      setStatuses(prev => ({ ...prev, [aiName]: 'RUNNING' }));
      setLogs(prev => ({ ...prev, [aiName]: [...prev[aiName], `> [시스템] 작업을 재개합니다.`] }));
      ws.current.send(JSON.stringify({ action: 'resume', aiName }));
    } else {
      setLogs(prev => ({ ...prev, [aiName]: [...(prev[aiName] || []), `> [오류] 서버와 연결되어 있지 않습니다! 재개 실패.`] }));
    }
  };

  // 5. 작업 중지 (⏸ 버튼): 서버 연결 확인 후 작업을 일시 정지시키고 서버에 pause 명령 전송
  const stopTask = (aiName) => {
    if (!aiName || statuses[aiName] !== 'RUNNING') return;
    
    if (ws.current?.readyState === WebSocket.OPEN) {
      setStatuses(prev => ({ ...prev, [aiName]: 'STOPPED' }));
      setLogs(prev => ({ ...prev, [aiName]: [...prev[aiName], `> [시스템] 작업을 일시 중지했습니다.`] }));
      ws.current.send(JSON.stringify({ action: 'pause', aiName }));
    } else {
      setLogs(prev => ({ ...prev, [aiName]: [...(prev[aiName] || []), `> [오류] 서버와 연결되어 있지 않습니다! 중지 실패.`] }));
    }
  };

  // 6. 프롬프트 전송 (Enter 키): 입력한 명령을 화면에 띄우고, 작업을 시작하며 서버로 데이터 전송
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && input.trim() !== '') {
      if (!currentAI) return;
      
      setLogs(prev => ({ ...prev, [currentAI]: [...prev[currentAI], `> ${input}`] }));
      
      if (statuses[currentAI] === 'READY' || statuses[currentAI] === 'STOPPED') {
        setStatuses(prev => ({ ...prev, [currentAI]: 'RUNNING' }));
      }

      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ 
          action: 'prompt', 
          aiName: currentAI, 
          text: input 
        }));
      } else {
        setLogs(prev => ({ ...prev, [currentAI]: [...prev[currentAI], `[오류] 서버와 연결되어 있지 않습니다!`] }));
      }

      setInput('');
    }
  };

  return (
    <div className="layout">
      {/* 7. 좌측 사이드바: AI 탭 목록 및 터미널 (상태 뱃지, 제어 버튼, 로그 출력창, 입력창) */}
      <div className="sidebar">
        <div className="ai-tabs">
          {Object.keys(logs).map((aiName) => (
            <div 
              key={aiName}
              className={`ai-tab ${currentAI === aiName ? 'active' : ''}`}
              onClick={() => setCurrentAI(aiName)}
            >
              <span className="tab-name">{aiName}</span>
              <span className="delete-btn" onClick={(e) => handleRemoveAI(aiName, e)}>X</span>
            </div>
          ))}
          <button className="ai-tab add-btn" onClick={handleAddAI}>+</button>
        </div>

        <div className="terminal">
          {currentAI ? (
            <>
              <div className="terminal-header">
                <span className={`status-badge ${statuses[currentAI]}`}>
                  [{statuses[currentAI]}]
                </span>
                {statuses[currentAI] !== 'READY' && (
                  <div className="control-buttons">
                    <button 
                      className="control-btn start" 
                      onClick={() => startTask(currentAI)}
                      disabled={statuses[currentAI] === 'RUNNING' || statuses[currentAI] === 'COMPLETED'}
                    >
                      ▶ 재개
                    </button>
                    <button 
                      className="control-btn stop" 
                      onClick={() => stopTask(currentAI)}
                      disabled={statuses[currentAI] !== 'RUNNING'}
                    >
                      ⏸ 중지
                    </button>
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
                <input
                  type="text"
                  className="terminal-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                />
              </div>
            </>
          ) : (
            <div className="terminal-log">
              <div className="log-line" style={{ color: '#555' }}>
                [시스템] 가동 중인 AI가 없습니다. '+' 버튼을 눌러 에이전트를 할당하세요.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 8. 우측 맵 영역: 고정된 컴퓨터 3대와 동적으로 생성되는 요원(+상태창) 렌더링 */}
      <div className="pixel-floor"> 
        <div className="map-item pos-comp-1" style={{ backgroundImage: `url(${ComputerImg})` }}></div>
        <div className="map-item pos-comp-2" style={{ backgroundImage: `url(${ComputerImg})` }}></div>
        <div className="map-item pos-comp-3" style={{ backgroundImage: `url(${ComputerImg})` }}></div>
        
        {Object.keys(logs).map((aiName, index) => {
          const currentProg = progresses[aiName] || 0; 
          return (
            <div 
              key={aiName}
              className="agent-container" 
              style={{ gridArea: agentPositions[index % 3] }}
            >
              <div className="agent-status-floating">
                <span className="progress-text">{currentProg}%</span>
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar-fill" 
                    style={{ 
                      width: `${currentProg}%`,
                      backgroundColor: statuses[aiName] === 'STOPPED' ? '#ff4444' : '#0f0'
                    }} 
                  ></div>
                </div>
              </div>
              
              <div 
                className="map-item agent-icon"
                style={{ backgroundImage: `url(${AgentImg})` }}
              ></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default App;
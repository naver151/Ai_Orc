import { useState } from 'react';
import './App.css';

const INITIAL_AGENT = {
  id: 1,
  name: 'UNIT-01',
  model: 'CLAUDE 3.5',
  role: 'ANALYST',
  persona: 'You are a senior AI assistant specialized in analysis and problem solving.',
  status: 'idle',
  progress: 0,
};

const STATUS_LABEL = {
  idle:    '■ STANDBY',
  running: '► EXEC...',
  done:    '✓ DONE',
  error:   '✕ ERROR',
};

export default function App() {
  const [agent, setAgent] = useState(INITIAL_AGENT);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isEditingPersona, setIsEditingPersona] = useState(false);
  const [personaDraft, setPersonaDraft] = useState(INITIAL_AGENT.persona);

  const handleDeploy = () => {
    if (!input.trim() || agent.status === 'running') return;

    const userMsg = {
      role: 'user',
      text: input.trim(),
      ts: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setAgent(prev => ({ ...prev, status: 'running', progress: 0 }));

    const steps = [15, 35, 55, 75, 90, 100];
    steps.forEach((val, i) => {
      setTimeout(() => {
        setAgent(prev => ({ ...prev, progress: val }));
        if (val === 100) {
          setAgent(prev => ({ ...prev, status: 'done' }));
          setMessages(prev => [
            ...prev,
            {
              role: 'agent',
              agentName: 'UNIT-01',
              text: `CMD RECEIVED: "${userMsg.text}"\n> AI API 미연결 상태입니다.\n> 백엔드 연결 후 실제 응답이 출력됩니다.`,
              ts: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            },
          ]);
        }
      }, (i + 1) * 500);
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleDeploy();
    }
  };

  const handleReset = () => setAgent(prev => ({ ...prev, status: 'idle', progress: 0 }));

  const handlePersonaSave = () => {
    setAgent(prev => ({ ...prev, persona: personaDraft }));
    setIsEditingPersona(false);
  };

  return (
    <div className="app">

      {/* ── Header ── */}
      <header className="header">
        <div className="header-left">
          <div className="header-sprite" />
          <span className="header-title">AI CREW COMMANDER</span>
          <span className="header-version">MVP v0</span>
        </div>
        <div className="header-right">
          <span className="header-badge">PROJECT: ALPHA</span>
          <div className={`header-blink ${agent.status === 'running' ? 'active' : ''}`} />
        </div>
      </header>

      {/* ── Main ── */}
      <main className="main">

        {/* Left: Agent Panel */}
        <aside className="agent-panel">
          <div className="panel-label">
            AGENTS <span className="panel-count">1</span>
          </div>

          <div className={`agent-card ${agent.status}`}>
            <div className="agent-card-header">
              <span className="agent-name">{agent.name}</span>
              <span className={`status-badge ${agent.status}`}>
                {STATUS_LABEL[agent.status]}
              </span>
            </div>

            <div className="agent-meta">
              <div className="meta-row">
                <span className="meta-key">MODEL</span>
                <span className="meta-value">{agent.model}</span>
              </div>
              <div className="meta-row">
                <span className="meta-key">ROLE</span>
                <span className="meta-value">{agent.role}</span>
              </div>
            </div>

            <div className="persona-section">
              <div className="persona-header">
                <span className="meta-key">PERSONA</span>
                <button
                  className="persona-edit-btn"
                  onClick={() => {
                    setPersonaDraft(agent.persona);
                    setIsEditingPersona(v => !v);
                  }}
                >
                  {isEditingPersona ? 'CANCEL' : 'EDIT'}
                </button>
              </div>
              {isEditingPersona ? (
                <div className="persona-edit">
                  <textarea
                    className="persona-textarea"
                    value={personaDraft}
                    onChange={e => setPersonaDraft(e.target.value)}
                    rows={4}
                  />
                  <button className="persona-save-btn" onClick={handlePersonaSave}>
                    SAVE
                  </button>
                </div>
              ) : (
                <p className="persona-text">{agent.persona}</p>
              )}
            </div>

            <div className="progress-section">
              <div className="progress-header">
                <span className="meta-key">PROGRESS</span>
                <span className="progress-value">{agent.progress}%</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${agent.progress}%` }} />
              </div>
            </div>

            {agent.status === 'done' && (
              <button className="reset-btn" onClick={handleReset}>
                [RESET UNIT]
              </button>
            )}
          </div>
        </aside>

        {/* Right: Output */}
        <section className="output-panel">
          <div className="panel-label">MISSION OUTPUT</div>

          <div className="message-list">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="pixel-char" />
                <p>UNIT STANDING BY<br />AWAITING ORDERS...</p>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <div className="message-header">
                    <span className="message-sender">
                      {msg.role === 'user' ? '► COMMANDER' : `◆ ${msg.agentName}`}
                    </span>
                    <span className="message-ts">{msg.ts}</span>
                  </div>
                  <p className="message-text" style={{ whiteSpace: 'pre-line' }}>
                    {msg.text}
                  </p>
                </div>
              ))
            )}

            {agent.status === 'running' && (
              <div className="message agent thinking">
                <div className="message-header">
                  <span className="message-sender">◆ UNIT-01</span>
                </div>
                <p className="message-text">
                  PROCESSING<span className="thinking-cursor" />
                </p>
              </div>
            )}
          </div>
        </section>
      </main>

      {/* ── Task Bar ── */}
      <footer className="task-bar">
        <span className="task-bar-prompt">_</span>
        <textarea
          className="task-input"
          placeholder="ENTER COMMAND... (ENTER TO SEND / SHIFT+ENTER FOR NEWLINE)"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={agent.status === 'running'}
        />
        <button
          className={`deploy-btn ${agent.status === 'running' ? 'disabled' : ''}`}
          onClick={handleDeploy}
          disabled={agent.status === 'running' || !input.trim()}
        >
          {agent.status === 'running' ? '[ RUNNING ]' : '[ DEPLOY ► ]'}
        </button>
      </footer>
    </div>
  );
}

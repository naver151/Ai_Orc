import React from 'react';
import './App.css';

function App() {
  return (
    <div className="game-container">
      <div className="background-map">
        <div className="ui-overlay">
          <div className="retro-window status-window">
            <h2>AI Status</h2>
            <p>Status: <span className="text-green">ACTIVE</span></p>
            <p>Project: ALPHA</p>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: '75%' }}></div>
            </div>
          </div>

          <div className="retro-window chat-window">
            <h2>Active Chats</h2>
            <ul>
              <li> User: "코드 예시..."</li>
              <li> Agent: "분석 중..."</li>
            </ul>
          </div>

          <div className="retro-window task-window">
            <h2>Tasks</h2>
            <p> Optimize Path</p>
            <p> Update DB</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
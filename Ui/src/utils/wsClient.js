/**
 * WebSocket 클라이언트 — AI Orc 오케스트레이션 허브
 *
 * 백엔드 ws://localhost:8000/ws 와 연결하여
 * spawn / prompt / pause / resume / kill / set_reviewer 액션을 전송하고
 * log / progress / status / review_* / orchestration_* 이벤트를 수신합니다.
 */

const WS_URL = 'ws://localhost:8000/ws'

class OrcWsClient {
  constructor() {
    this._ws        = null
    this._handlers  = {}   // eventType → [callback, ...]
    this._ready     = false
    this._queue     = []   // 연결 전 쌓인 메시지 대기열
  }

  // ── 연결 ──────────────────────────────────────────────────

  connect() {
    if (this._ws && this._ws.readyState <= 1) return this   // 이미 연결 중

    this._ws = new WebSocket(WS_URL)

    this._ws.onopen = () => {
      this._ready = true
      this._queue.forEach(msg => this._ws.send(msg))
      this._queue = []
      this._emit('connected', {})
    }

    this._ws.onclose = () => {
      this._ready = false
      this._emit('disconnected', {})
    }

    this._ws.onerror = (e) => {
      this._emit('error', { error: e })
    }

    this._ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        this._emit(data.type, data)
        this._emit('*', data)   // 와일드카드 리스너
      } catch {}
    }

    return this
  }

  disconnect() {
    this._ws?.close()
    this._ws    = null
    this._ready = false
  }

  // ── 이벤트 ────────────────────────────────────────────────

  on(type, cb) {
    if (!this._handlers[type]) this._handlers[type] = []
    this._handlers[type].push(cb)
    return () => this.off(type, cb)   // unsubscribe 함수 반환
  }

  off(type, cb) {
    this._handlers[type] = (this._handlers[type] ?? []).filter(h => h !== cb)
  }

  _emit(type, data) {
    ;(this._handlers[type] ?? []).forEach(cb => cb(data))
  }

  // ── 전송 ──────────────────────────────────────────────────

  _send(payload) {
    const msg = JSON.stringify(payload)
    if (this._ready) {
      this._ws.send(msg)
    } else {
      this._queue.push(msg)
    }
  }

  // ── 액션 API ──────────────────────────────────────────────

  /** 에이전트 슬롯 등록 */
  spawn(aiName, provider = 'github') {
    this._send({ action: 'spawn', aiName, provider })
  }

  /** 프롬프트 전송 (오케스트레이션 또는 단일 에이전트) */
  prompt(aiName, text) {
    this._send({ action: 'prompt', aiName, text })
  }

  /** 일시 정지 */
  pause(aiName) {
    this._send({ action: 'pause', aiName })
  }

  /** 재개 */
  resume(aiName) {
    this._send({ action: 'resume', aiName })
  }

  /** 에이전트 종료 */
  kill(aiName) {
    this._send({ action: 'kill', aiName })
  }

  /** 리뷰어 AI 설정 (빈 문자열이면 비활성화) */
  setReviewer(provider) {
    this._send({ action: 'set_reviewer', provider })
  }
}

// 싱글턴 — 앱 전체에서 하나의 WS 연결 공유
export const wsClient = new OrcWsClient()

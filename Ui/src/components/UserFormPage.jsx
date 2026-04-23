import { useState, useRef, useEffect } from 'react'
import styles from './UserFormPage.module.css'

const STEPS = [
  {
    key: 'name',
    question: '이름이 무엇인가요?',
    type: 'text',
    placeholder: '홍길동',
    label: '이름',
  },
  {
    key: 'age',
    question: '나이가 어떻게 되세요?',
    type: 'number',
    placeholder: '25',
    label: '나이',
    unit: '세',
  },
  {
    key: 'job',
    question: '어떤 일을 하시나요?',
    type: 'choice',
    label: '직업',
    options: ['개발자', '디자이너', '기획자', '연구원', '학생', '기타'],
  },
  {
    key: 'gender',
    question: '성별을 선택해주세요',
    type: 'choice',
    label: '성별',
    options: ['남성', '여성', '기타'],
  },
]

export default function UserFormPage({ onSubmit, theme = 'dark', onThemeToggle }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({ name: '', age: '', job: '', gender: '' })
  const [inputVal, setInputVal] = useState('')
  const [error, setError] = useState('')
  const [animKey, setAnimKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    if (STEPS[step]?.type !== 'choice') {
      setTimeout(() => inputRef.current?.focus(), 80)
    }
  }, [step, animKey])

  const validate = () => {
    const s = STEPS[step]
    if (!inputVal.trim()) return '입력해주세요'
    if (s.key === 'age') {
      const n = Number(inputVal)
      if (!Number.isInteger(n) || n < 1 || n > 120) return '올바른 나이를 입력해주세요'
    }
    return ''
  }

  const advance = (value) => {
    const key = STEPS[step].key
    const newAnswers = { ...answers, [key]: key === 'age' ? Number(value) : value }
    setAnswers(newAnswers)
    setInputVal('')
    setError('')

    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
      setAnimKey(k => k + 1)
    } else {
      submit(newAnswers)
    }
  }

  const handleNext = () => {
    const err = validate()
    if (err) { setError(err); return }
    advance(inputVal.trim())
  }

  const submit = async (data) => {
    setLoading(true)
    // uid는 App.jsx가 생성하므로 여기서 미리 생성해 포함
    const uid = `u${Date.now()}${Math.random().toString(36).slice(2, 6)}`
    const payload = { ...data, uid }
    try {
      await fetch('http://localhost:8000/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch {
      // 백엔드 꺼져 있어도 진행
    }
    onSubmit(payload)
  }

  const current = STEPS[step]
  const completed = STEPS.slice(0, step)

  return (
    <div className={styles.page}>
      <div className={styles.gridBg} />
      <div className={styles.glow} />

      <button className={styles.themeBtn} onClick={onThemeToggle} title={theme === 'dark' ? '라이트 모드' : '다크 모드'}>
        {theme === 'dark' ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        )}
      </button>

      <div className={styles.card}>

        {/* 진행 도트 */}
        <div className={styles.dots}>
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`${styles.dot} ${i < step ? styles.dotDone : ''} ${i === step ? styles.dotActive : ''}`}
            />
          ))}
        </div>

        {/* 완료된 답변 요약 */}
        {completed.length > 0 && (
          <div className={styles.summary}>
            {completed.map(s => (
              <div key={s.key} className={styles.summaryItem}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className={styles.summaryLabel}>{s.label}</span>
                <span className={styles.summaryValue}>
                  {answers[s.key]}{s.unit ?? ''}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 현재 스텝 */}
        <div key={animKey} className={styles.stepWrap}>
          <p className={styles.stepNum}>{step + 1} / {STEPS.length}</p>
          <h2 className={styles.question}>{current.question}</h2>

          {current.type === 'text' && (
            <div className={styles.inputGroup}>
              <input
                ref={inputRef}
                className={`${styles.input} ${error ? styles.inputError : ''}`}
                type="text"
                placeholder={current.placeholder}
                value={inputVal}
                onChange={e => { setInputVal(e.target.value); setError('') }}
                onKeyDown={e => e.key === 'Enter' && handleNext()}
              />
              {error && <span className={styles.errorMsg}>{error}</span>}
              <button className={styles.btnNext} onClick={handleNext}>
                다음 <span className={styles.arrow}>→</span>
              </button>
            </div>
          )}

          {current.type === 'number' && (
            <div className={styles.inputGroup}>
              <div className={styles.numberRow}>
                <input
                  ref={inputRef}
                  className={`${styles.input} ${styles.inputNumber} ${error ? styles.inputError : ''}`}
                  type="number"
                  placeholder={current.placeholder}
                  min="1"
                  max="120"
                  value={inputVal}
                  onChange={e => { setInputVal(e.target.value); setError('') }}
                  onKeyDown={e => e.key === 'Enter' && handleNext()}
                />
                {current.unit && <span className={styles.unit}>{current.unit}</span>}
              </div>
              {error && <span className={styles.errorMsg}>{error}</span>}
              <button className={styles.btnNext} onClick={handleNext}>
                다음 <span className={styles.arrow}>→</span>
              </button>
            </div>
          )}

          {current.type === 'choice' && (
            <div className={styles.choices}>
              {current.options.map(opt => (
                <button
                  key={opt}
                  className={styles.choiceBtn}
                  onClick={() => advance(opt)}
                  disabled={loading}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 로딩 */}
        {loading && (
          <div className={styles.loadingOverlay}>
            <span className={styles.spinner} />
          </div>
        )}
      </div>
    </div>
  )
}

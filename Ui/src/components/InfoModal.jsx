import styles from './InfoModal.module.css'

export default function InfoModal({ open, onClose }) {
  if (!open) return null

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h2 className={styles.title}>프로젝트 소개</h2>
        <p>AgentFlow는 중간 관리자 AI가 사용자의 요청을 분석하고, 여러 특화 에이전트에게 업무를 배분하는 멀티 에이전트 시스템입니다.</p>
        <p>사용자는 관리자 AI와 자연스럽게 대화하면 됩니다. 나머지는 에이전트들이 협력해 처리합니다.</p>
        <button className={styles.closeBtn} onClick={onClose}>닫기</button>
      </div>
    </div>
  )
}

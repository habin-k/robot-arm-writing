import { useEffect, useState, useCallback } from 'react'
import { getWritingHistory, deleteWritingHistory } from '../../api/writing'
import styles from './HistoryTab.module.css'

const FILL_LABEL = { outline: '윤곽선', hatch: '속 채우기' }

// ISO8601 → "YYYY.MM.DD HH:MM" (로컬)
function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function HistoryTab() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(() => new Set())  // 선택된 기록 id 집합
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const r = await getWritingHistory(100)
      setRows(r.data)
      setSelected(new Set())   // 새로 불러오면 선택 초기화
    } catch (e) {
      setError('내역을 불러오지 못했습니다: ' + (e.response?.data?.detail || e.message))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggleOne = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const allChecked = rows.length > 0 && selected.size === rows.length
  const toggleAll = () => {
    setSelected(allChecked ? new Set() : new Set(rows.map(r => r.id)))
  }

  const handleDelete = async () => {
    if (selected.size === 0) return
    const all = selected.size === rows.length
    if (!confirm(all
      ? `전체 ${rows.length}건을 삭제할까요?`
      : `선택한 ${selected.size}건을 삭제할까요?`)) return
    setDeleting(true)
    try {
      await deleteWritingHistory(all ? { all: true } : { ids: [...selected] })
      await load()
    } catch (e) {
      alert('삭제 실패: ' + (e.response?.data?.detail || e.message))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <span className={styles.count}>
          {loading ? '불러오는 중…'
            : selected.size > 0 ? `${selected.size}건 선택됨`
            : `총 ${rows.length}건`}
        </span>
        <div className={styles.toolbarBtns}>
          <button className={styles.deleteBtn} onClick={handleDelete}
            disabled={deleting || selected.size === 0}>
            {deleting ? '삭제 중…' : `선택 삭제${selected.size ? ` (${selected.size})` : ''}`}
          </button>
          <button className={styles.refreshBtn} onClick={load} disabled={loading || deleting}>
            ↻ 새로고침
          </button>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {!error && rows.length === 0 && !loading && (
        <div className={styles.empty}>아직 이용 내역이 없습니다.</div>
      )}

      {rows.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.checkCol}>
                  <input type="checkbox" checked={allChecked} onChange={toggleAll}
                    aria-label="전체 선택" />
                </th>
                <th>이용 시각</th>
                <th>닉네임</th>
                <th>문구</th>
                <th>폰트</th>
                <th>크기</th>
                <th>여백</th>
                <th>쓰기 방식</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const checked = selected.has(r.id)
                return (
                  <tr key={r.id} className={checked ? styles.rowChecked : ''}>
                    <td className={styles.checkCol}>
                      <input type="checkbox" checked={checked}
                        onChange={() => toggleOne(r.id)}
                        aria-label="이 기록 선택" />
                    </td>
                    <td className={styles.time}>{formatTime(r.created_at)}</td>
                    <td className={styles.nick}>{r.nickname || '익명'}</td>
                    <td className={styles.text} title={r.text}>{r.text}</td>
                    <td>{r.font_name}</td>
                    <td>{r.char_height_mm}mm</td>
                    <td>{r.margin_mm}mm</td>
                    <td>{FILL_LABEL[r.fill_mode] || r.fill_mode}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

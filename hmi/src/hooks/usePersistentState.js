import { useState, useEffect } from 'react'

// useState 와 동일하게 쓰되, 값이 sessionStorage 에 자동 저장되는 훅.
// 탭을 옮겼다 돌아오거나(컴포넌트 언마운트→재마운트), 새로고침해도 값이 유지된다.
// 창(탭)을 완전히 닫으면 sessionStorage 가 비워져 초기값으로 돌아간다.
export function usePersistentState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = sessionStorage.getItem(key)
      return raw != null ? JSON.parse(raw) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* 저장 실패(용량 초과 등)해도 화면 동작에는 영향 없음 */
    }
  }, [key, value])

  return [value, setValue]
}

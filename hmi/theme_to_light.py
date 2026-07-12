#!/usr/bin/env python3
"""다크 테마 → 라이트(흰 배경) 테마 색상 변환. 토큰 단위 1:1 단일 패스 치환."""
import re
import pathlib

# 다크 → 라이트 매핑 (keep: #fff, #ef4444, #dc2626, #22c55e, #3b82f6 는 그대로)
MAP = {
    '#0d0d0d': '#f7f7f8',  # 사이드바 (옅은 회색)
    '#111':    '#ffffff',  # 메인 배경 / 입력 배경 / 강조버튼 위 글자(→흰)
    '#1a1a1a': '#ffffff',  # 카드
    '#1e1e1e': '#ffffff',  # 캔버스 종이
    '#1f1f1f': '#f3f4f6',  # active/hover 하이라이트
    '#222':    '#e5e7eb',  # dpad 중앙
    '#2a2a2a': '#e5e7eb',  # 테두리
    '#333':    '#d1d5db',  # 캔버스 테두리
    '#3a3a3a': '#c0c4cc',  # placeholder
    '#444':    '#9ca3af',  # muted 텍스트
    '#555':    '#6b7280',  # 라벨
    '#666':    '#6b7280',  # muted 버튼 텍스트
    '#888':    '#4b5563',  # 내비 텍스트
    '#aaa':    '#374151',  # 보조 텍스트
    '#ccc':    '#333333',  # hover 텍스트 / 강조버튼 hover 배경
    '#e2e2e2': '#1a1a1a',  # 캔버스 잉크(글씨) → 진한색
    '#ececec': '#1a1a1a',  # 주 텍스트 / 강조 배경 / 진행바 → 진한색
    '#0f2318': '#ecfdf5',  # feedback 초록 배경
    '#1a3a28': '#a7f3d0',  # feedback 초록 테두리
    '#3a1f1f': '#fef2f2',  # 로그인 에러 배경
    '#2a1515': '#fecaca',  # 로그인 에러 테두리
}

TOKEN = re.compile(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')

def convert(text):
    def repl(m):
        return MAP.get(m.group(0).lower(), m.group(0))
    return TOKEN.sub(repl, text)

root = pathlib.Path(__file__).parent / 'src'
targets = list(root.rglob('*.css')) + [root / 'components/user/PreviewCanvas.jsx']

for f in targets:
    if not f.exists():
        continue
    orig = f.read_text()
    new = convert(orig)
    if new != orig:
        f.write_text(new)
        n = sum(1 for _ in TOKEN.finditer(orig) if _.group(0).lower() in MAP)
        print(f"변환됨: {f.relative_to(root.parent)}  ({n}곳)")
    else:
        print(f"변경없음: {f.relative_to(root.parent)}")

"""
Helvetica 기반 글씨 경로 생성기 (윤곽선 방식).

좌표계:
  원점(0, 0): 도화지 좌측 하단
  X: 오른쪽 방향 (mm)
  Y: 위쪽 방향 (mm)

경로 포맷:
  (x, y, pen_down)
  pen_down=False → 공이동 (펜 올림)
  pen_down=True  → 글씨 (펜 내림)
"""

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen

PEN_UP   = False
PEN_DOWN = True

FONT_PATHS = {
    'regular':      '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Helvetica Extended Medium.ttf',
    'bold':         '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Helvetica Bold.ttf',
    'light':        '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Helvetica Light.ttf',
    'condensed':    '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Helvetica Condensed.ttf',
    'extended':     '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Helvetica Extended.ttf',
    'brother':      '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Brother Signature.otf',
    'sansbold':     '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/GmarketSansBold.otf',
    'sanslight':   '//home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fontsGmarketSansLight.otf',
    'sansmedium':   '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/GmarketSansMedium.otf',
    'griun_cherri': '/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing/fonts/Griun_Cherry1Spoon-Rg.ttf'
}

_CURVE_STEPS = 12


def _quad_points(p0, p1, p2):
    pts = []
    for i in range(1, _CURVE_STEPS + 1):
        t = i / _CURVE_STEPS
        x = (1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t**2*p2[0]
        y = (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t**2*p2[1]
        pts.append((x, y))
    return pts


def _cubic_points(p0, p1, p2, p3):
    pts = []
    for i in range(1, _CURVE_STEPS + 1):
        t = i / _CURVE_STEPS
        x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
        y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


def _flatten_qcurve(start, args):
    """TrueType qCurveTo 분해: 마지막 점만 on-curve, 나머지는 off-curve."""
    pts = []
    cur = start
    off_curves = list(args[:-1])
    end = args[-1]
    if len(off_curves) == 1:
        pts.extend(_quad_points(cur, off_curves[0], end))
    else:
        # 연속 off-curve 점 사이에 암묵적 on-curve 점 삽입
        for i, p1 in enumerate(off_curves):
            if i < len(off_curves) - 1:
                p2 = off_curves[i + 1]
                mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
                pts.extend(_quad_points(cur, p1, mid))
                cur = mid
            else:
                pts.extend(_quad_points(cur, p1, end))
    return pts


def _flatten_ccurve(start, args):
    """Cubic bezier (CFF): p0=start, p1,p2=control points, p3=end."""
    return _cubic_points(start, args[0], args[1], args[2])


class PathGenerator:
    """
    텍스트를 로봇 글씨 경로(waypoints)로 변환합니다. (Helvetica 윤곽선 방식)

    사용 예:
        gen = PathGenerator(font_name='regular', char_height_mm=30)
        path = gen.generate("Hello World")
        for x, y, pen_down in path:
            robot.move(x, y, pen_down)
    """

    def __init__(self,
                 font_name='regular',
                 char_height_mm=15.0,
                 line_spacing_factor=1.6,
                 char_spacing_mm=20,
                 paper_width_mm=295.57,
                 paper_height_mm=209.72,
                 margin_mm=20.0,
                 fill_mode='outline',
                 hatch_spacing_mm=1.0):
        """
        Args:
            font_name:           Helvetica 변형 ('regular', 'bold', 'light', 'condensed', 'extended')
            char_height_mm:      대문자 높이 (mm)
            line_spacing_factor: 줄 간격 = char_height_mm × factor
            char_spacing_mm:     글자 간 추가 간격 (mm)
            paper_width_mm:      도화지 가로 (mm)
            paper_height_mm:     도화지 세로 (mm)
            margin_mm:           상하좌우 여백 (mm)
            fill_mode:           'outline' (테두리만) 또는 'hatch' (속 채우기)
            hatch_spacing_mm:    해칭 선 간격 (mm). fill_mode='hatch' 일 때만 사용.
        """
        font_path = FONT_PATHS.get(font_name, FONT_PATHS['regular'])
        self._tt = TTFont(font_path)
        self._glyph_set = self._tt.getGlyphSet()
        self._cmap = self._tt.getBestCmap()
        self._hmtx = self._tt['hmtx'].metrics

        cap = self._cap_height_units()
        self._scale = char_height_mm / cap  # font units → mm

        self.char_height_mm = char_height_mm
        self.line_spacing_factor = line_spacing_factor
        self.char_spacing_mm = char_spacing_mm
        self.paper_width_mm = paper_width_mm
        self.paper_height_mm = paper_height_mm
        self.margin_mm = margin_mm
        self.fill_mode = fill_mode
        self.hatch_spacing_mm = hatch_spacing_mm

        self._cache = {}  # char → (strokes, adv_mm)

    def _cap_height_units(self):
        """대문자 높이를 font units로 반환. 'H' 글리프 bbox 우선, 없으면 sTypoAscender."""
        os2 = self._tt['OS/2']
        cap = getattr(os2, 'sCapHeight', None)
        if cap:
            return cap
        cmap = self._tt.getBestCmap()
        h_gid = cmap.get(ord('H'))
        if h_gid and 'glyf' in self._tt:
            glyph = self._tt['glyf'][h_gid]
            if hasattr(glyph, 'yMax') and glyph.yMax:
                return glyph.yMax
        return os2.sTypoAscender

    @property
    def line_height_mm(self):
        return self.char_height_mm * self.line_spacing_factor

    def _glyph_strokes(self, char):
        """글자 하나의 윤곽선 획 목록(mm)과 advance width(mm) 반환."""
        if char in self._cache:
            return self._cache[char]

        gid = self._cmap.get(ord(char))
        if gid is None:
            adv = self._hmtx.get('.notdef', (500, 0))[0] * self._scale
            self._cache[char] = ([], adv)
            return [], adv

        pen = RecordingPen()
        self._glyph_set[gid].draw(pen)
        adv = self._hmtx[gid][0] * self._scale

        strokes = []
        cur_stroke = []
        cur_pos = (0.0, 0.0)

        for op, args in pen.value:
            if op == 'moveTo':
                if cur_stroke:
                    strokes.append(cur_stroke)
                cur_pos = args[0]
                cur_stroke = [cur_pos]
            elif op == 'lineTo':
                cur_pos = args[0]
                cur_stroke.append(cur_pos)
            elif op == 'qCurveTo':
                pts = _flatten_qcurve(cur_pos, args)
                cur_stroke.extend(pts)
                cur_pos = args[-1]
            elif op == 'curveTo':
                pts = _flatten_ccurve(cur_pos, args)
                cur_stroke.extend(pts)
                cur_pos = args[-1]
            elif op == 'closePath':
                if cur_stroke:
                    cur_stroke.append(cur_stroke[0])  # 윤곽선 닫기
                    strokes.append(cur_stroke)
                    cur_stroke = []
            elif op == 'endPath':
                if cur_stroke:
                    strokes.append(cur_stroke)
                    cur_stroke = []

        if cur_stroke:
            strokes.append(cur_stroke)

        scaled = [
            [(x * self._scale, y * self._scale) for x, y in s]
            for s in strokes
        ]
        self._cache[char] = (scaled, adv)
        return scaled, adv

    def _hatch_glyph(self, strokes):
        """Even-odd 스캔라인으로 글자 속을 채운 수평 획 목록 반환."""
        segments = [
            (stroke[i], stroke[i + 1])
            for stroke in strokes
            for i in range(len(stroke) - 1)
        ]
        if not segments:
            return []

        all_y = [p[1] for stroke in strokes for p in stroke]
        y_min, y_max = min(all_y), max(all_y)

        # 뱀(serpentine/boustrophedon)형 채우기: 한 줄은 왼→오, 다음 줄은 오→왼으로
        # 방향을 번갈아 그린다. 아래에서 위로 일정하게 훑는 대신 지그재그로 왕복해
        # 사람이 붓으로 음영을 채우는 듯한 자연스러운 궤적이 된다.
        hatch = []
        y = y_min + self.hatch_spacing_mm
        row = 0
        while y < y_max:
            xs = []
            for (x1, y1), (x2, y2) in segments:
                if y1 == y2:
                    continue
                if min(y1, y2) <= y < max(y1, y2):
                    t = (y - y1) / (y2 - y1)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            spans = [(xs[i], xs[i + 1])
                     for i in range(0, len(xs) - 1, 2) if xs[i + 1] > xs[i]]
            if row % 2 == 1:
                # 홀수 줄: 스팬 순서와 각 스팬의 방향을 뒤집어 오른쪽→왼쪽으로 왕복
                spans = [(b, a) for a, b in reversed(spans)]
            for a, b in spans:
                hatch.append([(a, y), (b, y)])
            y += self.hatch_spacing_mm
            row += 1
        return hatch

    def _line_width(self, text):
        total = 0.0
        for ch in text:
            _, adv = self._glyph_strokes(ch)
            total += adv + self.char_spacing_mm
        return total

    def _wrap(self, text):
        """단어 단위 자동 줄바꿈. 단어 자체가 너무 길면 글자 단위로 자름."""
        max_w = self.paper_width_mm - 2 * self.margin_mm
        result = []
        for raw in text.split('\n'):
            words = raw.split(' ')
            line = ''
            for word in words:
                if self._line_width(word) > max_w:
                    if line:
                        result.append(line)
                        line = ''
                    chunk = ''
                    for ch in word:
                        if self._line_width(chunk + ch) <= max_w:
                            chunk += ch
                        else:
                            if chunk:
                                result.append(chunk)
                            chunk = ch
                    line = chunk
                    continue

                candidate = (line + ' ' + word).strip() if line else word
                if self._line_width(candidate) <= max_w:
                    line = candidate
                else:
                    if line:
                        result.append(line)
                    line = word
            if line:
                result.append(line)
        return result

    def stroke_char_map(self, text):
        """generate() 와 '같은 순서'로, 각 획(pen_down 연속 구간)이 속한 글자를
        리스트로 반환한다. i번째 원소 = (i+1)번째 획의 글자.
        서버가 획 진행 인덱스로 '현재 글자'를 역추적하는 데 사용한다.
        (generate 의 글자·획 순회 로직과 반드시 일치시켜야 한다.)"""
        chars = []
        for line in self._wrap(text):
            if not line:
                continue
            for ch in line:
                strokes, _adv = self._glyph_strokes(ch)
                draw_strokes = (self._hatch_glyph(strokes)
                                if self.fill_mode == 'hatch' else strokes)
                for stroke in draw_strokes:
                    if not stroke:
                        continue
                    chars.append(ch)
        return chars

    def generate(self, text, center_h=True, center_v=True):
        """
        텍스트를 경로 좌표 리스트로 변환합니다.

        Args:
            text:     쓸 텍스트. '\\n' 으로 줄바꿈.
            center_h: 도화지 가로 중앙 정렬
            center_v: 도화지 세로 중앙 정렬

        Returns:
            list of (x_mm, y_mm, pen_down)
        """
        lines = self._wrap(text)
        if not lines:
            return []

        block_h = (len(lines) - 1) * self.line_height_mm + self.char_height_mm

        if center_v:
            block_top_y = (self.paper_height_mm + block_h) / 2.0
        else:
            block_top_y = self.paper_height_mm - self.margin_mm

        path = []
        for i, line in enumerate(lines):
            if not line:
                continue

            x_offset = ((self.paper_width_mm - self._line_width(line)) / 2.0
                        if center_h else self.margin_mm)
            # TTF 좌표: baseline=0, cap=char_height_mm (스케일 후)
            y_offset = block_top_y - i * self.line_height_mm - self.char_height_mm

            cur_x = x_offset
            for ch in line:
                strokes, adv = self._glyph_strokes(ch)
                draw_strokes = (self._hatch_glyph(strokes)
                                if self.fill_mode == 'hatch' else strokes)
                for stroke in draw_strokes:
                    if not stroke:
                        continue
                    path.append((cur_x + stroke[0][0],
                                 y_offset + stroke[0][1],
                                 PEN_UP))
                    for sx, sy in stroke:
                        path.append((cur_x + sx, y_offset + sy, PEN_DOWN))
                cur_x += adv + self.char_spacing_mm

        # 실제 크기(char_height_mm) 유지 + 중앙 정렬.
        #   → 글씨 크기 슬라이더가 실제 글자 높이(mm)를 그대로 결정한다.
        #   → 텍스트 블록이 여백 안쪽 영역(용지 - 2*여백)을 '넘칠 때만' 축소해서 담는다.
        #     (여백은 크기 조절이 아니라 '종이 밖으로 안 나가게 하는 경계'로 작동)
        if path:
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            block_w = max(xs) - min(xs)
            block_h = max(ys) - min(ys)
            draw_w = self.paper_width_mm - 2 * self.margin_mm
            draw_h = self.paper_height_mm - 2 * self.margin_mm
            if block_w > 1e-6 and block_h > 1e-6 and draw_w > 0 and draw_h > 0:
                s = 1.0                                   # 기본: 실제 크기 유지
                if block_w > draw_w or block_h > draw_h:  # 여백 상자를 넘칠 때만 축소
                    s = min(draw_w / block_w, draw_h / block_h)
                bx = (min(xs) + max(xs)) / 2.0   # 블록 중심
                by = (min(ys) + max(ys)) / 2.0
                px = self.paper_width_mm / 2.0    # 용지 중심
                py = self.paper_height_mm / 2.0
                path = [((x - bx) * s + px, (y - by) * s + py, pd)
                        for x, y, pd in path]

        return path

    def summary(self, path):
        if not path:
            return "경로 없음"
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        strokes = sum(1 for i, p in enumerate(path)
                      if p[2] == PEN_DOWN and (i == 0 or path[i-1][2] == PEN_UP))
        return (
            f"총 웨이포인트: {len(path)}  (획 수: {strokes})\n"
            f"  공이동: {sum(1 for p in path if not p[2])}  "
            f"글씨: {sum(1 for p in path if p[2])}\n"
            f"  X: {min(xs):.1f} ~ {max(xs):.1f} mm\n"
            f"  Y: {min(ys):.1f} ~ {max(ys):.1f} mm"
        )

    def export_csv(self, path, filepath):
        with open(filepath, 'w') as f:
            f.write("x_mm,y_mm,pen_down\n")
            for x, y, pd in path:
                f.write(f"{x:.4f},{y:.4f},{int(pd)}\n")
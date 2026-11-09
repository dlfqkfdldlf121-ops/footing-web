# -*- coding: utf-8 -*-
"""검토보고서 PDF → 표 구조 JSON.
각 표: page, title(표 위 2~3줄), unit, header(열 제목 경로), rows[{label, cells(raw), nums}]
숫자는 '(1,234)' → -1234, '-' → 0, 공란 → None.
"""
import json, re, sys
import pymupdf

NUM = re.compile(r'^\(?-?[\d,]+(\.\d+)?\)?%?$')


def to_num(s):
    if s is None:
        return None
    s = s.strip().replace(' ', '')
    if s in ('', ):
        return None
    if s in ('-', '–', '—'):
        return 0
    if not NUM.match(s):
        return None
    neg = s.startswith('(') or s.startswith('-')
    v = s.strip('()%-').replace(',', '')
    try:
        x = float(v) if '.' in v else int(v)
    except ValueError:
        return None
    return -x if neg else x


def cell_text(page, rect, words=None):
    """셀 영역 안의 단어를 읽는다. words(page.get_text('words'))를 주면 빠르다."""
    if rect is None:
        return None
    if words is None:
        t = page.get_textbox(pymupdf.Rect(rect))
        return re.sub(r'\s+', ' ', t).strip()
    x0, y0, x1, y1 = rect
    ws = [w for w in words if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1]
    ws.sort(key=lambda w: (round(w[3]), w[0]))
    return ' '.join(w[4] for w in ws).strip()


def title_above(page, bbox, n=3):
    """표 바로 위 텍스트 줄 n개."""
    lines = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            y = l['bbox'][3]
            if y <= bbox[1] + 1 and bbox[1] - y < 120:
                txt = ''.join(s['text'] for s in l['spans']).strip()
                if txt:
                    lines.append((y, txt))
    lines.sort()
    return ' / '.join(t for _, t in lines[-n:])


HEAD = re.compile(r'^(\d{1,2})\.\s*([^\d\s].{1,40})$')
SUB = re.compile(r'^\((\d{1,2})\)\s*(.{1,50})$')


def col_names(hdr, ncol):
    names = [''] * ncol
    for row in hdr:
        last = ''
        for i in range(ncol):
            c = row[i] if i < len(row) else None
            if c is None:
                c = last            # 병합 셀: 왼쪽 값 이어받기
            else:
                last = c
            if c and c not in names[i]:
                names[i] = (names[i] + ' ' + c).strip()
    return names


def extract(path):
    doc = pymupdf.open(path)
    out = {'file': path, 'pages': [], 'tables': []}
    note, sub = '', ''
    for pno, page in enumerate(doc):
        out['pages'].append(page.get_text())
        lines = []
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                txt = ''.join(sp['text'] for sp in l['spans']).strip()
                if txt:
                    lines.append((l['bbox'][1], txt))
        lines.sort()
        tabs = sorted(page.find_tables().tables, key=lambda t: t.bbox[1])
        words = page.get_text('words')
        li = 0
        def advance(ylim):
            nonlocal li, note, sub
            while li < len(lines) and lines[li][0] < ylim:
                t = lines[li][1]
                m = HEAD.match(t)
                if m and len(t) < 40:
                    note, sub = m.group(1) + '. ' + m.group(2).strip(), ''
                m = SUB.match(t)
                if m:
                    sub = '(' + m.group(1) + ') ' + m.group(2).strip()[:30]
                li += 1
        for t in tabs:
            advance(t.bbox[1])
            grid = []
            for r in t.rows:
                grid.append([cell_text(page, c, words) for c in r.cells])
            if not grid or len(grid[0]) < 2:
                continue
            # 헤더: 숫자 없는 앞쪽 행들
            hdr = []
            k = 0
            while k < len(grid) and not any(to_num(c) is not None and c not in ('-',)
                                            for c in grid[k][1:] if c):
                hdr.append(grid[k]); k += 1
                if k >= 3:
                    break
            rows = []
            for r in grid[k:]:
                label = ' '.join(c for c in r[:1] if c) or ''
                rows.append({'cells': r, 'label': label, 'nums': [to_num(c) for c in r]})
            ttl = title_above(page, t.bbox)
            unit = re.search(r'\(단위\s*:\s*([^)]+)\)', ttl + ' ' + (page.get_text()[:400]))
            out['tables'].append({'page': pno + 1, 'title': ttl, 'note': note, 'sub': sub,
                                  'bbox': list(t.bbox), 'cols': col_names(hdr, len(grid[0])), 'unit': unit.group(1).strip() if unit else '',
                                  'header': hdr, 'rows': rows, 'ncol': len(grid[0])})
        advance(1e9)
    return out


if __name__ == '__main__':
    for p in sys.argv[1:]:
        d = extract(p)
        o = p.rsplit('.', 1)[0] + '.tables.json'
        json.dump(d, open(o, 'w', encoding='utf-8'), ensure_ascii=False)
        print(p, 'pages', len(d['pages']), 'tables', len(d['tables']))

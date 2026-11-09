# -*- coding: utf-8 -*-
"""검토결과 JSON → 검토결과 엑셀(.xlsx, 7개 시트).

입력 JSON 구조는 schema.md 참조. 차이는 수식, 판정은
  · Claude가 준 값(정상변동/확인필요/불일치 등)이 있으면 그대로
  · 없으면 차이로 자동 판정(0 → 일치, 허용 단수차이 이내 → 일치 + 비고 '단수차이')
요약 시트 건수(검토 건수/불일치/확인필요)는 각 시트 행에서 자동 집계한다.
"""
import json, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

NAVY, SEC = '1F3864', 'D9E2F3'
BAD_BG, BAD_FG = 'FCE4E4', 'C00000'
CHK_BG, CHK_FG = 'FFF2CC', 'BF8F00'
NUM = '#,##0;(#,##0);-'
F_BODY = '맑은 고딕'
F_HEAD = 'Noto Sans CJK KR'
THIN = Side(style='thin', color='BFBFBF')
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

BAD = {'불일치', '오류', '상'}
CHK = {'확인필요', '중'}

SHEETS = ['0.검토요약', '1.전기말_감사보고서대사', '2.전반기_반기보고서대사',
          '3.본문_주석대사', '4.주석간대사', '5.소계합계_검증', '6.오탈자_표기검토']


def head(ws, titles, widths):
    for i, (t, w) in enumerate(zip(titles, widths), 1):
        c = ws.cell(1, i, t)
        c.font = Font(name=F_HEAD, bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=NAVY)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = BOX
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'A2'


def section(ws, r, text, ncol):
    for i in range(1, ncol + 1):
        c = ws.cell(r, i)
        c.fill = PatternFill('solid', fgColor=SEC)
        c.border = BOX
    c = ws.cell(r, 1, text)
    c.font = Font(name=F_HEAD, bold=True, color=NAVY, size=10)


def body(c, num=False, note=False):
    c.font = Font(name=F_HEAD if note else F_BODY, size=10 if not note else 9)
    c.border = BOX
    c.alignment = Alignment(vertical='center', wrap_text=True,
                            horizontal='right' if num else 'left')
    if num:
        c.number_format = NUM


def verdict_style(c, v):
    c.alignment = Alignment(horizontal='center', vertical='center')
    if v in BAD:
        c.fill = PatternFill('solid', fgColor=BAD_BG)
        c.font = Font(name=F_BODY, bold=True, color=BAD_FG, size=10)
    elif v in CHK:
        c.fill = PatternFill('solid', fgColor=CHK_BG)
        c.font = Font(name=F_BODY, bold=True, color=CHK_FG, size=10)


def auto_verdict(a, b, given, tol, ok_word='일치', unit='원'):
    """판정 자동 결정. given 있으면 우선. 반환 (판정, 비고 접두)."""
    if given:
        return given, ''
    if a is None or b is None:
        return '확인필요', ''
    d = a - b
    if d == 0:
        return ok_word, ''
    if abs(d) <= tol:
        return '일치', '%s%s 단수차이' % (format(abs(d), ','), unit)
    return '불일치', ''


def join_note(prefix, note):
    if prefix and note:
        return prefix + '. ' + note
    return prefix or note or ''


def compare_sheet(ws, data, with_period, tol):
    """시트1·2: 구분/항목/(기간)/단위/A/B/차이/판정/비고"""
    t = ['구분', '항목'] + (['기간'] if with_period else []) + \
        ['단위', data['col_a'], data['col_b'], '차이', '판정', '비고']
    w = [26, 34] + ([7] if with_period else []) + [6, 17, 17, 12, 9, 70]
    head(ws, t, w)
    ncol = len(t)
    ia = 4 + (1 if with_period else 0)       # 금액 A 열 번호
    r, stats = 2, [0, 0, 0]
    for sec in data['sections']:
        section(ws, r, sec['title'], ncol); r += 1
        for row in sec['rows']:
            v, pre = auto_verdict(row.get('a'), row.get('b'), row.get('verdict'),
                                  tol.get(row.get('unit', '원'), 0), unit=row.get('unit', '원'))
            vals = [row.get('gubun'), row.get('item')] + \
                   ([row.get('period')] if with_period else []) + \
                   [row.get('unit'), row.get('a'), row.get('b')]
            for i, x in enumerate(vals, 1):
                body(ws.cell(r, i, x), num=i >= ia)
            A, B = ws.cell(r, ia).coordinate, ws.cell(r, ia + 1).coordinate
            dc = ws.cell(r, ia + 2,
                         '=%s-%s' % (A, B) if row.get('a') is not None and row.get('b') is not None else None)
            body(dc, num=True)
            vc = ws.cell(r, ia + 3, v); body(vc); verdict_style(vc, v)
            body(ws.cell(r, ia + 4, join_note(pre, row.get('note'))), note=True)
            stats[0] += 1; stats[1] += v in BAD; stats[2] += v in CHK
            r += 1
    return stats


def sheet3(ws, data, tol):
    t = ['재무제표', '본문 항목', '본문 금액(원)', '관련 주석', '주석 금액(천원)',
         '주석금액×1,000', '차이(원)\n※±%s원 미만은\n천원단위 반올림' % format(tol, ','), '판정', '비고']
    head(ws, t, [16, 30, 17, 38, 14, 17, 13, 9, 70])
    ws.row_dimensions[1].height = 46
    r, stats = 2, [0, 0, 0]
    for sec in data['sections']:
        section(ws, r, sec['title'], 9); r += 1
        for row in sec['rows']:
            a, n = row.get('body'), row.get('note_amt')
            mult = row.get('mult', 1000)
            v, pre = auto_verdict(a, None if n is None else n * mult, row.get('verdict'), tol)
            if row.get('verdict') is None and n is None:
                v, pre = '일치', ''      # 합산 검증 행(주석 금액 없음) — Claude가 판정 안 주면 일치
            for i, x in enumerate([row.get('fs'), row.get('item'), a, row.get('note_ref'), n], 1):
                body(ws.cell(r, i, x), num=i in (3, 5))
            body(ws.cell(r, 6, '=E%d*%d' % (r, mult) if n is not None else None), num=True)
            body(ws.cell(r, 7, '=C%d-F%d' % (r, r) if n is not None and a is not None else None), num=True)
            vc = ws.cell(r, 8, v); body(vc); verdict_style(vc, v)
            body(ws.cell(r, 9, join_note(pre, row.get('note'))), note=True)
            stats[0] += 1; stats[1] += v in BAD; stats[2] += v in CHK
            r += 1
    return stats


def sheet4(ws, rows, tol):
    head(ws, ['No', '대사 항목', '출처 A', '금액 A', '출처 B / 재계산 근거', '금액 B', '차이', '판정', '비고'],
         [5, 30, 34, 15, 38, 15, 12, 9, 70])
    order = {'불일치': 0, '오류': 0, '확인필요': 1}
    rows = sorted(rows, key=lambda x: order.get(
        auto_verdict(x.get('a'), x.get('b'), x.get('verdict'), tol)[0], 2))
    stats = [0, 0, 0]
    for k, row in enumerate(rows, 1):
        r = k + 1
        v, pre = auto_verdict(row.get('a'), row.get('b'), row.get('verdict'), tol, unit='천원')
        for i, x in enumerate([k, row.get('item'), row.get('src_a'), row.get('a'),
                               row.get('src_b'), row.get('b')], 1):
            body(ws.cell(r, i, x), num=i in (4, 6))
        body(ws.cell(r, 7, '=D%d-F%d' % (r, r)), num=True)
        vc = ws.cell(r, 8, v); body(vc); verdict_style(vc, v)
        body(ws.cell(r, 9, join_note(pre, row.get('note'))), note=True)
        stats[0] += 1; stats[1] += v in BAD; stats[2] += v in CHK
    return stats


def sheet5(ws, data, tol):
    head(ws, ['구분', '검증 대상', '단위', '표시 금액', '재계산 금액', '차이', '판정', '비고'],
         [18, 38, 6, 17, 17, 12, 9, 70])
    r, stats = 2, [0, 0, 0]
    for sec in data['sections']:
        section(ws, r, sec['title'], 8); r += 1
        for row in sec['rows']:
            v, pre = auto_verdict(row.get('shown'), row.get('recalc'), row.get('verdict'),
                                  tol.get(row.get('unit', '원'), 0), ok_word='적정',
                                  unit=row.get('unit', '원'))
            if v == '불일치':
                v = '오류'
            for i, x in enumerate([row.get('gubun'), row.get('target'), row.get('unit'),
                                   row.get('shown'), row.get('recalc')], 1):
                body(ws.cell(r, i, x), num=i >= 4)
            body(ws.cell(r, 6, '=D%d-E%d' % (r, r)), num=True)
            vc = ws.cell(r, 7, v); body(vc); verdict_style(vc, v)
            body(ws.cell(r, 8, join_note(pre, row.get('note'))), note=True)
            stats[0] += 1; stats[1] += v in BAD; stats[2] += v in CHK
            r += 1
    return stats


def sheet6(ws, findings):
    head(ws, ['No', '위치', '유형', '현재 표기 / 내용', '수정 제안', '중요도'],
         [5, 30, 18, 50, 70, 7])
    for k, f in enumerate(findings, 1):
        r = k + 1
        for i, x in enumerate([k, f['loc'], f['type'], f['current'], f['fix'], f['sev']], 1):
            body(ws.cell(r, i, x), note=i in (4, 5))
        verdict_style(ws.cell(r, 6), f['sev'])
    return [len(findings), sum(f['sev'] == '상' for f in findings),
            sum(f['sev'] == '중' for f in findings)]


def order_findings(findings):
    """상→중→하 정렬 후 번호 부여. 엑셀 시트6 No = PDF 배지 번호."""
    rank = {'상': 0, '중': 1, '하': 2}
    out = sorted(findings, key=lambda f: rank[f['sev']])
    for k, f in enumerate(out, 1):
        f['no'] = k
    return out


def build(data, out):
    tol = data.get('tolerance', {'원': 0, '천원': 1, '주': 0})
    tol3 = data.get('tolerance_sheet3', 500)
    findings = order_findings(data['findings'])
    wb = Workbook()
    ws0 = wb.active; ws0.title = SHEETS[0]
    st = {}
    st[1] = compare_sheet(wb.create_sheet(SHEETS[1]), data['s1'], False, tol)
    st[2] = compare_sheet(wb.create_sheet(SHEETS[2]), data['s2'], True, tol)
    st[3] = sheet3(wb.create_sheet(SHEETS[3]), data['s3'], tol3)
    st[4] = sheet4(wb.create_sheet(SHEETS[4]), data['s4'], tol.get('천원', 1))
    st[5] = sheet5(wb.create_sheet(SHEETS[5]), data['s5'], tol)
    st[6] = sheet6(wb.create_sheet(SHEETS[6]), findings)

    head(ws0, ['검토항목', '검토 범위', '검토 건수', '불일치·오류', '확인필요', '주요 발견사항'],
         [26, 44, 9, 10, 9, 110])
    for k, s in enumerate(data['summary'], 1):
        r = k + 1
        n, bad, chk = st[k]
        for i, x in enumerate([s['item'], s['scope'], n, bad or '-', chk or '-', s['findings']], 1):
            body(ws0.cell(r, i, x), num=i in (3, 4, 5), note=i == 6)
        if bad:
            c = ws0.cell(r, 4); c.fill = PatternFill('solid', fgColor=BAD_BG)
            c.font = Font(name=F_BODY, bold=True, color=BAD_FG, size=10)
        if chk:
            c = ws0.cell(r, 5); c.fill = PatternFill('solid', fgColor=CHK_BG)
            c.font = Font(name=F_BODY, bold=True, color=CHK_FG, size=10)
        ws0.row_dimensions[r].height = 80
    c = ws0.cell(len(data['summary']) + 3, 1, data['meta'].get('footnote', ''))
    c.font = Font(name=F_HEAD, size=9, color='808080')
    wb.save(out)
    return findings


def self_audit(data):
    """판정-차이 정합성: Claude가 준 판정이 차이와 모순되는 행을 찾는다."""
    tol = data.get('tolerance', {'원': 0, '천원': 1, '주': 0})
    tol3 = data.get('tolerance_sheet3', 500)
    bad = []
    def chk(sheet, label, a, b, v, t, note=''):
        if v is None or a is None or b is None:
            return
        d = a - b
        # 비고에 단수차이 근거를 적은 소액 차이(천원 2 / 원 1,500 이내)는 '일치' 허용 — 지침: 단수차이는 일치 + 비고
        small = 2 if t <= 2 else 1500
        if v in ('일치', '적정') and abs(d) <= small and ('단수' in (note or '') or '차이' in (note or '')):
            return
        if v in ('일치', '적정') and abs(d) > t:
            bad.append((sheet, label, v, d, '일치인데 차이 유의적'))
        if v in ('불일치', '오류') and d == 0:
            bad.append((sheet, label, v, d, '불일치인데 차이 0'))
    for key in ('s1', 's2'):
        for sec in data[key]['sections']:
            for r in sec['rows']:
                chk(key, r.get('item'), r.get('a'), r.get('b'), r.get('verdict'), tol.get(r.get('unit', '원'), 0), r.get('note'))
    for sec in data['s3']['sections']:
        for r in sec['rows']:
            n = r.get('note_amt')
            chk('s3', r.get('item'), r.get('body'), None if n is None else n * r.get('mult', 1000), r.get('verdict'), tol3, r.get('note'))
    for r in data['s4']:
        chk('s4', r.get('item'), r.get('a'), r.get('b'), r.get('verdict'), tol.get('천원', 1))
    for sec in data['s5']['sections']:
        for r in sec['rows']:
            chk('s5', r.get('target'), r.get('shown'), r.get('recalc'), r.get('verdict'), tol.get(r.get('unit', '원'), 0))
    return bad


if __name__ == '__main__':
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    build(d, sys.argv[2])
    print('saved', sys.argv[2])

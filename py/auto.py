# -*- coding: utf-8 -*-
"""키 없는 자동 파이프라인: PDF 3개 → 검토결과 JSON(판단 문장 없이).

프로그램이 하는 것: 표 추출 → 시트1·2 자동 대사 → 시트3 본문↔주석 자동 매칭 → 시트5 산식·소계 검증
                   → 차이·미매칭 행을 지적사항(시트6·체크본 PDF)으로 자동 등록.
Claude(API 키)가 붙으면: 확인필요 행의 원인 추정·주석간 판단·지적 문안을 채운다(llm.py, 추후).
"""
import re
from extract import extract
from recon import stitch, compare, subtotal_checks
import stmt
import body_note

fmt = lambda x: format(x, ',')


def pdf_num(v, unit):
    """PDF에 찍힌 모양으로 숫자 문자열을 만든다 (음수는 괄호)."""
    if isinstance(v, float):
        s = ('%.2f' % abs(v))
    else:
        s = fmt(abs(int(v)))
    return '(%s)' % s if v < 0 else s


def is_restated(cur):
    txt = ' '.join(cur['pages'][:12])
    return '중단영업' in txt


def analyze(cur_pdf, audit_pdf, half_pdf, company='', period='', kind='연결', progress=None):
    P = progress or (lambda m, f: None)
    P('당기 보고서 표 추출', 0.05)
    C = stitch(extract(cur_pdf))
    P('전기 감사보고서 표 추출', 0.30)
    A = stitch(extract(audit_pdf))
    P('전년 반기보고서 표 추출', 0.50)
    H = stitch(extract(half_pdf))
    P('대사 중', 0.70)
    FS = (kind if kind == '연결' else '') + '%s'
    restated = is_restated(C)
    merged = '주식병합' in ' '.join(C['pages'])

    # ── 시트1
    x1 = lambda n: n.replace('제29(전)기말', '제29(당)기말').replace('(전)기말', '(당)기말').replace('전기말', '당기말')
    r1 = compare(C, A, ['전기말', '(전)기말', '전기'], xlat=x1)
    row1 = lambda r: dict(gubun=(FS % '재무상태표' if r['page'] <= 10 else r['sec']), item='%s · %s' % (r['item'], r['col']),
                          unit=r['unit'], a=r['a'], b=r['b'], page=r['page'], note='비교 p%d' % r['b_page'])
    s1 = {"col_a": "%s 당기 보고서\n(전기말)" % period, "col_b": "전기 감사보고서\n(당기말)", "sections": [
        {"title": "Ⅰ. 재무제표 본문 전기말 열 (단위: 원)", "rows": [row1(r) for r in r1 if r['page'] <= 10]},
        {"title": "Ⅱ. 주석 전기말 열", "rows": [row1(r) for r in r1 if r['page'] > 10]}]}

    # ── 시트2
    x2 = lambda n: n.replace('(전)반기', '(당)반기').replace('전반기', '당반기')
    per = lambda c: '3개월' if '3개월' in (c or '') else '누적'
    r2 = compare(C, H, ['전반기', '(전) 반기', '(전)반기'], per, xlat=x2)
    pl_rows = stmt.restated_pl(C, H) if restated else []
    rows2 = []
    for r in r2:
        if restated and r['page'] <= 10 and pl_rows and r['b_page'] <= 10 and '현금' not in r['sec']:
            # 본문 손익은 계속+중단 합산 행으로 대체 (주당손익만 따로)
            if '주당' not in r['item']:
                continue
        vr, nt = None, '비교 p%d' % r['b_page']
        if '주당' in r['item'] and r['a'] != r['b'] and merged and r['b'] and r['a'] % r['b'] == 0:
            vr, nt = '정상변동', '주식병합 소급 재작성 추정: 비교 보고서 × %d' % (r['a'] // r['b'])
        elif restated and r['a'] != r['b'] and any(k in (r['col'] or '') for k in ('3개월', '누적')) and r['page'] > 10:
            # 손익 성격 주석(3개월·누적 열)은 계속영업분만 재작성되어 금액이 달라지는 것이 정상
            vr, nt = '정상변동', '중단영업 재작성 추정 — 당기 보고서 전반기는 계속영업분만 표시(합계 대사는 Ⅰ섹션)'
        rows2.append(dict(gubun=r['sec'] if r['page'] > 10 else ('본문 p%d' % r['page']), item='%s · %s' % (r['item'], r['col']),
                          period=r['period'], unit=r['unit'], a=r['a'], b=r['b'], verdict=vr, note=nt, page=r['page']))
    s2 = {"col_a": "%s 당기 보고서\n(전반기)" % period, "col_b": "전년 반기보고서\n(당반기)", "sections": []}
    if pl_rows:
        s2['sections'].append({"title": "Ⅰ. 포괄손익계산서 (단위: 천원) — 중단영업 재작성: 당기 보고서 계속 + 주석 중단 ↔ 전년 본문", "rows": pl_rows})
    s2['sections'].append({"title": "Ⅱ. 본문·주석 전반기 열", "rows": rows2})

    # ── 시트3
    sce_vals = set()
    for t in C['tables']:
        if t['page'] <= 10 and t['ncol'] >= 8:
            for r in t['rows']:
                sce_vals |= {x for x in r['nums'] if isinstance(x, (int, float))}
    bn = body_note.match(C, [(FS % fs[2:] if fs.startswith('연결') else fs, t, c)
                             for fs, t, c in body_note.stmt_tables(C)])
    rows3 = []
    for r in bn:
        if '주당' in r['item']:
            continue
        row = dict(fs=r['fs'], item=r['item'], body=r['body'], note_ref=r['note_ref'] + (' (p%d)' % r['page'] if r['page'] else ''),
                   note_amt=r['note_amt'], page=r['page'])
        if r['note_amt'] is None:
            if r['body'] in sce_vals:
                row.update(note_ref='자본변동표 동일 금액', verdict='일치', note='자본변동표에서 같은 금액 확인')
            else:
                row.update(verdict='확인필요', note='주석에서 대응 금액을 찾지 못함 — 원인 확인 필요(키 연결 시 자동 판단)')
        elif 500 < abs(r['body'] - r['note_amt'] * 1000) <= 1500:
            row.update(verdict='일치', note='%s원 단수차이 — 주석 천원 표시 반올림/절사' % fmt(abs(r['body'] - r['note_amt'] * 1000)))
        rows3.append(row)
    s3 = {"sections": [{"title": "본문 ↔ 주석 (본문 원 → 천원 환산 자동 검색)", "rows": rows3}]}

    # ── 시트4 (키 없음: 본문 한 줄이 여러 주석에 같은 금액으로 나오는지)
    rows4 = []
    for r in bn:
        refs = [x.strip() for x in (r['note_ref'] or '').split('·') if x.strip()]
        if len(refs) >= 2 and r['note_amt'] is not None:
            rows4.append(dict(item=r['item'], src_a=refs[0], a=r['note_amt'], src_b=' · '.join(refs[1:]), b=r['note_amt'],
                              note='여러 주석에 동일 금액 표시 확인'))

    # ── 시트5
    rows5a = [dict(gubun=FS % x['gubun'][2:] if x['gubun'].startswith('연결') else x['gubun'], target=x['target'], unit=x['unit'],
                   shown=x['shown'], recalc=x['recalc'], note=x['note'], page=None) for x in stmt.statement_checks(C)]
    rows5b = [dict(gubun=x['sec'][:28], target=x['target'], unit=x['unit'] or '천원', shown=x['shown'], recalc=x['recalc'],
                   note='p%d · %d개 항목' % (x['page'], x['n']), page=x['page']) for x in subtotal_checks(C, 1)]
    s5 = {"sections": [{"title": "Ⅰ. 재무제표 본문 산식 재계산 (단위: 원)", "rows": rows5a},
                       {"title": "Ⅱ. 주석 표별 소계·합계·행합계·기초→기말 검증", "rows": rows5b}]}

    # ── 지적사항 자동 등록
    F = []
    def add(sev, loc, typ, cur, fix, page, nums, unit):
        F.append(dict(loc=loc, type=typ, current=cur, fix=fix, sev=sev,
                      pdf=dict(page=page, find=[pdf_num(n, unit) for n in nums if n is not None])))
    for sec in s1['sections']:
        for r in sec['rows']:
            d = r['a'] - r['b']
            if d:
                sev = '하' if abs(d) <= 1 else '상'
                add(sev, '%s (전기말)' % r['gubun'][:30], '전기 감사보고서와 %s' % ('단수차이' if sev == '하' else '불일치'),
                    '%s: %s ↔ 감사보고서 %s' % (r['item'], fmt(r['a']), fmt(r['b'])), '차이 %s — 원인 확인' % fmt(d), r['page'], [r['a']], r['unit'])
    for r in rows2:
        d = r['a'] - r['b']
        if d and not r['verdict']:
            sev = '하' if abs(d) <= 2 else '상'
            add(sev, '%s (전반기)' % r['gubun'][:30], '전년 반기보고서와 %s' % ('단수차이' if sev == '하' else '불일치'),
                '%s: %s ↔ 전년 %s' % (r['item'], fmt(r['a']), fmt(r['b'])), '차이 %s — 원인 확인' % fmt(d), r['page'], [r['a']], r['unit'])
    for r in rows3:
        if r.get('verdict') == '확인필요':
            add('중', '%s 본문' % r['fs'], '주석 대응 금액 미발견', '%s %s원' % (r['item'], fmt(r['body'])),
                '관련 주석 공시 또는 조정내역 확인', None, [r['body']], '원')
    for sec in s5['sections']:
        for r in sec['rows']:
            d = r['shown'] - r['recalc']
            if abs(d) > (1 if r['unit'] != '원' else 0):
                add('상', r['gubun'], '소계·합계 산술 오류', '%s: 표시 %s ↔ 재계산 %s' % (r['target'], fmt(r['shown']), fmt(r['recalc'])),
                    '차이 %s — 표시 금액 정정' % fmt(d), r['page'], [r['shown']], r['unit'])

    n = lambda rows, pred: sum(1 for r in rows if pred(r))
    all1 = [r for s in s1['sections'] for r in s['rows']]
    all2 = [r for s in s2['sections'] for r in s['rows']]
    all5 = rows5a + rows5b
    summary = [
        {"item": "1. 전기말 금액 대사", "scope": "당기 보고서 전기말 열 ↔ 전기 감사보고서 당기말",
         "findings": "자동 대응 %d건 중 차이 %d건" % (len(all1), n(all1, lambda r: r['a'] != r['b']))},
        {"item": "2. 전반기 금액 대사", "scope": "당기 보고서 전반기 열 ↔ 전년 반기보고서 당반기",
         "findings": "자동 대응 %d건%s" % (len(all2), ' · 중단영업 재작성 반영(계속+중단 합산 대사)' if pl_rows else '')},
        {"item": "3. 본문 ↔ 주석 대사", "scope": "본문 금액을 천원 환산해 주석 표에서 자동 검색",
         "findings": "주석 대응 미발견 %d건(확인필요)" % n(rows3, lambda r: r.get('verdict') == '확인필요')},
        {"item": "4. 주석 간 대사", "scope": "같은 금액이 여러 주석에 표시된 항목",
         "findings": "%d건 확인. 주석 간 판단 대사는 키 연결 후 자동 작성" % len(rows4)},
        {"item": "5. 소계·합계 검증", "scope": "본문 산식 + 주석 전 표 소계·합계·행합계·기초→기말",
         "findings": "검증 %d건 중 오류 %d건" % (len(all5), n(all5, lambda r: abs(r['shown'] - r['recalc']) > (1 if r['unit'] != '원' else 0)))},
        {"item": "6. 오탈자·표기 검토", "scope": "자동 지적사항 목록(PDF 체크본 번호와 동일)",
         "findings": "자동 등록 %d건. 오탈자·문구 검토는 키 연결 후" % len(F)},
    ]
    data = {"meta": {"company": company, "period": period, "kind": kind,
                     "footnote": "※ 자동 대사 결과(판단 문장 없음). 본문 '원', 주석 '천원'. 확인필요 사유는 수동 확인 또는 API 키 연결 시 자동 작성"},
            "summary": summary, "s1": s1, "s2": s2, "s3": s3, "s4": rows4, "s5": s5, "findings": F}
    P('엑셀·체크본 생성', 0.85)
    return data

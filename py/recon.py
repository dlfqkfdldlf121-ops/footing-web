# -*- coding: utf-8 -*-
"""기계 대사: 시트1(전기말)·시트2(전반기)·시트5(소계·합계).

시트1·2 — 비교 문서 표 자동 짝짓기
  1) 당기 표 a 와 비교 문서 표 b 의 숫자 집합 교집합으로 후보 표를 고른다.
  2) 행 라벨 정규화로 행을 맞추고, 값이 같은 칸이 가장 많은 (a열 → b열) 대응을 찾는다.
  3) 대응된 열의 모든 행을 비교한다 → 같은 값/단수차이/불일치.
시트5 — 표 안 소계·합계
  · 라벨이 합계/소계/계/총계 인 행: 직전 합계행 이후 세부행 합 / 표 처음부터 비합계행 합 중 하나와 일치하면 적정
  · 변동표(…초 → …말): 행마다 기초 + 증감 열 = 기말
"""
import json, re, itertools
from collections import Counter, defaultdict

TOTAL = re.compile(r'^(합\s*계|소\s*계|계|총\s*계|합 계)$|합계$|소계$')
ROMAN = re.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴ|Ⅵ|Ⅶ|Ⅷ|Ⅸ|Ⅹ)\s*\.')


def stitch(D):
    """머리글 없는 표(페이지 넘김 연속분)를 직전 표에 이어 붙인다."""
    out = []
    for t in D['tables']:
        if out and not any(c for c in t['cols']) and out[-1]['ncol'] == t['ncol'] \
                and t['page'] - out[-1]['page'] <= 1:
            out[-1] = dict(out[-1], rows=out[-1]['rows'] + t['rows'])
        else:
            out.append(t)
    return dict(D, tables=out)


def norm(s):
    s = s or ''
    s = re.sub(r'\(\*\d?\)|\(\*\)', '', s)
    s = re.sub(r'^[IVX]+\.\s*|^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.\s*|^\d+\.\s*', '', s)
    return re.sub(r'[\s·ㆍ,.()\-]', '', s)


def nums_of(t, minabs=100):
    out = set()
    for r in t['rows']:
        for v in r['nums'][1:]:
            if isinstance(v, (int, float)) and abs(v) >= minabs:
                out.add(v)
    return out


def row_key(t, r):
    """라벨 + (첫 칸이 비면 둘째 칸) — 회사명 열 등을 위해."""
    lab = r['cells'][0] or ''
    c1 = r['cells'][1] if len(r['cells']) > 1 else None
    if c1 and r['nums'][1] is None and c1 not in ('-',) and (not lab or lab in ('지분증권', '채무증권')):
        lab = (lab + ' ' + c1).strip()
    return norm(lab)


def col_map(a, b, xlat=None):
    """값 일치 횟수가 많은 (a열, b열) 대응. 각 a열은 하나의 b열로."""
    bk = defaultdict(list)
    for r in b['rows']:
        bk[row_key(b, r)].append(r)
    cnt = Counter()
    seen = Counter()
    for ra in a['rows']:
        k = row_key(a, ra); n = seen[k]; seen[k] += 1
        for rb in bk.get(k, [])[n:n + 1]:
            for i, va in enumerate(ra['nums']):
                if not isinstance(va, (int, float)) or va == 0 or i == 0:
                    continue
                for j, vb in enumerate(rb['nums']):
                    if vb == va:
                        cnt[(i, j)] += 1
    # 열 이름 대응 가점: 당기 보고서 '전기말' ↔ 비교 보고서 '당기말' 등
    def nm(x):
        return re.sub(r'\s|<[^>]*>', '', x or '')
    if xlat:
        for (i, j) in list(cnt):
            an = nm(a['cols'][i]) if i < len(a['cols']) else ''
            bn = nm(b['cols'][j]) if j < len(b['cols']) else ''
            if an and bn and xlat(an) == bn:
                cnt[(i, j)] += 0.5 + cnt[(i, j)]      # 이름이 맞으면 두 배 + 가점
    mp = {}
    used = set()
    for (i, j), c in cnt.most_common():
        if i in mp or j in used or c < 1:
            continue
        mp[i] = j; used.add(j)
    return mp, cnt


def compare(A, B, want_cols, period_of=None, xlat=None):
    """A 표들 중 want_cols(열 이름 포함 문자열) 열을 B 표와 대사."""
    used_b = set()
    rows_out = []
    for a in A['tables']:
        acols = [i for i, c in enumerate(a['cols']) if any(w in (c or '') for w in want_cols)
                 and not re.search(r'주\s*석', c or '')]
        if not acols:
            continue
        na = nums_of(a)
        if len(na) < 2:
            continue
        best, bs = None, 0
        for bi, b in enumerate(B['tables']):
            s = len(na & nums_of(b))
            if s > bs:
                best, bs = bi, s
        if best is None or bs < 2:
            continue
        b = B['tables'][best]
        mp, cnt = col_map(a, b, xlat)
        # 비교 대상: 원하는 열(acols) 중 대응된 열. 본문(10쪽 이하)은 열 이름으로 다시 거름
        targets = [i for i in mp if i in acols]
        targets = [i for i in targets if cnt[(i, mp[i])] >= 2 or len(a['rows']) <= 3]
        if not targets:
            continue
        bk = defaultdict(list)
        for r in b['rows']:
            bk[row_key(b, r)].append(r)
        sec = (a['note'] + ' ' + a['sub']).strip() if a['page'] > 10 else ('본문 p%d' % a['page'])
        seen = Counter()
        for ra in a['rows']:
            k = row_key(a, ra)
            if not k or k not in bk:
                continue
            n = seen[k]; seen[k] += 1
            if n >= len(bk[k]):
                continue
            rb = bk[k][n]
            for i in targets:
                va, vb = ra['nums'][i], rb['nums'][mp[i]] if mp[i] < len(rb['nums']) else None
                if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
                    continue
                if va == 0 and vb == 0:
                    continue
                rows_out.append(dict(page=a['page'], b_page=b['page'], sec=sec, unit=a['unit'] or '천원',
                                     item=(ra['cells'][0] or ra['cells'][1] or '').strip(),
                                     col=a['cols'][i], a=va, b=vb, period=period_of(a['cols'][i]) if period_of else None))
    return rows_out


def is_total(label):
    l = re.sub(r'\s', '', label or '')
    return bool(TOTAL.search(l)) or l in ('합계', '소계', '계', '총계')


def subtotal_checks(T, tol):
    """시트5: 표별 합계·소계 및 변동표 기초→기말."""
    out = []
    for t in T['tables']:
        sec = (t['note'] + ' ' + t['sub']).strip() if t['page'] > 10 else ('본문 p%d' % t['page'])
        rows = t['rows']
        ncol = t['ncol']
        # (1) 열 합계
        for j in range(1, ncol):
            seg = []          # 직전 합계 이후 세부행 값
            allv = []         # 표 처음부터 비합계행
            subs = []         # 소계행 값
            for r in rows:
                v = r['nums'][j] if j < len(r['nums']) else None
                if not isinstance(v, (int, float)):
                    continue
                if is_total(r['cells'][0]) or (len(r['cells']) > 1 and is_total(r['cells'][1])):
                    if seg and v != 0:
                        cands = [sum(seg), sum(allv), sum(subs) if subs else None]
                        ok = any(c is not None and abs(c - v) <= tol for c in cands)
                        best = min((c for c in cands if c is not None), key=lambda c: abs(c - v))
                        out.append(dict(page=t['page'], sec=sec, unit=t['unit'] or '천원',
                                        target='%s · %s' % ((r['cells'][0] or r['cells'][1] or '합계').strip(), t['cols'][j]),
                                        shown=v, recalc=best, n=len(seg), exact=ok))
                    lab0 = re.sub(r'\s', '', (r['cells'][0] or '') + (r['cells'][1] or '' if len(r['cells']) > 1 else ''))
                    if '합계' in lab0 or '총계' in lab0:
                        allv, subs = [], []      # 대분류 합계 뒤에는 새 블록
                    else:
                        subs.append(v)
                    seg = []
                else:
                    seg.append(v); allv.append(v)
        # (1b) 행 합계: '합계' 열 = 앞쪽 금액 열 합 (부문별 정보 등)
        tc = [i for i, c in enumerate(t['cols']) if re.sub(r'\s', '', c or '').endswith('합계')]
        if tc and tc[-1] == ncol - 1 and ncol >= 4:
            e = tc[-1]
            skip = {i for i, c in enumerate(t['cols']) if re.search(r'주\s*석', c or '')}
            for r in rows:
                vals = [x for i, x in enumerate(r['nums'][1:e], 1) if isinstance(x, (int, float)) and i not in skip]
                ve = r['nums'][e] if e < len(r['nums']) else None
                if not isinstance(ve, (int, float)) or len(vals) < 2 or any(isinstance(x, float) for x in vals):
                    continue
                out.append(dict(page=t['page'], sec=sec, unit=t['unit'] or '천원',
                                target='%s · 행 합계' % (r['cells'][0] or '').strip(),
                                shown=ve, recalc=sum(vals), n=len(vals), exact=abs(sum(vals) - ve) <= tol))
        # (2) 변동표: 첫 값열이 '초', 마지막 값열이 '말'
        cols = t['cols']
        idx = [i for i, c in enumerate(cols) if c]
        ci = [i for i in idx if re.search(r'(반기|기)초', cols[i] or '')]
        ce = [i for i in idx if re.search(r'(반기|기)말$', (cols[i] or '').strip())]
        if ci and ce and ci[0] < ce[-1]:
            s, e = ci[0], ce[-1]
            for r in rows:
                vs = r['nums'][s:e]
                ve = r['nums'][e] if e < len(r['nums']) else None
                if not isinstance(ve, (int, float)) or not any(isinstance(x, (int, float)) for x in vs):
                    continue
                calc = sum(x for x in vs if isinstance(x, (int, float)))
                out.append(dict(page=t['page'], sec=sec, unit=t['unit'] or '천원',
                                target='%s · %s → %s' % ((r['cells'][0] or r['cells'][1] or '').strip(), cols[s], cols[e]),
                                shown=ve, recalc=calc, n=e - s, exact=abs(calc - ve) <= tol))
    return out


if __name__ == '__main__':
    import sys
    cur = stitch(json.load(open(sys.argv[1], encoding='utf-8')))
    prev_audit = stitch(json.load(open(sys.argv[2], encoding='utf-8')))
    prev_half = stitch(json.load(open(sys.argv[3], encoding='utf-8')))
    x1 = lambda n: n.replace('제29(전)기말', '제29(당)기말').replace('전기말', '당기말')
    s1 = compare(cur, prev_audit, ['전기말', '(전)기말', '전기'], xlat=x1)
    per = lambda c: '3개월' if '3개월' in (c or '') else '누적'
    x2 = lambda n: n.replace('(전)반기', '(당)반기').replace('전반기', '당반기')
    s2 = compare(cur, prev_half, ['전반기', '(전) 반기', '(전)반기'], per, xlat=x2)
    s5 = subtotal_checks(cur, 1)
    json.dump(dict(s1=s1, s2=s2, s5=s5), open(sys.argv[4], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    for k, v in (('s1', s1), ('s2', s2)):
        d = [x for x in v if x['a'] != x['b']]
        print(k, '비교', len(v), '차이', len(d))
        for x in d[:40]:
            print('  p%d↔p%d %s | %s | %s : %s vs %s' % (x['page'], x['b_page'], x['sec'][:22], x['item'][:18], x['col'][:14], x['a'], x['b']))
    bad = [x for x in s5 if not x['exact']]
    print('s5 검증', len(s5), '불일치', len(bad))
    for x in bad[:40]:
        print('  p%d %s | %s : 표시 %s 재계산 %s' % (x['page'], x['sec'][:22], x['target'][:40], x['shown'], x['recalc']))

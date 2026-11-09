# -*- coding: utf-8 -*-
"""시트3 자동 후보: 본문 금액(원) → 천원 환산 ±1 값을 주석 표에서 검색, 위치를 '관련 주석'으로 기록.
찾지 못한 행은 '확인필요' 후보(사람/Claude 검토 대상)."""
import re
from stmt import lab, v


def note_index(D):
    idx = {}
    for t in D['tables']:
        if t['page'] <= 10:
            continue
        loc = (t['note'].split('.')[0] + (t['sub'][:3] if t['sub'] else '')).strip()
        for r in t['rows']:
            for j, x in enumerate(r['nums']):
                if isinstance(x, (int, float)) and j > 0 and abs(x) >= 1:
                    name = '주석%s %s' % (loc, (r['cells'][0] or r['cells'][1] or '').strip()[:14])
                    idx.setdefault(x, []).append((t['page'], name, t['cols'][j] if j < len(t['cols']) else ''))
    return idx


def match(D, stmt_tables):
    idx = note_index(D)
    out = []
    for fs, t, cols in stmt_tables:
        for r in t['rows']:
            L = lab(r)
            if re.match(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV)\.', L) and fs != '연결포괄손익계산서' \
                    or '총계' in L or L.endswith(':') or '항목' in L:
                continue                      # 소계·합계 행은 시트5에서 검증
            for j, when in cols:
                x = v(r, j)
                if x is None or x == 0:
                    continue
                k = round(x / 1000)
                hits = []
                for cand in (k, k - 1, k + 1, -k, -k - 1, -k + 1):
                    hits += [(h, cand) for h in idx.get(cand, [])]
                # 기간 열 이름이 맞는 히트 우선
                pref = [h for h in hits if when[:2] in (h[0][2] or '')] or hits
                item = (r['cells'][0] or '').strip()
                if pref:
                    (pg, name, col), n = pref[0]
                    refs = ' · '.join(sorted({h[0][1] for h in pref})[:3])
                    out.append(dict(fs=fs, item='%s(%s)' % (item, when), body=x, note_ref=refs,
                                    note_amt=n if (n > 0) == (x > 0) else -n, page=pg))
                else:
                    out.append(dict(fs=fs, item='%s(%s)' % (item, when), body=x, note_ref='', note_amt=None, page=None))
    return out


def stmt_tables(D):
    res = []
    for t in D['tables']:
        if t['page'] > 10:
            continue
        L = ' '.join(lab(r) for r in t['rows'][:3])
        if '유동자산' in L:
            res.append(('연결재무상태표', t, [(2, '당반기말'), (3, '당반기말')]))
        elif '매출액' in L:
            res.append(('연결포괄손익계산서', t, [(3, '당반기 누적')]))
        elif '영업활동' in L:
            res.append(('연결현금흐름표', t, [(2, '당반기'), (3, '당반기')]))
    return res

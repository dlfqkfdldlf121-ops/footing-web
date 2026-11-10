# -*- coding: utf-8 -*-
"""본문 4표 검증(시트5 본문 섹션) + 중단영업 재작성 시 전반기 계속+중단 합산 대사(시트2).
라벨 정규식으로 행을 찾는다 — K-IFRS 요약반기 재무제표의 일반 양식 기준."""
import re


ROMAN_U = {'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V', 'Ⅵ': 'VI', 'Ⅶ': 'VII', 'Ⅷ': 'VIII',
           'Ⅸ': 'IX', 'Ⅹ': 'X', 'Ⅺ': 'XI', 'Ⅻ': 'XII'}


def lab(r):
    s = re.sub(r'\s', '', r['cells'][0] or '')
    for k, v in ROMAN_U.items():          # 전각 로마숫자(Ⅱ) → 영문(II)
        s = s.replace(k, v)
    return s


def find(rows, pat, nth=0):
    hit = [r for r in rows if re.search(pat, lab(r))]
    return hit[nth] if len(hit) > nth else None


def v(r, i):
    if r is None or i >= len(r['nums']):
        return None
    x = r['nums'][i]
    return x if isinstance(x, (int, float)) else None


def tbl(D, page, ncol=None):
    for t in D['tables']:
        if t['page'] == page and (ncol is None or t['ncol'] == ncol):
            return t


def chk(out, sec, target, shown, parts, note, unit='원'):
    if shown is None or any(p is None for p in parts):
        return
    out.append(dict(gubun=sec, target=target, unit=unit, shown=shown, recalc=sum(parts), note=note))


def period_groups(t):
    """표의 금액 열을 '당기(말)'·'전기(말)' 그룹으로 나눈다. (분리된 빈 열까지 묶음)"""
    H = lambda c: re.sub(r'\s', '', c or '')
    dang, jeon = [], []
    for i, c in enumerate(t['cols']):
        h = H(c)
        if any(k in h for k in ('당기말', '당반기말', '당분기말')) or (('(당)' in h or '당' == h[:1]) and '말' in h):
            dang.append(i)
        elif any(k in h for k in ('전기말', '전기', '(전)기말')):
            jeon.append(i)
    # 못 나누면 숫자가 가장 많은 두 열을 당·전으로
    if not dang or not jeon:
        return None, None
    return dang, jeon


def amt(row, cols):
    for i in cols:
        if i < len(row['nums']) and isinstance(row['nums'][i], (int, float)):
            return row['nums'][i]
    return None


def bs_checks(t, out):
    rows = t['rows']
    dang, jeon = period_groups(t)
    if dang is None:
        return                          # 기간 열을 확신 못 하면 본문 BS 검증 건너뜀
    blocks = [k for k, r in enumerate(rows) if re.match(r'^(I|II)\.', lab(r))]
    for cols, when in ((dang, '당기말'), (jeon, '전기말')):
        for k in blocks:
            end = len(rows)
            for j in range(k + 1, len(rows)):
                lj = lab(rows[j])
                if re.match(r'^(I|II|III|IV|V)\.', lj) or '총계' in lj or lj in ('부채', '자본', '자본금'):
                    end = j; break
            det = [amt(r, cols) for r in rows[k + 1:end]
                   if amt(r, cols) is not None and '총계' not in lab(r) and '소계' not in lab(r)]
            if not det:
                continue
            chk(out, '연결재무상태표', '%s(%s)' % (rows[k]['cells'][0], when), amt(rows[k], cols), det,
                '%d개 세부항목 합산' % len(det))
        R = lambda p: find(rows, p)
        ca, nca, ta = R(r'^I\.유동자산'), R(r'^II\.비유동자산'), R(r'^자산총계')
        cl, ncl, tl = R(r'^I\.유동부채'), R(r'^II\.비유동부채'), R(r'^부채총계')
        own = R(r'지배기업의소유주지분|지배기업소유주지분')
        caps = [R(p) for p in (r'^I\.자본금', r'^II\.자본잉여금|^II\.주식발행초과금', r'^III\.기타자본|^III\.기타포괄', r'^IV\.결손금|^IV\.이익잉여금')]
        nci = R(r'^비지배지분')
        te, tle = R(r'^자본총계|^자본 ?총계'), R(r'^부채및자본총계|^부채 및 자본')
        A = lambda row: amt(row, cols) if row else None
        chk(out, '연결재무상태표', '자산총계(%s)' % when, A(ta), [A(ca), A(nca)], '유동 + 비유동')
        chk(out, '연결재무상태표', '부채총계(%s)' % when, A(tl), [A(cl), A(ncl)], '유동 + 비유동')
        if own and all(caps):
            chk(out, '연결재무상태표', '지배기업의 소유주지분(%s)' % when, A(own), [A(c) for c in caps],
                '자본금 + 자본잉여금 + 기타자본 + 결손금')
        chk(out, '연결재무상태표', '자본총계(%s)' % when, A(te), [A(own), A(nci)], '지배 + 비지배')
        chk(out, '연결재무상태표', '부채 및 자본 총계(%s)' % when, A(tle), [A(tl), A(te)], '부채총계 + 자본총계')
        chk(out, '연결재무상태표', '대차 일치(%s)' % when, A(ta), [A(tle)], '자산총계 = 부채및자본총계')


def pl_checks(t, out):
    rows = t['rows']
    R = lambda p, n=0: find(rows, p, n)
    for i, when in ((2, '당반기 3개월'), (3, '당반기 누적'), (4, '전반기 3개월'), (5, '전반기 누적')):
        s, c, gp = R(r'^I\.매출액'), R(r'^II\.매출원가'), R(r'^III\.매출총이익')
        sga, op = R(r'^IV\.판매비'), R(r'^V\.영업이익')
        oi, oe, fi, fe = R(r'^1\.기타수익'), R(r'^2\.기타비용'), R(r'^3\.금융수익'), R(r'^4\.금융비용')
        eq, pbt = R(r'^VI\.관계기업'), R(r'^VII\.법인세비용차감전')
        tax, cont = R(r'^VIII\.법인세'), R(r'^IX\.계속영업')
        disc, ni = R(r'^X\.중단영업'), R(r'^XI\.반기순')
        own, nci = R(r'^지배기업소유주지분'), R(r'^비지배지분')
        oc = R(r'^XII\.기타포괄')
        oc1, oc2 = R(r'^1\.후속적으로당기손익으로재분류되는'), R(r'^2\.후속적으로당기손익으로재분류되지')
        tci = R(r'^XIII\.총포괄')
        own2, nci2 = R(r'^지배기업소유주지분', 1), R(r'^비지배지분', 1)
        cn = lambda x: None if v(x, i) is None else -v(x, i)
        G = '연결포괄손익계산서'
        chk(out, G, 'III. 매출총이익(%s)' % when, v(gp, i), [v(s, i), cn(c)], '매출액 − 매출원가')
        chk(out, G, 'V. 영업이익(%s)' % when, v(op, i), [v(gp, i), cn(sga)], '매출총이익 − 판관비')
        chk(out, G, 'VII. 세전이익(%s)' % when, v(pbt, i),
            [v(op, i), v(oi, i), cn(oe), v(fi, i), cn(fe), v(eq, i)], '영업이익 + 기타수익 − 기타비용 + 금융수익 − 금융비용 + 관계기업손익')
        chk(out, G, 'IX. 계속영업순손익(%s)' % when, v(cont, i), [v(pbt, i), cn(tax)], '세전 − 법인세')
        chk(out, G, 'XI. 반기순손익(%s)' % when, v(ni, i), [v(cont, i), v(disc, i)], '계속 + 중단')
        chk(out, G, '반기순손익 귀속 합(%s)' % when, v(ni, i), [v(own, i), v(nci, i)], '지배 + 비지배')
        chk(out, G, 'XII. 기타포괄손익(%s)' % when, v(oc, i), [v(oc1, i), v(oc2, i)], '재분류 + 재분류불가')
        chk(out, G, 'XIII. 총포괄손익(%s)' % when, v(tci, i), [v(ni, i), v(oc, i)], '반기순손익 + 기타포괄손익')
        chk(out, G, '총포괄손익 귀속 합(%s)' % when, v(tci, i), [v(own2, i), v(nci2, i)], '지배 + 비지배')
        e, ec, ed = R(r'^1\.기본주당'), R(r'^계속영업기본주당'), R(r'^중단영업기본주당')
        if v(e, i) is not None and v(ec, i) is not None and v(ed, i) is not None:
            out.append(dict(gubun=G, target='기본주당손익 계속+중단(%s, 원)' % when, unit='원', shown=v(e, i),
                            recalc=v(ec, i) + v(ed, i), note='계속 %s + 중단 %s' % (v(ec, i), v(ed, i)),
                            tol=1))


def sce_checks(t, out):
    """연결자본변동표: 금액 열 판별 + 머리글 역할 식별로, 확실할 때만 검증(애매하면 건너뜀)."""
    rows = t['rows']; G = '연결자본변동표'; cols = t['cols']; ncol = t['ncol']
    H = lambda i: re.sub(r'\s', '', cols[i] or '') if i < len(cols) and cols[i] else ''
    # 금액 열: 숫자 셀이 충분히 많은 열(라벨·주석 열 제외)
    def numeric_count(i):
        return sum(1 for r in rows if i < len(r['nums']) and isinstance(r['nums'][i], (int, float)))
    need = max(3, len(rows) // 3)
    amt = [i for i in range(1, ncol) if numeric_count(i) >= need and '주석' not in H(i) and '주 석' not in (cols[i] or '')]
    if len(amt) < 3:
        return
    tot_i = next((i for i in reversed(amt) if '총자본' in H(i) or '총계' in H(i)
                  or (H(i).endswith('합계') and '지배' not in H(i) and '비지배' not in H(i))), amt[-1])
    nci_i = next((i for i in amt if '비지배' in H(i)), None)
    sub_i = next((i for i in amt if '지배' in H(i) and ('소계' in H(i) or '합계' in H(i))
                  and '비지배' not in H(i) and '총' not in H(i) and i != tot_i), None)
    end_comp = sub_i if sub_i is not None else (nci_i if nci_i is not None else tot_i)
    comp = [i for i in amt if i < end_comp and i not in (sub_i, nci_i, tot_i)]

    def g(nums, i):
        x = nums[i] if (i is not None and i < len(nums)) else None
        return x if isinstance(x, (int, float)) else None

    if comp and (sub_i is not None or (nci_i is not None and tot_i is not None)):
        for r in rows:
            nums = r['nums']
            cs = [g(nums, i) for i in comp]
            if sub_i is not None and g(nums, sub_i) is not None and cs and all(c is not None for c in cs):
                chk(out, G, '%s 지배기업 소계' % (r['cells'][0] or '').strip(), g(nums, sub_i), cs, '성분 합')
            if tot_i is not None and g(nums, tot_i) is not None:
                base = ([g(nums, sub_i)] if sub_i is not None else cs) + ([g(nums, nci_i)] if nci_i is not None else [])
                if len(base) >= 2 and all(b is not None for b in base):
                    chk(out, G, '%s 총계' % (r['cells'][0] or '').strip(), g(nums, tot_i), base,
                        ('지배 소계' if sub_i is not None else '성분 합') + (' + 비지배' if nci_i is not None else ''))
    # 열 방향: 기초 + 변동 = 기말
    starts = [k for k, r in enumerate(rows) if re.search(r'반기초|분기초|기초\)', lab(r))]
    for st in starts:
        e = next((k for k in range(st + 1, len(rows)) if re.search(r'반기말|분기말|기말\)', lab(rows[k]))), None)
        if e is None:
            continue
        for j in amt:
            parts = [v(rows[k], j) for k in range(st, e) if v(rows[k], j) is not None]
            if len(parts) < 2:
                continue
            chk(out, G, '%s %s 열' % ((rows[e]['cells'][0] or '').strip(), (cols[j] or '').replace('지배기업 소유주 ', '')),
                v(rows[e], j), parts, '기초 + %d개 변동' % (len(parts) - 1))


def cf_checks(t, out):
    rows = t['rows']
    G = '연결현금흐름표'
    heads = [k for k, r in enumerate(rows) if re.match(r'^(I|II|III)\.', lab(r))]
    for cur, tot, when in ((2, 3, '당반기'), (4, 5, '전반기')):
        for k in heads:
            end = next((j for j in range(k + 1, len(rows)) if re.match(r'^(I|II|III|IV|V)\.', lab(rows[j]))), len(rows))
            det = [v(r, cur) for r in rows[k + 1:end] if v(r, cur) is not None]
            chk(out, G, '%s(%s)' % (rows[k]['cells'][0], when), v(rows[k], tot), det, '%d개 항목 합산' % len(det))
        R = lambda p: find(rows, p)
        a, b, c, d = R(r'^I\.영업'), R(r'^II\.투자'), R(r'^III\.재무'), R(r'^IV\.현금')
        inc, beg, oth, end = R(r'^V\.현금'), R(r'^VI\.기초'), R(r'^VII\.'), R(r'^VIII\.기말|^VII\.기말')
        chk(out, G, 'V. 현금증감(%s)' % when, v(inc, tot), [v(a, tot), v(b, tot), v(c, tot), v(d, tot)], 'Ⅰ+Ⅱ+Ⅲ+Ⅳ')
        parts = [v(beg, tot), v(inc, tot)] + ([v(oth, tot)] if oth is not None and oth is not end else [])
        chk(out, G, '기말 현금(%s)' % when, v(end, tot), parts, '기초 + 증감' + (' + 매각예정 대체' if len(parts) == 3 else ''))


def statement_checks(D):
    out = []
    for t in D['tables']:
        L = ' '.join(lab(r) for r in t['rows'][:3])
        if t['page'] > 12:
            continue
        if '유동자산' in L:
            bs_checks(t, out)
        elif '매출액' in L:
            pl_checks(t, out)
        elif '전반기초' in L or '기초' in L and t['ncol'] >= 9:
            sce_checks(t, out)
        elif '영업활동' in L:
            cf_checks(t, out)
    return out


def restated_pl(cur, prev_half):
    """FY26 전반기(계속) + 주석 중단영업 전반기 ↔ FY25 반기 본문 (천원 비교)."""
    def find_pl(D):
        return next((t for t in D['tables'] if t['page'] <= 10
                     and any(k in ' '.join(lab(r) for r in t['rows'][:3]) for k in ('매출액', '영업수익'))), None)
    pl = find_pl(cur)
    disc = next((t for t in cur['tables'] if '중단영업' in t['note'] and '(1)' in t['sub']), None)
    old = find_pl(prev_half)
    if disc is None or pl is None or old is None:
        return []
    m = [  # (FY26 본문, 중단 주석, FY25 본문, 표시명, 부호: 중단 주석이 비용을 음수로 표시하면 -1)
        (r'^I\.매출액', r'^매출액', r'^I\.매출액', 'Ⅰ. 매출액(계속+중단)', 1),
        (r'^II\.매출원가', r'^매출원가', r'^II\.매출원가', 'Ⅱ. 매출원가(계속+중단)', -1),
        (r'^IV\.판매비', r'^판매비', r'^IV\.판매비', 'Ⅳ. 판매비와관리비(계속+중단)', -1),
        (r'^V\.영업이익', r'^영업이익', r'^V\.영업이익', 'Ⅴ. 영업이익(계속+중단)', 1),
        (r'^1\.기타수익', r'^기타영업외수익', r'^1\.기타수익', '기타수익(계속+중단)', 1),
        (r'^2\.기타비용', r'^기타영업외비용', r'^2\.기타비용', '기타비용(계속+중단)', -1),
        (r'^3\.금융수익', r'^금융수익', r'^3\.금융수익', '금융수익(계속+중단)', 1),
        (r'^4\.금융비용', r'^금융비용', r'^4\.금융비용', '금융비용(계속+중단)', -1),
        (r'^VI\.관계기업', r'^지분법손익', r'^VI\.관계기업', '관계기업 등 투자손익(계속+중단)', 1),
        (r'^VII\.법인세비용차감전', r'^법인세비용차감전', r'^VII\.법인세비용차감전', '법인세비용차감전손익(계속+중단)', 1),
        (r'^VIII\.법인세', r'^법인세수익', r'^VIII\.법인세', '법인세비용(계속+중단)', -1),
    ]
    out = []
    for p26, pd, p25, name, sg in m:
        a, d, b = find(pl['rows'], p26), find(disc['rows'], pd), find(old['rows'], p25)
        for i26, idd, i25, per in ((4, 3, 2, '3개월'), (5, 4, 3, '누적')):
            x, y, z = v(a, i26), v(d, idd), v(b, i25)
            if None in (x, y, z):
                continue
            total = round(x / 1000) + sg * y       # 천원
            out.append(dict(gubun='연결포괄손익계산서', item=name, period=per, unit='천원', a=total, b=round(z / 1000),
                            note='FY26 계속 %s + 중단 %s천원. FY25 본문 %s원' % (format(round(x / 1000), ','),
                                                                         format(sg * y, ','), format(z, ','))))
    return out

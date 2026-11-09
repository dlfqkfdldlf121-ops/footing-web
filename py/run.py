# -*- coding: utf-8 -*-
"""검토결과 JSON 1개 → 엑셀 + 체크본 PDF 2개. 지적사항 목록(findings)이 엑셀 시트6과 PDF의 단일 원천."""
import json, os, sys, tempfile
import gen_excel, pdf_check

LV = {'상': 'E', '중': 'W', '하': 'L'}


def run(data, src_pdf, out_dir, stem):
    os.makedirs(out_dir, exist_ok=True)
    audit = gen_excel.self_audit(data)
    if audit:                      # 웹 버전: 이 목록을 Claude에 돌려보내 판정·비고 수정 요청
        raise ValueError('판정-차이 모순 %d건: %s' % (len(audit), audit))
    xlsx = os.path.join(out_dir, stem + '_검토결과.xlsx')
    findings = gen_excel.build(data, xlsx)
    import pymupdf
    src = pymupdf.open(src_pdf)
    for f in findings:
        if f.get('pdf') and not f['pdf'].get('page'):
            hits = [i + 1 for i, pg in enumerate(src) if all(pg.search_for(x) for x in f['pdf']['find'])] or \
                   [i + 1 for i, pg in enumerate(src) if pg.search_for(f['pdf']['find'][0])]
            f['pdf']['page'] = hits[-1] if hits else 1   # 주석 쪽(뒤쪽) 우선
    src.close()
    spec = [dict(no=f['no'], page=f['pdf']['page'], lv=LV[f['sev']], find=f['pdf']['find'],
                 t=f['pdf'].get('t') or f['loc'], n=f['pdf'].get('n') or f['fix'])
            for f in findings if f.get('pdf')]
    tmp = tempfile.mkdtemp()
    pdf_check.FR, pdf_check.FB = os.path.join(tmp, 'R.ttf'), os.path.join(tmp, 'B.ttf')
    chars = set('검토 지적사항') | set(pdf_check.CIRC) | set(''.join(pdf_check.LVNM.values()))
    for it in spec:
        chars |= set(it['t']) | set(it['n'])
    pdf_check.make_subset(chars)
    base = os.path.splitext(os.path.basename(src_pdf))[0]
    full = os.path.join(out_dir, base + '_체크.pdf')
    only = os.path.join(out_dir, base + '_체크페이지만.pdf')
    pages, misses = pdf_check.build(src_pdf, spec, full, only, data['meta'].get('kind', ''))
    return xlsx, full, only, pages, misses


if __name__ == '__main__':
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    x, f, o, pages, misses = run(d, sys.argv[2], sys.argv[3], sys.argv[4])
    print('엑셀', x); print('체크본', f, '/ 발췌', o, '체크페이지', pages)
    for m in misses:
        print('MISS', m)

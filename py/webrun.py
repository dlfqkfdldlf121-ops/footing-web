# -*- coding: utf-8 -*-
"""브라우저(Pyodide)용 진입점: worker.js 가 go() 를 호출한다."""
import json, os, shutil
import pdf_check
pdf_check.NOTO_R = '/app/fonts/NotoKR-R.otf'     # 한글 전용 서브셋 폰트(웹 동봉)
pdf_check.NOTO_B = '/app/fonts/NotoKR-B.otf'
import auto, run


def go(cur, aud, half, company, period, kind, progress):
    p = lambda m, x: progress(m, x)
    data = auto.analyze(cur, aud, half, company=company, period=period, kind=kind, progress=p)
    stem = '%s_%s%s%s검토보고서' % (company or '회사', period or '', data.get('pw', '반기'), '연결' if kind == '연결' else '(별도)')
    out = '/out'
    shutil.rmtree(out, ignore_errors=True)
    xlsx, full, only, pages, misses = run.run(data, cur, out, stem)
    p('완료', 1.0)
    return json.dumps({
        'summary': data['summary'],
        'findings': [{'no': f['no'], 'sev': f['sev'], 'loc': f['loc'], 'type': f['type'], 'current': f['current'],
                      'page': f['pdf'].get('page')} for f in data['findings']],
        'pages': pages, 'misses': len(misses), 'errors': data.get('errors', []),
        'files': {'xlsx': xlsx, 'full': full, 'only': only},
    }, ensure_ascii=False)

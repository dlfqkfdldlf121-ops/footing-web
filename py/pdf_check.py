# -*- coding: utf-8 -*-
"""원본 PDF에 검토 지적사항을 색상 하이라이트 + 여백 주석으로 표시하고,
   (1) 전체 페이지 체크본 (2) 체크된 페이지만 발췌본 을 생성한다.

사용법
  1) spec_c.py / spec_s.py 처럼 지적사항 목록 파일을 만든다.
     SPEC = [ dict(page=63,            # 원본 PDF 페이지 (1-based)
                   lv='E',             # E=오류(빨강) W=확인필요(파랑) L=표기(회색)
                   find=['(2,090,393)', '(1,170,504)'],   # PDF에서 찾을 문자열들
                   t='주석30(2) 전반기 부문별 순손익 배분 오류',   # 여백 제목
                   n='본문 계속영업 (1,456,717)천원과 633,676천원 상충 …'),  # 사유
              ... ]
     · find 문자열은 먼저 아래 명령으로 실제 검색되는지 확인할 것
         python3 -c "import pymupdf,sys; d=pymupdf.open(sys.argv[1]); \
           print([(i+1,len(p.search_for(sys.argv[2]))) for i,p in enumerate(d) if p.search_for(sys.argv[2])])" 원본.pdf "찾을문자열"
     · 줄바꿈으로 끊기면 더 짧은 조각이나 인접 제목(예: '28. 재무위험관리')으로 대체
  2) 아래 __main__ 의 jobs 목록에 (원본, SPEC, 출력2개, 라벨) 을 넣고 실행
  3) MISS 가 찍히면 그 문자열을 못 찾은 것이므로 spec 을 고친다
"""
import pymupdf, sys, os

STRIP = 240.0          # 오른쪽에 덧붙일 여백 폭
FR = os.environ.get('FOOT_FR', '/tmp/sub_R.ttf')
FB = os.environ.get('FOOT_FB', '/tmp/sub_B.ttf')


NOTO_R = '/tmp/NotoKR.ttf'
NOTO_B = '/tmp/NotoKR-Bold.ttf'


def ensure_noto():
    """NotoSansCJK TTC에서 한국어(index 1) 폰트를 TTF로 추출한다."""
    from fontTools.ttLib import TTCollection
    src = {'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc': NOTO_R,
           '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc': NOTO_B}
    for ttc, out in src.items():
        if not os.path.exists(out):
            TTCollection(ttc).fonts[1].save(out)   # index 1 = Noto Sans CJK KR


def make_subset(chars):
    """주석에 쓰이는 글자만 남긴 경량 폰트를 만든다 (CJK 원본은 16MB)."""
    from fontTools import subset
    ensure_noto()
    for src_ttf, out in ((NOTO_R, FR), (NOTO_B, FB)):
        opt = subset.Options()
        opt.layout_features = ['*']
        opt.notdef_outline = True
        opt.retain_gids = True      # 글리프 ID 유지 — 안 하면 한글이 깨짐
        opt.drop_tables += ['DSIG']
        f = subset.load_font(src_ttf, opt)
        s = subset.Subsetter(options=opt)
        s.populate(text=''.join(sorted(chars)))
        s.subset(f)
        subset.save_font(f, out, opt)
        f.close()
    print('  subset font: %.0fKB / %.0fKB'
          % (os.path.getsize(FR) / 1024, os.path.getsize(FB) / 1024))
RED   = (0.78, 0.05, 0.05)
BLUE  = (0.04, 0.30, 0.76)
GRAY  = (0.38, 0.38, 0.38)
COL   = {'E': RED, 'W': BLUE, 'L': GRAY}
LVNM  = {'E': '오류', 'W': '확인필요', 'L': '표기'}
CIRC  = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵'


def tbox(page, rect, text, font, size, color, align=0):
    """텍스트를 넣고 실제 사용 높이를 돌려준다. 넘치면 크기를 줄여 재시도."""
    for s in (size, size - 0.4, size - 0.8, size - 1.2):
        rc = page.insert_textbox(rect, text, fontname=font, fontsize=s,
                                 color=color, align=align, lineheight=1.28)
        if rc >= 0:
            return rect.height - rc
        page.insert_textbox(rect, '', fontname=font, fontsize=s)  # no-op
    page.insert_textbox(rect, text, fontname=font, fontsize=size - 1.2,
                        color=color, align=align, lineheight=1.22)
    return rect.height


def measure(text, font_file, size, width, lh=1.28):
    """textbox 없이 높이를 추정 (임시 페이지에 시뮬레이션)."""
    d = pymupdf.open(); p = d.new_page(width=width + 20, height=2000)
    p.insert_font(fontname='M', fontfile=font_file)
    r = pymupdf.Rect(0, 0, width, 1900)
    rc = p.insert_textbox(r, text, fontname='M', fontsize=size, lineheight=lh)
    h = 1900 - rc if rc >= 0 else 1900
    d.close()
    return h


def build(src_path, spec, out_full, out_only, doc_title):
    src = pymupdf.open(src_path)
    # 페이지별 지적사항 묶기 (번호는 전체 통산)
    bypage = {}
    for i, item in enumerate(spec):
        bypage.setdefault(item['page'], []).append((i, item))

    dst = pymupdf.open()
    marked_pages = []
    misses = []

    for pno in range(len(src)):
        sp = src[pno]
        r = sp.rect
        np_ = dst.new_page(width=r.width + STRIP, height=r.height)
        np_.show_pdf_page(pymupdf.Rect(0, 0, r.width, r.height), src, pno)

        items = bypage.get(pno + 1)
        if not items:
            continue
        marked_pages.append(pno + 1)
        np_.insert_font(fontname='ZzChkR', fontfile=FR)
        np_.insert_font(fontname='ZzChkB', fontfile=FB)

        # 여백 배경 + 구분선
        np_.draw_rect(pymupdf.Rect(r.width, 0, r.width + STRIP, r.height),
                      color=None, fill=(0.975, 0.977, 0.982), overlay=True)
        np_.draw_line(pymupdf.Point(r.width, 0), pymupdf.Point(r.width, r.height),
                      color=(0.7, 0.7, 0.7), width=0.7)

        x0 = r.width + 11
        W = STRIP - 22

        # ── 범례
        np_.insert_textbox(pymupdf.Rect(x0, 12, x0 + W, 26), '검토 지적사항',
                           fontname='ZzChkB', fontsize=8, color=(0.15, 0.15, 0.15))
        lx = x0
        for lv in ('E', 'W', 'L'):
            np_.draw_rect(pymupdf.Rect(lx, 26.5, lx + 6, 32.5), color=None, fill=COL[lv])
            np_.insert_textbox(pymupdf.Rect(lx + 8, 24.8, lx + 8 + 46, 40), LVNM[lv],
                               fontname='ZzChkR', fontsize=6.6, color=COL[lv])
            lx += 8 + (len(LVNM[lv]) * 6.6) + 8
        np_.draw_line(pymupdf.Point(x0, 37), pymupdf.Point(x0 + W, 37),
                      color=(0.78, 0.78, 0.78), width=0.5)
        y = 44

        for idx, it in items:
            c = COL[it['lv']]
            k = it.get('no', idx + 1) - 1     # 엑셀 시트6 No와 동일 번호
            num = CIRC[k] if k < len(CIRC) else '(%d)' % (k + 1)

            # ── 본문 하이라이트 (형광 + 테두리)
            anchor = None
            for needle in it['find']:
                rects = sp.search_for(needle)
                if not rects:
                    misses.append((doc_title, pno + 1, needle))
                    continue
                for q in rects:
                    box = pymupdf.Rect(q.x0 - 1.4, q.y0 - 1.4, q.x1 + 1.4, q.y1 + 1.4)
                    sh = np_.new_shape()
                    sh.draw_rect(box)
                    sh.finish(color=None, fill=c, fill_opacity=0.22)
                    sh.commit(overlay=True)
                    sh = np_.new_shape()
                    sh.draw_rect(box)
                    sh.finish(color=c, width=1.0, fill=None)
                    sh.commit(overlay=True)
                    if anchor is None:
                        anchor = box

            # ── 여백 주석 블록 높이 계산
            th = measure(it['t'], FB, 7.2, W - 13)
            bh = measure(it['n'], FR, 6.4, W - 13)
            blk = th + bh + 9
            if y + blk > r.height - 22:
                y = max(44, r.height - 22 - blk)

            np_.draw_rect(pymupdf.Rect(x0 - 4, y - 2, x0 - 1.8, y - 2 + blk),
                          color=None, fill=c)
            np_.insert_textbox(pymupdf.Rect(x0 + 0.5, y - 1.2, x0 + 16, y + 16), num,
                               fontname='ZzChkR', fontsize=8, color=c)
            np_.insert_textbox(pymupdf.Rect(x0 + 13, y, x0 + W, y + th + 4), it['t'],
                               fontname='ZzChkB', fontsize=7.2, color=c, lineheight=1.28)
            np_.insert_textbox(pymupdf.Rect(x0 + 13, y + th + 2.5, x0 + W, y + th + bh + 7), it['n'],
                               fontname='ZzChkR', fontsize=6.4, color=(0.25, 0.25, 0.25), lineheight=1.28)

            # ── 본문 배지 + 지시선
            if anchor is not None:
                bx = min(anchor.x1 + 2.5, r.width - 13)
                np_.draw_circle(pymupdf.Point(bx + 4, anchor.y0 + anchor.height / 2), 4.6,
                                color=None, fill=c)
                cy = anchor.y0 + anchor.height / 2
                np_.insert_textbox(pymupdf.Rect(bx - 2, cy - 6, bx + 10, cy + 6.5),
                                   num, fontname='ZzChkR', fontsize=6.8, color=(1, 1, 1), align=1)
                np_.draw_line(pymupdf.Point(bx + 9.5, anchor.y0 + anchor.height / 2),
                              pymupdf.Point(x0 - 5, y + 5),
                              color=c, width=0.5, dashes='[1.2 2] 0')
            y += blk + 6

    dst.save(out_full, garbage=4, deflate=True, clean=True)

    # 발췌본은 이미 서브셋된 전체본에서 뽑는다
    full = pymupdf.open(out_full)
    only = pymupdf.open()
    for p in marked_pages:
        only.insert_pdf(full, from_page=p - 1, to_page=p - 1)
    only.save(out_only, garbage=4, deflate=True, clean=True)
    only.close(); full.close(); dst.close(); src.close()
    return marked_pages, misses


if __name__ == '__main__':
    import spec_c, spec_s
    B = '/sessions/jolly-vigilant-albattani/mnt/00. 풋팅/'
    O = '/tmp/out/'

    chars = set('검토 지적사항') | set(CIRC) | set(''.join(LVNM.values()))
    for sp in (spec_c.SPEC, spec_s.SPEC):
        for it in sp:
            chars |= set(it['t']) | set(it['n'])
    make_subset(chars)
    jobs = [
        (B + '00. FY26_케이바이오_반기연결검토보고서.pdf', spec_c.SPEC,
         O + '00. FY26_케이바이오_반기연결검토보고서_체크.pdf',
         O + '00. FY26_케이바이오_반기연결검토보고서_체크페이지만.pdf', '연결'),
        (B + '01. FY26_케이바이오_별도보고서.pdf', spec_s.SPEC,
         O + '01. FY26_케이바이오_별도보고서_체크.pdf',
         O + '01. FY26_케이바이오_별도보고서_체크페이지만.pdf', '별도'),
    ]
    for src, spec, of, oo, t in jobs:
        pages, misses = build(src, spec, of, oo, t)
        ne = sum(1 for x in spec if x['lv'] == 'E')
        nw = sum(1 for x in spec if x['lv'] == 'W')
        nl = sum(1 for x in spec if x['lv'] == 'L')
        print('%s: 지적 %d건(오류 %d/확인 %d/표기 %d) · 체크 페이지 %d개 %s'
              % (t, len(spec), ne, nw, nl, len(pages), pages))
        for m in misses:
            print('   MISS', m)

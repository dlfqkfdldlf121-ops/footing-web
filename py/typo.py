# -*- coding: utf-8 -*-
"""규칙 기반 표기 검토(오프라인, AI 불필요).
PDF 추출은 줄바꿈이 많아 공백 기반 규칙은 거짓양성이 크다 → '진짜 공백' 또는 '확정 오타 문자열'만 잡는다.
개행은 공백으로 바꾸지 않는다(줄바꿈을 공백으로 오인하지 않기 위함)."""
import re

# 1) 확정 오타 문자열(공백 무관) — 매우 안전
EXACT = [
    ('하였니다', '오탈자', "'하였습니다'"),
    ('되었니다', '오탈자', "'되었습니다'"),
    ('하였슴니다', '오탈자', "'하였습니다'"),
    ('되었슴니다', '오탈자', "'되었습니다'"),
    ('습니니다', '오탈자', "'습니다'"),
    ('됩니니다', '오탈자', "'됩니다'"),
    ('있니다', '오탈자', "'있습니다'"),
]
# 2) 한 줄 안의 진짜 공백 패턴만(개행 제외). 각 줄 단위로 검사.
LINE_RULES = [
    (re.compile(r'[를을] 이상을'), '조사 중복', "'% 이상을'로 정정 (10%를 이상을 → 10% 이상을)"),
    (re.compile(r'[이가] 이상이 '), '조사 중복', '조사 중복 확인'),
    (re.compile(r'\(구,[^\s)]'), '쉼표 뒤 공백 누락', "쉼표 뒤 공백 (구,주식회사 → 구, 주식회사)"),
    (re.compile(r'재작성 되었습니다'), '띄어쓰기', "'재작성되었습니다'"),
    (re.compile(r'표시 하였습니다'), '띄어쓰기', "'표시하였습니다'"),
]


def scan(pages):
    out = []
    for pno, text in enumerate(pages, 1):
        for sub, typ, desc in EXACT:
            if sub in text.replace('\n', ''):
                out.append((pno, typ, sub, desc))
        for line in text.split('\n'):
            ln = re.sub(r'[ \t]+', ' ', line)
            for rx, typ, desc in LINE_RULES:
                m = rx.search(ln)
                if m:
                    out.append((pno, typ, m.group(0).strip(), desc))
    seen = set(); uniq = []
    for r in out:
        k = (r[1], r[2])
        if k not in seen:
            seen.add(k); uniq.append(r)
    return uniq

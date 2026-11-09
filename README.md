# 반기검토보고서 교차대사 (브라우저 전용)

https://dlfqkfdldlf121-ops.github.io/footing-web/

PDF 3개(당기 반기검토보고서 · 전기 감사보고서 · 전년 반기검토보고서)를 선택하면
검토결과 엑셀(7개 시트)과 체크본 PDF를 만든다.

- 모든 처리는 사용자 PC의 브라우저 안(Pyodide)에서 이뤄진다. 파일은 서버로 전송되지 않는다.
- 저장소에는 프로그램만 있고 보고서·데이터는 없다.
- 구성: `index.html`(화면), `worker.js`(계산 스레드), `py/`(대사 엔진), `wheels/`(PyMuPDF·openpyxl), `fonts/`(한글 폰트 서브셋 — Noto Sans CJK, SIL OFL)

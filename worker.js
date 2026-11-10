// 계산 전용 작업 스레드: Pyodide(브라우저 안 파이썬)로 대사 엔진을 실행한다. 네트워크로 파일을 보내지 않는다.
importScripts('https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js');

const PY_FILES = ['extract.py', 'recon.py', 'stmt.py', 'body_note.py', 'gen_excel.py', 'pdf_check.py', 'run.py', 'auto.py', 'webrun.py'];
const WHEELS = ['wheels/pymupdf-1.28.2-cp313-abi3-pyodide_2025_0_wasm32.whl',
                'wheels/et_xmlfile-2.0.0-py3-none-any.whl', 'wheels/openpyxl-3.1.5-py2.py3-none-any.whl'];
const FONTS = ['fonts/NotoKR-R.otf', 'fonts/NotoKR-B.otf'];
const base = self.location.href.replace(/[^/]*$/, '');
const say = (type, payload) => self.postMessage(Object.assign({ type }, payload));

let ready = (async () => {
  say('status', { msg: '엔진 불러오는 중 (처음 한 번 30초 내외)', p: 0.02 });
  const py = await loadPyodide();
  await py.loadPackage(['fonttools'].concat(WHEELS.map(w => base + w)), { checkIntegrity: false });
  py.FS.mkdirTree('/app/py'); py.FS.mkdirTree('/app/fonts');
  for (const f of PY_FILES) py.FS.writeFile('/app/py/' + f, await (await fetch(base + 'py/' + f)).text());
  for (const f of FONTS) py.FS.writeFile('/app/' + f, new Uint8Array(await (await fetch(base + f)).arrayBuffer()));
  await py.runPythonAsync("import sys; sys.path.insert(0, '/app/py'); import webrun");
  say('ready', {});
  return py;
})();

self.onmessage = async (ev) => {
  const py = await ready;
  const { files, company, period, kind } = ev.data;
  try {
    py.FS.mkdirTree('/in');
    const names = [];
    for (const [i, f] of files.entries()) {
      const p = '/in/' + (i === 0 ? f.name : ['cur', 'aud', 'half'][i] + '.pdf');
      py.FS.writeFile(p, new Uint8Array(f.buf));
      names.push(p);
    }
    const prog = (m, x) => say('status', { msg: m, p: x });
    const res = JSON.parse(await py.pyimport('webrun').go(names[0], names[1], names[2], company, period, kind, prog));
    if (res.error) { say('error', { msg: res.error + '\n\n' + (res.traceback || '') }); return; }
    const out = {};
    for (const k of ['xlsx', 'full', 'only']) {
      out[k] = { name: res.files[k].split('/').pop(), data: py.FS.readFile(res.files[k]) };
    }
    say('done', { res, out });
  } catch (e) {
    say('error', { msg: String(e).slice(-1500) });
  }
};

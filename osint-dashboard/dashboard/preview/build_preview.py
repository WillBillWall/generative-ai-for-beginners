#!/usr/bin/env python3
"""Build preview.html: a standalone local preview of ../index.html.

The dashboard page is not standalone: in production a host page injects it into
<div id="dash-root">, with a global `d3` (v7), a global `dash` object and host CSS
variables. This script writes a page that fakes all three and embeds the data
from ../../data/processed/, so the dashboard can be opened and screenshotted
locally. It only READS index.html (re-read on every build) and never writes it.

Usage: python3 build_preview.py      (then: node shoot.js)
"""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE.parent / "index.html"
DATA = HERE.parent.parent / "data" / "processed"
OUT = HERE / "preview.html"
D3_LOCAL = HERE / "d3.min.js"          # optional offline copy (npm pack d3@7.9.0)
D3_CDN = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"

# Values copied from the host stylesheet (app.css); light first, dark second.
HOST_CSS = """
:root {
  color-scheme: light;
  --color-fg: rgb(0 0 0 / 0.9);
  --color-fg-muted: rgb(0 0 0 / 0.6);
  --color-bg: #fcfcfb;
  --color-panel: #ffffff;
  --color-border-line: rgb(0 0 0 / 0.1);
  --color-ok: #006c10;
  --color-warn: #794c02;
  --color-bad: #a42528;
  --font-anthropic-sans: "Anthropic Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-anthropic-serif: "Anthropic Serif", ui-serif, Georgia, "Times New Roman", serif;
  --cds-font-size-caption: .75rem;
  --cds-font-size-body: .875rem;
  --cds-font-size-heading: .9375rem;
  --cds-font-size-title: 1.375rem;
  --cds-font-weight-medium: 500;
  --cds-gap-xs: .375rem; --cds-gap-sm: .5rem; --cds-gap-md: .75rem; --cds-gap-lg: 1.25rem; --cds-gap-xl: 2rem;
  --cds-pad-xs: .25rem; --cds-pad-sm: .5rem; --cds-pad-md: .75rem; --cds-pad-lg: 1rem; --cds-pad-xl: 1.5rem;
  --cds-radius: .5rem;
  --cds-chart-muted: #c3c2b7;
  --cds-chart-grid: rgb(11 11 11 / 0.1);
  --cds-chart-axis: #c3c2b7;
  --cds-chart-reference: #898781;
  --cds-chart-status-critical: #d03b3b;
  --cds-surface-popover: #ffffff;
  --cds-border: rgb(0 0 0 / 0.08);
  --cds-shadow-popover: 0 8px 24px #0000001f, 0 2px 6px #00000014;
  --cds-text-secondary: rgb(0 0 0 / 0.6);
  --cds-dur-slow: .45s;
  --cds-ease-out: cubic-bezier(.165, .84, .44, 1);
  --cds-chart-categorical-1: #2a78d6;
  --cds-chart-categorical-2: #eb6834;
  --cds-chart-categorical-3: #1baf7a;
  --cds-chart-categorical-4: #eda100;
  --cds-chart-categorical-5: #e87ba4;
  --cds-chart-categorical-6: #008300;
  --cds-chart-categorical-7: #6250d6;
  --cds-chart-categorical-8: #e34948;
}
:root[data-theme=dark] {
  color-scheme: dark;
  --color-fg: rgb(255 255 255 / 0.93);
  --color-fg-muted: rgb(255 255 255 / 0.57);
  --color-bg: #151515;
  --color-panel: #1f1f1f;
  --color-border-line: rgb(255 255 255 / 0.1);
  --color-ok: #53c556;
  --color-warn: #e49c06;
  --color-bad: #f17778;
  --cds-chart-muted: #5f5e5a;
  --cds-chart-grid: rgb(255 255 255 / 0.1);
  --cds-chart-axis: #383835;
  --cds-chart-reference: #97958d;
  --cds-surface-popover: #303030;
  --cds-border: rgb(255 255 255 / 0.04);
  --cds-shadow-popover: 0 8px 24px #00000052, 0 2px 6px #0003;
  --cds-text-secondary: rgb(255 255 255 / 0.57);
  --cds-chart-categorical-1: #3987e5;
  --cds-chart-categorical-2: #d95926;
  --cds-chart-categorical-3: #199e70;
  --cds-chart-categorical-4: #c98500;
  --cds-chart-categorical-5: #d55181;
  --cds-chart-categorical-6: #008300;
  --cds-chart-categorical-7: #9085e9;
  --cds-chart-categorical-8: #e66767;
}
html, body { margin: 0; background: var(--color-bg); }
#dash-root { color: var(--color-fg); font-size: 14px; line-height: 1.45; font-family: var(--font-anthropic-sans);
  padding: clamp(var(--cds-pad-md), 4%, var(--cds-pad-xl)); }
#dash-root a[href] { text-underline-offset: .15em; text-decoration: underline; }
"""

MOCK_DASH = r"""
(function () {
  // theme: preview.html?theme=dark (default) or ?theme=light
  const theme = new URLSearchParams(location.search).get('theme') || 'dark';
  document.documentElement.dataset.theme = theme;

  const RAW = JSON.parse(document.getElementById('preview-data').textContent);
  const calcs = {}, drawings = {}, cache = {};
  let ready = false;
  const noop = () => {};

  function data(id) {
    if (calcs[id]) {
      if (!(id in cache)) {
        const c = calcs[id];
        cache[id] = c.fn(...c.inputs.map((i) => data(i).data));
      }
      const rows = cache[id] || [];
      return { status: 'ok', data: rows, columns: rows.length ? Object.keys(rows[0]) : [] };
    }
    if (RAW[id]) return { status: 'ok', data: RAW[id].rows, columns: RAW[id].columns };
    return { status: 'missing', data: [] };
  }

  function run(name) {
    const fn = drawings[name];
    if (!fn) return;
    for (const el of document.querySelectorAll('[data-draw="' + name + '"]')) {
      if (el.closest('[hidden]')) continue;
      try { fn(el); } catch (e) { console.error('[preview] drawing "' + name + '" threw: ' + (e && e.stack || e)); }
    }
  }
  function runAll() { for (const name of Object.keys(drawings)) run(name); }

  window.dash = {
    data,
    calc(id, spec) { calcs[id] = spec; delete cache[id]; },
    draw(name, fn) {
      if (fn === undefined) { run(name); return; }
      drawings[name] = typeof fn === 'function' ? fn : (el) => { const made = fn.mount && fn.mount(el); if (fn.update) fn.update(el, made); };
      if (ready) run(name);
    },
    colors: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => 'var(--cds-chart-categorical-' + i + ')'),
    onData(fn) { fn(); },
    params() { return {}; },
    setParams: noop, resetParams: noop, setLink: noop, refresh: noop, loader: noop,
  };

  // Called by the last inline script, after every dashboard script has run.
  window.__previewStart = function () {
    ready = true;
    runAll();
    // report data-draw names that no script registered
    const names = new Set([...document.querySelectorAll('[data-draw]')].map((e) => e.dataset.draw));
    for (const n of names) if (!drawings[n]) console.error('[preview] data-draw="' + n + '" has no dash.draw registration');
    let timer = null;
    window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(runAll, 60); });
    document.documentElement.dataset.previewReady = '1';
  };
})();
"""


def load_data():
    """Every data file as {id: {columns, rows}}. CSV cells stay strings, as in production."""
    out = {}
    for p in sorted(DATA.iterdir()):
        if p.suffix == ".csv":
            with p.open(newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                cols = next(reader, [])
                rows = [{c: (row[i] if i < len(row) else "") for i, c in enumerate(cols)} for row in reader if row]
            out[p.stem] = {"columns": cols, "rows": rows}
        elif p.suffix == ".json":
            rows = json.loads(p.read_text(encoding="utf-8"))
            cols = []
            for r in rows:
                for k in r:
                    if k not in cols:
                        cols.append(k)
            out[p.stem] = {"columns": cols, "rows": rows}
    return out


def scope_scripts(html):
    """Production runs each <script> in its own scope (they redeclare top-level
    consts). Wrap each inline script body in an IIFE so they still run in order."""
    def wrap(m):
        return f"{m.group(1)}(function () {{\n{m.group(2)}\n}})();{m.group(3)}"
    return re.sub(r"(<script>)(.*?)(</script>)", wrap, html, flags=re.S)


def main():
    index = INDEX.read_text(encoding="utf-8")       # re-read on every build; never written
    data_json = json.dumps(load_data(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    if D3_LOCAL.exists():
        d3_tag = "<script>" + D3_LOCAL.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
        d3_from = "inlined from d3.min.js"
    else:
        d3_tag = f'<script src="{D3_CDN}"></script>'
        d3_from = D3_CDN
    page = f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard preview (local harness)</title>
<style>{HOST_CSS}</style>
{d3_tag}
<script type="application/json" id="preview-data">{data_json}</script>
<script>{MOCK_DASH}</script>
</head>
<body>
<div id="dash-root" data-dash-one-writer>
{scope_scripts(index)}
</div>
<script>window.__previewStart();</script>
</body>
</html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page) / 1e6:.1f} MB; d3 {d3_from}; {len(index)} bytes of index.html)")


if __name__ == "__main__":
    main()

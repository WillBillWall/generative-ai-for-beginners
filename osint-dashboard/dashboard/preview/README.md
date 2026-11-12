# Local preview harness
Renders `../index.html` outside its host page, with a mock `dash`, host CSS variables (light and dark) and the files in `../../data/processed/` embedded.
1. `python3 build_preview.py` writes `preview.html` (re-run after every change to `index.html` or the data; it never writes `index.html`).
2. `node shoot.js` screenshots it at 1280px and 400px, dark and light, into `shots/`, and reports JS errors, empty drawings, cut labels and overflow; `node interact.js` then tests chips, search, tooltips and the map.
3. Open `preview.html?theme=light` (or `dark`, the default) in a browser to try it by hand. Offline, put d3 7.9.0 here as `d3.min.js` (`npm pack d3@7.9.0`) and it is inlined.

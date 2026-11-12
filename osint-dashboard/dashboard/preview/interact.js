// Exercise the dashboard's interactions in preview.html and report what happened.
// Usage: python3 build_preview.py && node interact.js   (screenshots: shots/ix-*.png)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const PAGE = 'file://' + path.join(__dirname, 'preview.html') + '?theme=dark';
const SHOTS = path.join(__dirname, 'shots');

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  await page.goto(PAGE);
  await page.waitForSelector('html[data-preview-ready]');
  // "More detail" blocks start closed. Opening one by its summary must redraw its charts at their real width.
  const widths = async (sel) => page.$eval(sel, (el) => ({ box: el.clientWidth, vb: Number((el.querySelector('svg').getAttribute('viewBox') || '').split(' ')[2]) }));
  const closed = await page.$$eval('details', (d) => d.filter((x) => x.open).length);
  await page.click('#trends > summary'); await page.waitForTimeout(300);
  const gw = await widths('[data-draw="growth"]');
  console.log(`${closed === 0 && Math.abs(gw.box - gw.vb) < 2 ? 'PASS' : 'FAIL'}  details: closed on load, redrawn at real width when opened  — ${closed} open on load; growth box ${gw.box}px, drawn ${gw.vb}px`);
  for (const s of await page.$$('details:not([open]) > summary')) { await s.click(); }
  await page.waitForTimeout(400);
  const log = (name, ok, extra) => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
  const shot = async (sel, name) => { const el = await page.$(sel); if (el) await el.screenshot({ path: path.join(SHOTS, `ix-${name}.png`) }); };
  const tipText = (sel) => page.$eval(sel, (el) => { const t = el.querySelector('.ut-tip'); return t && !t.hidden ? t.innerText.replace(/\n/g, ' | ') : null; });
  const hoverAt = async (sel, fx, fy) => {
    const el = await page.$(sel); await el.scrollIntoViewIfNeeded();
    const b = await el.boundingBox(); await page.mouse.move(b.x + b.width * fx, b.y + b.height * fy); await page.waitForTimeout(80);
  };

  // --- hover tooltips ---
  await hoverAt('[data-draw="index"]', 0.5, 0.5);
  let t = await tipText('[data-draw="index"]'); log('tooltip: growth index chart', !!t, t); await shot('[data-draw="index"]', 'tip-index');

  const hoverEl = async (host, inner, nth) => {
    const els = await page.$$(`${host} ${inner}`); const el = els[nth < 0 ? els.length + nth : nth];
    if (!el) return null; await el.scrollIntoViewIfNeeded(); await el.hover({ force: true }); await page.waitForTimeout(80); return tipText(host);
  };
  t = await hoverEl('[data-draw="perday"][data-metric="uav_per_day"]', 'rect', -2); log('tooltip: drones per day bar', !!t, t);
  t = await hoverEl('[data-draw="territory"]', 'rect.hit', 5); log('tooltip: territory month bar', !!t, t);
  t = await hoverEl('[data-draw="territory"]', 'g > line[stroke-width="3"]', 3); log('tooltip: territory report tick', !!t, t); await shot('[data-draw="territory"]', 'tip-territory-tick');
  t = await hoverEl('[data-draw="advantage"]', 'g:last-of-type rect', 10); log('tooltip: pace/cost chart', !!t, t);
  t = await hoverEl('[data-draw="before-after"]', 'g > g', 0); log('tooltip: before/after bar', !!t, t);
  t = await hoverEl('[data-draw="direction-heat"]', 'rect', 14); log('tooltip: direction heat cell', !!t, t);
  const latestRows = await page.$$eval('[data-draw="metrics-latest"] tr', (r) => r.length);
  log('metrics: latest-figure list filled', latestRows >= 8, `${latestRows} measures`);
  const stages = await page.$$eval('[data-draw="stage-legend"] span', (s) => s.map((x) => x.textContent));
  log('timeline legend lists only stages in the data', stages.length > 0 && !stages.includes('Resurgent'), stages.join(', '));
  t = await hoverEl('[data-draw="growth"]', 'g > g', 5); log('tooltip: growth row', !!t, t);
  t = await hoverEl('[data-draw="shift"][data-cls="tank"]', 'g[style] rect', 0); log('tooltip: shift marker', !!t, t); await shot('[data-draw="shift"][data-cls="tank"]', 'tip-shift');
  t = await hoverEl('[data-draw="adapt"]', 'rect', 0); log('tooltip: adaptation bar', !!t, t);
  t = await hoverEl('[data-draw="armour-adapt"]', 'g:last-of-type rect', 40); log('tooltip: armour adaptation', !!t, t);
  t = await hoverEl('[data-draw="claims"]', 'g > g', 2); log('tooltip: claims row', !!t, t);
  const decades = await page.$$eval('[data-draw="tank-age"] svg g g', (g) => g.map((x) => x.textContent));
  log('tank age: every decade labelled, no "Latest"', decades.length === 8 && !decades.join(' ').includes('Latest'), decades.slice(0, 3).join(' / '));

  // --- timeline chips and marker click ---
  const lanes = () => page.$$eval('[data-draw="timeline"] circle', (c) => c.length);
  const all = await lanes();
  await page.click('[data-side="RU"]'); const ru = await lanes();
  await page.click('[data-side="UA"]'); const ua = await lanes();
  await page.click('[data-side="all"]');
  log('timeline side chips', ru < all && ua < all && ru > 0 && ua > 0, `markers all=${all} RU=${ru} UA=${ua}`);
  await page.click('[data-src="RUSI"]'); const rusi = await lanes();
  await page.click('[data-src="ISW"]'); const isw = await lanes();
  await page.click('[data-src="other"]'); const oth = await lanes();
  await page.click('[data-src="all"]');
  log('timeline source chips', rusi > 0 && isw > 0 && oth > 0 && rusi < all, `RUSI=${rusi} ISW=${isw} other=${oth}`);
  const pressed = await page.$$eval('.ut-chip[aria-pressed="true"]', (b) => b.map((x) => x.textContent));
  log('chips show pressed state', pressed.includes('Both sides') && pressed.includes('All sources'), pressed.join(', '));
  const marks = await page.$$('[data-draw="timeline"] circle');
  await marks[6].scrollIntoViewIfNeeded(); await marks[6].click({ force: true }); await page.waitForTimeout(100);
  const detail = await page.$eval('[data-draw="detail"]', (e) => e.innerText.replace(/\n/g, ' | '));
  const big = await page.$$eval('[data-draw="timeline"] circle', (c) => c.filter((x) => x.getAttribute('r') === '7').length);
  log('timeline marker click fills detail', !/^Select a/.test(detail) && detail.length > 40, `${big} enlarged marker(s); ${detail.slice(0, 160)}`);
  await shot('#tactic-timeline .ut-card', 'timeline-selected');

  // --- source log search ---
  const rows = () => page.$$eval('[data-draw="obs-table"] tr', (r) => r.length);
  const n0 = await rows();
  await page.fill('#ut-search', 'fiber'); await page.waitForTimeout(80); const n1 = await rows();
  await page.fill("#ut-search", "zzzz"); await page.waitForTimeout(80); const n2 = await rows();
  await page.fill('#ut-search', ''); await page.waitForTimeout(80); const n3 = await rows();
  log('source log search', n1 > 0 && n1 < n0 && n2 === 1 && n3 === n0, `all=${n0} "fiber"=${n1} "zzzz" shows: ${await page.$eval('[data-draw="obs-table"]', (e) => e.textContent.slice(0, 60))}`);

  // --- map ---
  const map = '[data-draw="front-map"]';
  await (await page.$(map)).scrollIntoViewIfNeeded();
  const view = () => page.evaluate(() => JSON.stringify(window.utMapView || null));
  const cap = () => page.$eval('[data-draw="map-caption"]', (e) => e.textContent);
  const c0 = await cap();
  await page.click('[data-mapwin="s_12m"]'); const c1 = await cap();
  log('map period chips change caption', c0 !== c1, c1);
  await page.click('[data-mapwin="s_3m"]');
  const v0 = await view();
  await page.click('[data-mapzoom="in"]'); await page.click('[data-mapzoom="in"]'); await page.waitForTimeout(400);
  const v1 = await view(); log('map zoom in (+ twice)', v0 !== v1, `${v0} -> ${v1}`); await shot('#front-map', 'map-zoomed');
  const labelsZoomed = await page.$$eval(`${map} svg text`, (t) => t.length);
  const b = await (await page.$(map)).boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down(); await page.mouse.move(b.x + b.width / 2 - 120, b.y + b.height / 2 - 60, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(200);
  const v2 = await view(); log('map drag pans', v1 !== v2, v2);
  await page.click('[data-mapzoom="out"]'); await page.waitForTimeout(300); const v3 = await view(); log('map zoom out (−)', v3 !== v2, v3);
  await page.click('[data-mapzoom="reset"]'); await page.waitForTimeout(400);
  const v4 = await view(); log('map Reset returns to start view', v4 === v0, `${v4} (start ${v0}); svg text labels zoomed=${labelsZoomed}`);
  // hover then click a council that changed hands (not grey / background fill)
  const target = await page.evaluateHandle((sel) => {
    const paths = [...document.querySelectorAll(sel + ' svg path')].filter((p) => /categorical/.test(p.getAttribute('fill') || ''));
    return paths.sort((p, q) => q.getBBox().width * q.getBBox().height - p.getBBox().width * p.getBBox().height)[0] || null;
  }, map);
  const el = target.asElement();
  if (!el) log('map council click', false, 'no coloured council path found');
  else {
    const bb = await el.boundingBox();
    await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.waitForTimeout(100);
    t = await tipText(map); log('map hover tooltip', !!t, t);
    await page.mouse.click(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.waitForTimeout(200);
    const d = await page.$eval('[data-draw="map-detail"]', (e) => e.innerText.replace(/\n+/g, ' | '));
    log('map council click fills details panel', !/^Click a council/.test(d) && d.length > 60, d.slice(0, 420));
    await shot('#front-map', 'map-selected');
    await page.mouse.click(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.waitForTimeout(200);
    const d2 = await page.$eval('[data-draw="map-detail"]', (e) => e.innerText);
    log('map second click clears selection', /^Click a council/.test(d2.trim()), d2.trim().slice(0, 60));
  }

  console.log(`\nconsole errors during interactions: ${errors.length}`);
  for (const e of errors) console.log('  ' + e.split('\n')[0]);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });

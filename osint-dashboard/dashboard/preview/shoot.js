// Screenshot preview.html at desktop and phone width, light and dark.
// Usage: python3 build_preview.py && node shoot.js
// Output: shots/<width>-<theme>-full.png, one PNG per .ut-card and per section header,
// plus a console report of JS errors, empty drawings and horizontal overflow.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const PAGE = 'file://' + path.join(HERE, 'preview.html');
const SHOTS = path.join(HERE, 'shots');
const WIDTHS = [1280, 400];
const THEMES = ['dark', 'light'];
const slug = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'untitled';

(async () => {
  fs.rmSync(SHOTS, { recursive: true, force: true });
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  let problems = 0;
  for (const width of WIDTHS) {
    for (const theme of THEMES) {
      const tag = `${width}-${theme}`;
      const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      const errors = [];
      page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });
      page.on('pageerror', (e) => errors.push('pageerror: ' + (e.stack || e.message)));
      await page.goto(`${PAGE}?theme=${theme}`);
      await page.waitForSelector('html[data-preview-ready]', { timeout: 15000 }).catch(() => errors.push('preview never became ready'));
      await page.waitForTimeout(300);

      console.log(`\n=== ${tag} ===`);
      for (const e of errors) console.log('  ERROR ' + e.split('\n').slice(0, 3).join(' | '));
      problems += errors.length;

      const audit = async (label) => {
      console.log(`  -- ${label} --`);
      // drawings that are empty or still show only the placeholder dash
      const draws = await page.$$eval('[data-draw]', (els) => els.map((el) => {
        const text = el.textContent.trim();
        const state = el.closest('[hidden]') ? 'hidden' : (el.children.length === 0 && text === '') ? 'EMPTY' : text === '—' ? 'DASH' : 'ok';
        return { name: el.dataset.draw, key: el.dataset.metric || el.dataset.fieldKey || el.dataset.cls || '', state };
      }));
      const bad = draws.filter((d) => d.state === 'EMPTY' || d.state === 'DASH');
      console.log(`  drawings: ${draws.length} total, ${bad.length} empty or dash`);
      for (const d of bad) console.log(`  ${d.state} data-draw="${d.name}" ${d.key}`);
      problems += bad.length;

      // horizontal overflow of the page, and elements that stick out of the viewport
      const over = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const out = [];
        for (const el of document.querySelectorAll('#dash-root *')) {
          if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
          const r = el.getBoundingClientRect();
          if (r.width && r.right > vw + 1 && !el.closest('.ut-tablebox, .ut-scroll')) out.push(`${el.tagName.toLowerCase()}.${el.className && el.className.baseVal === undefined ? el.className : ''} right=${Math.round(r.right)}`);
        }
        return { scrollW: document.documentElement.scrollWidth, vw, out: out.slice(0, 8) };
      });
      console.log(`  page scrollWidth ${over.scrollW} vs viewport ${over.vw}${over.scrollW > over.vw ? '  <-- HORIZONTAL OVERFLOW' : ''}`);
      for (const o of over.out) console.log('  sticks out: ' + o);

      // SVG text clipped by its own viewBox (cut labels)
      const cut = await page.evaluate(() => {
        const out = [];
        for (const svg of document.querySelectorAll('#dash-root svg')) {
          const sr = svg.getBoundingClientRect();
          const host = svg.closest('[data-draw]');
          for (const t of svg.querySelectorAll('text')) {
            const r = t.getBoundingClientRect();
            if (!r.width) continue;
            if (r.left < sr.left - 1.5 || r.right > sr.right + 1.5) out.push(`${host ? host.dataset.draw : '?'}: "${t.textContent.slice(0, 40)}" by ${Math.round(Math.max(sr.left - r.left, r.right - sr.right))}px`);
          }
        }
        return out;
      });
      console.log(`  svg labels cut by the chart edge: ${cut.length}`);
      for (const c of cut.slice(0, 12)) console.log('  cut: ' + c);
      console.log(`  page height ${await page.evaluate(() => document.documentElement.scrollHeight)} px`);
      };
      await audit('as loaded (More detail blocks closed)');

      await page.screenshot({ path: path.join(SHOTS, `${tag}-full.png`), fullPage: true });

      // one shot per section header area (h2 plus any lede/summary before the first card)
      const sections = await page.$$('.ut-section');
      for (let i = 0; i < sections.length; i++) {
        const id = (await sections[i].getAttribute('id')) || `section-${i}`;
        const clip = await sections[i].evaluate((s) => {
          const r = s.getBoundingClientRect();
          const firstCard = s.querySelector(':scope > .ut-card, :scope > .ut-grid4, :scope > .ut-grid');
          const bottom = firstCard ? firstCard.getBoundingClientRect().top : r.bottom;
          return { x: r.left + scrollX, y: r.top + scrollY - 8, width: r.width, height: Math.min(Math.max(bottom - r.top + 8, 30), 1400) };
        });
        await page.screenshot({ path: path.join(SHOTS, `${tag}-s${String(i + 1).padStart(2, '0')}-${slug(id)}-header.png`), clip, fullPage: true });
      }
      // top of page (title, summary, tiles)
      const head = await page.$('.ut-head');
      if (head) await head.screenshot({ path: path.join(SHOTS, `${tag}-s00-head.png`) });
      const tiles = await page.$('.ut-tiles');
      if (tiles) await tiles.screenshot({ path: path.join(SHOTS, `${tag}-s00-tiles.png`) });

      // one shot per card (outer cards and nested ones)
      const cards = await page.$$('.ut-card');
      for (let i = 0; i < cards.length; i++) {
        const title = await cards[i].evaluate((c) => { const h = c.querySelector('h3'); return h ? h.textContent : (c.closest('section') || {}).id || ''; });
        await cards[i].screenshot({ path: path.join(SHOTS, `${tag}-c${String(i + 1).padStart(2, '0')}-${slug(title)}.png`) });
      }
      // open every <details> block: its drawings are redrawn at their real width, then audited and shot
      const blocks = await page.$$('details');
      await page.$$eval('details', (ds) => ds.forEach((d) => { d.open = true; }));
      await page.waitForTimeout(500);
      await audit('with every More detail block open');
      for (let i = 0; i < blocks.length; i++) {
        const id = (await blocks[i].getAttribute('id')) || `details-${i}`;
        await blocks[i].screenshot({ path: path.join(SHOTS, `${tag}-d${String(i + 1).padStart(2, '0')}-${slug(id)}.png`) });
      }
      await page.screenshot({ path: path.join(SHOTS, `${tag}-full-open.png`), fullPage: true });
      console.log(`  saved ${cards.length} card shots, ${sections.length} section headers, ${blocks.length} opened detail blocks`);
      await ctx.close();
    }
  }
  await browser.close();
  console.log(`\n${problems ? problems + ' problem(s) found' : 'no errors, no empty drawings'}; screenshots in ${SHOTS}`);
})().catch((e) => { console.error(e); process.exit(1); });

const { chromium } = require('playwright'); const { Rec, cursor, click, moveTo, smoothScroll } = require('./rec.js');
const B = 'http://localhost:3000', OUT = process.env.OUT, T = process.env.TOK; const fs = require('fs'); const log = {};
const top = async (p, sel, off = 110) => smoothScroll(p, await p.evaluate(([s, o]) => document.querySelector(s).getBoundingClientRect().top + scrollY - o, [sel, off]), 1800);
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3, acceptDownloads: true });
  await ctx.addInitScript(t => { try { localStorage.setItem('reversa_token', t) } catch {} }, T); const p = await ctx.newPage();
  // C — plan review, approval, execution
  await p.goto(B + '/command', { waitUntil: 'networkidle' }); await p.waitForTimeout(1000); await cursor(p);
  const cb = p.getByLabel(/Try Vultr inference/); await cb.uncheck();
  let r = new Rec(p, 'C-plan', OUT + '/frames'); await r.start(); await p.waitForTimeout(1500);
  await click(p, p.getByRole('button', { name: 'Generate plan' })); await p.waitForSelector('#plan-title'); await p.waitForTimeout(800);
  await top(p, '#plan-title', 90); await p.waitForTimeout(4500);
  await moveTo(p, p.locator('text=Cannot be undone automatically')); await p.waitForTimeout(2500);
  await click(p, p.getByRole('button', { name: 'Approve plan' })); await p.waitForTimeout(1600);
  await click(p, p.getByRole('button', { name: 'Execute now' })); await p.waitForSelector('[data-state="COMPLETED"]', { timeout: 60000 }); await p.waitForTimeout(1500);
  const wfLink = await p.getAttribute('a:has-text("Open workflow")', 'href'); log.happy = wfLink;
  await click(p, p.getByRole('link', { name: 'Open workflow' })); await p.waitForSelector('text=Execution sequence'); await cursor(p); await p.waitForTimeout(2000);
  await smoothScroll(p, 330, 2200); await p.waitForTimeout(3000);
  await top(p, '[role=tablist]', 100); await p.waitForTimeout(3500);
  log.C = await r.stop(OUT + '/C-plan-exec.mp4');
  // D — simulate a failure, recovery
  await p.goto(B + '/demo-lab', { waitUntil: 'networkidle' }); await p.waitForTimeout(800); await cursor(p);
  r = new Rec(p, 'D-chaos', OUT + '/frames'); await r.start(); await p.waitForTimeout(2000);
  await click(p, p.getByRole('button', { name: 'Simulate a failure' }));
  await p.waitForSelector('text=Chaos scenario finished', { timeout: 120000 }); await p.waitForTimeout(2500);
  const ch = await p.getAttribute('a:has-text("Open result")', 'href'); log.chaos = ch;
  await click(p, p.getByRole('link', { name: /Open result/ })); await p.waitForSelector('text=Execution sequence'); await cursor(p); await p.waitForTimeout(3500);
  await smoothScroll(p, 520, 3000); await p.waitForTimeout(4000);
  await top(p, '[role=tablist]', 100); await click(p, p.getByRole('tab', { name: 'Recovery' })); await p.waitForTimeout(800);
  await smoothScroll(p, await p.evaluate(() => scrollY + 120), 1500); await p.waitForTimeout(4500);
  log.D = await r.stop(OUT + '/D-chaos.mp4');
  r = new Rec(p, 'D2-recovery', OUT + '/frames'); await p.goto(B + '/recovery', { waitUntil: 'networkidle' }); await p.waitForTimeout(1200); await cursor(p); await r.start();
  await p.waitForTimeout(2500); await moveTo(p, p.locator('text=Verified result')); await p.waitForTimeout(3000);
  log.D2 = await r.stop(OUT + '/D2-recovery.mp4');
  // E — evidence passport + JSON export
  const id = ch.split('/').pop();
  await p.goto(B + '/evidence/' + id, { waitUntil: 'networkidle' }); await p.waitForTimeout(1000); await cursor(p);
  r = new Rec(p, 'E-evidence', OUT + '/frames'); await r.start(); await p.waitForTimeout(2500);
  await moveTo(p, p.locator('text=Chain valid').first()); await p.waitForTimeout(2500);
  const [dl] = await Promise.all([p.waitForEvent('download'), click(p, p.getByRole('button', { name: 'Download JSON' }))]);
  await dl.saveAs(OUT + `/reversa-evidence-${id}.json`); await p.waitForTimeout(1200);
  await top(p, '#verify-title', 100); await p.waitForTimeout(3500);
  await smoothScroll(p, await p.evaluate(() => scrollY + 560), 2200); await p.waitForTimeout(3500);
  log.E = await r.stop(OUT + '/E-evidence.mp4');
  log.capturedAt = new Date().toISOString(); fs.writeFileSync(OUT + '/local-capture.json', JSON.stringify(log, null, 2)); console.log(JSON.stringify(log)); await b.close();
})();

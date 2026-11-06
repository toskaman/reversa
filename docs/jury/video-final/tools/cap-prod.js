const { chromium } = require('playwright'); const { Rec, cursor, click, moveTo, smoothScroll } = require('./rec.js');
const B = 'https://217.69.7.155.nip.io', OUT = process.env.OUT; const fs = require('fs'); const log = {};
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3 }); const p = await ctx.newPage();
  // A — overview + guided demo
  await p.goto(B + '/', { waitUntil: 'networkidle' }); await p.waitForTimeout(1500); await cursor(p);
  let r = new Rec(p, 'A-demo', OUT + '/frames'); await r.start(); await p.waitForTimeout(2500);
  await moveTo(p, p.locator('#hero-title')); await p.waitForTimeout(1200);
  await click(p, p.getByRole('button', { name: 'Start demo' }));
  await p.waitForSelector('text=View the result', { timeout: 90000 }); await p.waitForTimeout(2500);
  const href = await p.getAttribute('a:has-text("View the result")', 'href'); log.demoWorkflow = href;
  await click(p, p.getByRole('link', { name: 'View the result' }));
  await p.waitForSelector('text=Execution sequence', { timeout: 30000 }); await cursor(p); await p.waitForTimeout(2500);
  await smoothScroll(p, 420, 2500); await p.waitForTimeout(2500);
  log.A = await r.stop(OUT + '/A-demo.mp4');
  // B — real Vultr Inference planning (same guest session, 2nd workflow of quota)
  await p.goto(B + '/command', { waitUntil: 'networkidle' }); await p.waitForTimeout(1200); await cursor(p);
  r = new Rec(p, 'B-ai', OUT + '/frames'); await r.start(); await p.waitForTimeout(1200);
  const ta = p.locator('#intent'); await click(p, ta); await ta.fill('');
  await ta.pressSequentially('We just signed Globex Corporation as an enterprise customer. Set up their workspace, three user accounts, a support queue and billing, then verify everything.', { delay: 22 });
  await p.locator('#company').fill('Globex Corporation');
  const cb = p.getByLabel(/Try Vultr inference/); if (!(await cb.isChecked())) await click(p, cb);
  await moveTo(p, cb); await p.waitForTimeout(900);
  const [resp] = await Promise.all([p.waitForResponse(x => x.url().includes('/api/v1/intents'), { timeout: 120000 }), click(p, p.getByRole('button', { name: 'Generate plan' }))]);
  const body = await resp.json().catch(() => ({})); log.aiStatus = resp.status(); log.aiProvider = body.provider; log.aiWorkflow = body.workflow && body.workflow.id; log.aiKind = body.status || (body.workflow ? 'plan' : 'other');
  await p.waitForTimeout(1500);
  const plan = p.locator('#plan-title'); if (await plan.count()) { await plan.scrollIntoViewIfNeeded(); await smoothScroll(p, await p.evaluate(() => document.getElementById('plan-title').getBoundingClientRect().top + scrollY - 120), 1800); }
  await p.waitForTimeout(5000);
  log.B = await r.stop(OUT + '/B-ai.mp4');
  if (log.aiWorkflow) { const ev = await p.evaluate(async (id) => { const t = localStorage.getItem('reversa_guest_token');
      const r = await fetch(`/api/v1/workflows/${id}/events?limit=5`, { headers: { Authorization: 'Bearer ' + t } }); return r.ok ? (await r.json()).data[0] : r.status; }, log.aiWorkflow).catch(e => String(e));
    log.aiCreatedEvent = ev; }
  log.capturedAt = new Date().toISOString(); fs.writeFileSync(OUT + '/prod-capture.json', JSON.stringify(log, null, 2)); console.log(JSON.stringify(log, null, 1)); await b.close();
})();

// Real-time CDP screencast recorder: JPEG q92 frames with true timestamps -> CFR 30fps mp4.
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
class Rec {
  constructor(page, name, dir) { this.page = page; this.name = name; this.dir = path.join(dir, name); this.frames = []; }
  async start() {
    fs.rmSync(this.dir, { recursive: true, force: true }); fs.mkdirSync(this.dir, { recursive: true });
    this.cdp = await this.page.context().newCDPSession(this.page);
    this.cdp.on('Page.screencastFrame', async (f) => {
      const i = this.frames.length; const file = path.join(this.dir, `f${String(i).padStart(5, '0')}.jpg`);
      fs.writeFileSync(file, Buffer.from(f.data, 'base64'));
      this.frames.push({ file, t: f.metadata.timestamp });
      try { await this.cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch {}
    });
    await this.cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
    this.t0 = Date.now() / 1000;
  }
  async stop(out) {
    await new Promise((r) => setTimeout(r, 400));
    await this.cdp.send('Page.stopScreencast'); const end = Date.now() / 1000;
    const fr = this.frames; if (!fr.length) throw new Error('no frames');
    let txt = '';
    for (let i = 0; i < fr.length; i++) {
      const d = (i + 1 < fr.length ? fr[i + 1].t : end) - fr[i].t;
      txt += `file '${fr[i].file}'\nduration ${Math.max(d, 0.001).toFixed(4)}\n`;
    }
    txt += `file '${fr[fr.length - 1].file}'\n`;
    fs.writeFileSync(path.join(this.dir, 'list.txt'), txt);
    const tmp = out.replace(/\.mp4$/, '.tmp.mp4');
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(this.dir, 'list.txt'),
      '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0b0c0e,fps=30,format=yuv420p',
      '-c:v', 'libx264', '-crf', '16', '-preset', 'veryfast', tmp]);
    fs.renameSync(tmp, out);
    return { frames: fr.length, seconds: +(end - fr[0].t).toFixed(2) };
  }
}
// Slow, visible, deliberate cursor (drawn in-page so it appears in the screencast).
async function cursor(page) {
  await page.addStyleTag({ content: `#__cur{position:fixed;z-index:2147483647;width:22px;height:22px;pointer-events:none;left:-40px;top:-40px;
    transition:left .55s cubic-bezier(.22,.8,.3,1),top .55s cubic-bezier(.22,.8,.3,1)}
    #__cur svg{filter:drop-shadow(0 2px 4px rgba(0,0,0,.6))}
    #__cur.click::after{content:"";position:absolute;left:-12px;top:-12px;width:30px;height:30px;border-radius:50%;border:2px solid #7c9cff;animation:__r .45s ease-out}
    @keyframes __r{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}` });
  await page.evaluate(() => { if (document.getElementById('__cur')) return; const d = document.createElement('div'); d.id = '__cur';
    d.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2l14 8-6 1.6L8 18z" fill="#fff" stroke="#111" stroke-width="1.2"/></svg>';
    document.body.appendChild(d); });
}
async function moveTo(page, loc) {
  const b = await loc.boundingBox(); if (!b) return;
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.evaluate(([x, y]) => { const c = document.getElementById('__cur'); if (c) { c.style.left = x + 'px'; c.style.top = y + 'px'; } }, [x, y]);
  await page.mouse.move(x, y); await page.waitForTimeout(650);
}
async function click(page, loc) {
  await loc.scrollIntoViewIfNeeded(); await moveTo(page, loc);
  await page.evaluate(() => { const c = document.getElementById('__cur'); if (c) { c.classList.remove('click'); void c.offsetWidth; c.classList.add('click'); } });
  await page.waitForTimeout(150); await loc.click(); await page.waitForTimeout(300);
}
async function smoothScroll(page, y, ms = 1600) {
  await page.evaluate(([y, ms]) => new Promise(r => { const s = scrollY, t0 = performance.now();
    const f = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; scrollTo(0, s + (y - s) * e); k < 1 ? requestAnimationFrame(f) : r(); };
    requestAnimationFrame(f); }), [y, ms]);
}
module.exports = { Rec, cursor, moveTo, click, smoothScroll };

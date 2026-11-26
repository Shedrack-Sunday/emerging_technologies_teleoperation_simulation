// Operator station UI. Talks to Python over one WebSocket.
import { CameraSensor } from './sensor.js';
import { MapView } from './mapview.js';

const $ = (id) => document.getElementById(id);
const S = {
  ws: null, init: null, sensor: null, map: null,
  simT: 0, simWall: performance.now(),
  frame: null, frameRecv: -1e9, frameTimes: [],
  keys: new Set(),
};
const simNow = () => S.simT + (performance.now() - S.simWall) / 1000;

// ------------------------------------------------------------------ websocket
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = 'arraybuffer';
  S.ws = ws;
  ws.onopen = () => {
    $('conn').classList.add('on'); $('conn').querySelector('span').textContent = 'connected';
    send({ type: 'hello', renderer: true, visible: !document.hidden });
  };
  ws.onclose = () => {
    $('conn').classList.remove('on'); $('conn').querySelector('span').textContent = 'no connection to robot (python3 run.py)';
    setTimeout(connect, 1000);
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      const d = JSON.parse(ev.data);
      if (d.type === 'batch') d.items.forEach(handle); else handle(d);
    } else {
      const dv = new DataView(ev.data);
      const n = dv.getUint32(0);
      const hdr = JSON.parse(new TextDecoder().decode(new Uint8Array(ev.data, 4, n)));
      onImage(hdr, new Uint8Array(ev.data, 4 + n));
    }
  };
}
function send(obj) { if (S.ws?.readyState === 1) S.ws.send(JSON.stringify(obj)); }

function sendFrame(id, w, h, pixels) {
  const hdr = new TextEncoder().encode(JSON.stringify({ kind: 'frame', id, w, h }));
  const buf = new Uint8Array(4 + hdr.length + pixels.length);
  new DataView(buf.buffer).setUint32(0, hdr.length);
  buf.set(hdr, 4); buf.set(pixels, 4 + hdr.length);
  S.ws.send(buf);
}

// ------------------------------------------------------------------ dispatch
function handle(d) {
  if (d.t !== undefined) { S.simT = d.t; S.simWall = performance.now(); }
  switch (d.type) {
    case 'init': onInit(d); break;
    case 'render':
      if (!S.sensor) { send({ type: 'render_error', error: S.sensorError || 'camera renderer not ready' }); break; }
      try { sendFrame(d.id, d.w, d.h, S.sensor.render(d)); }
      catch (e) { console.error(e); send({ type: 'render_error', error: String(e) }); }
      break;
    case 'msg': onTelemetry(d); break;
    case 'truth': S.map?.setTruth(d.p, d.q); break;
    case 'stats': onStats(d); break;
    case 'op': onOperator(d); break;
  }
}

function onInit(d) {
  if (S.init && S.init.session !== d.session) { location.reload(); return; }   // python restarted with new settings
  if (S.init) return;                                                          // reconnect to the same run
  S.init = d;
  try { S.sensor = new CameraSensor(d.world); }
  catch (e) { console.error(e); S.sensorError = String(e); }
  S.map = new MapView($('map'), d.world);
  S.map.showTruth = !!d.show_truth;
}

function onOperator(d) {
  $('keys-now').textContent = d.keys.length ? d.keys.join(' + ') : '';
  const c = d.cmd;
  const any = Object.values(c).some((v) => v !== 0);
  $('cmd-now').textContent = any
    ? `cmd v ${[c.vx, c.vy, c.vz].map((v) => v.toFixed(2)).join(' ')} m/s · ω ${[c.wx, c.wy, c.wz].map((v) => v.toFixed(2)).join(' ')} rad/s`
    : '';
}

// ------------------------------------------------------------------ camera feed
async function onImage(hdr, bytes) {
  if (hdr.topic !== 'camera/image') return;
  if (S.frame && hdr.seq < S.frame.seq) return;
  const bmp = await createImageBitmap(new Blob([bytes], { type: 'image/jpeg' }));
  S.frame = { ...hdr, bmp };
  S.frameRecv = hdr.recv;
  S.frameTimes.push(hdr.recv);
  while (S.frameTimes.length && S.frameTimes[0] < hdr.recv - 2) S.frameTimes.shift();
  drawFeed();
}

function drawFeed() {
  const c = $('feed'), wrap = c.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const W = Math.round(wrap.clientWidth * dpr), H = Math.round(wrap.clientHeight * dpr);
  if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
  const g = c.getContext('2d');
  g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
  const f = S.frame;
  if (!f) return;
  const s = Math.min(W / f.w, H / f.h);
  const dw = f.w * s, dh = f.h * s;
  g.imageSmoothingEnabled = true;
  g.drawImage(f.bmp, (W - dw) / 2, (H - dh) / 2, dw, dh);
  const fps = S.frameTimes.length / 2;
  $('feed-info').textContent = `${f.w}×${f.h} · ${(f.size / 1024).toFixed(1)} kB/frame · ${fps.toFixed(1)} fps`;
}

function tickOverlay() {
  const f = S.frame;
  const now = simNow();
  if (f) {
    const age = now - f.stamp;
    $('feed-age').textContent = `image age ${age.toFixed(2)} s`;
    $('feed-age').style.color = age > 1 ? 'var(--bad)' : age > 0.3 ? 'var(--warn)' : 'var(--ok)';
  }
  const stale = !f || now - S.frameRecv > 1.5;
  $('nosignal').style.display = stale ? 'flex' : 'none';
  $('feed').style.opacity = stale ? 0.35 : 1;
  requestAnimationFrame(tickOverlay);
}
new ResizeObserver(drawFeed).observe($('feed').parentElement);

// ------------------------------------------------------------------ telemetry
const RANGE_NAMES = ['fwd', 'back', 'left', 'right', 'up', 'down'];
$('ranges').innerHTML = RANGE_NAMES.map((n) => `<div class="rg"><div class="bar"><i></i></div>${n} <span>–</span></div>`).join('');

function quatToYawPitch(q) {
  const [w, x, y, z] = q;
  const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
  const pitch = Math.asin(Math.max(-1, Math.min(1, 2 * (w * y - z * x))));
  return [yaw * 180 / Math.PI, pitch * 180 / Math.PI];
}

// The numbers are averaged and refreshed 4x per second, like on a real
// ground station display: readable instead of flickering with sensor noise.
const NAV_DISPLAY_PERIOD = 0.25;
const f2 = (v) => (Math.abs(v) < 0.005 ? 0 : v).toFixed(2);   // no flickering "-0.00"
const navAcc = { n: 0, p: [0, 0, 0], speed: 0, yaw: [0, 0], pitch: 0, t0: -1 };
function navReadout(d) {
  const [yaw, pitch] = quatToYawPitch(d.q);
  const a = navAcc;
  a.n += 1;
  d.p.forEach((v, i) => { a.p[i] += v; });
  a.speed += Math.hypot(...d.v);
  a.yaw[0] += Math.cos(yaw * Math.PI / 180); a.yaw[1] += Math.sin(yaw * Math.PI / 180);   // average angles via unit vectors
  a.pitch += pitch;
  const now = simNow();
  if (a.t0 < 0) a.t0 = now;
  if (now - a.t0 < NAV_DISPLAY_PERIOD && a.n > 1) return;
  const speed = a.speed / a.n;
  $('tm-pos').textContent = a.p.map((v) => f2(v / a.n)).join(' ');
  $('tm-speed').textContent = `${(speed < 0.005 ? 0 : speed).toFixed(2)} m/s`;
  const yawAvg = Math.atan2(a.yaw[1], a.yaw[0]) * 180 / Math.PI;
  $('tm-att').textContent = `${Math.round(yawAvg)}° ${Math.round(a.pitch / a.n)}°`;
  Object.assign(a, { n: 0, p: [0, 0, 0], speed: 0, yaw: [0, 0], pitch: 0, t0: now });
}

function onTelemetry(m) {
  const d = m.data;
  switch (m.topic) {
    case 'nav/pose': {
      S.map?.setNav(d.p, d.q);
      navReadout(d);
      break;
    }
    case 'range': {
      const acc = S.rangeAcc ??= { n: 0, sum: [0, 0, 0, 0, 0, 0], t0: simNow() };
      acc.n += 1; d.d.forEach((r, i) => { acc.sum[i] += r; });
      [...$('ranges').children].forEach((el, i) => {
        const r = d.d[i];
        const bar = el.querySelector('i');
        bar.style.width = `${Math.max(0, Math.min(1, 1 - r / 1.5)) * 100}%`;
        bar.style.background = r < 0.15 ? 'var(--bad)' : r < 0.4 ? 'var(--warn)' : 'var(--ok)';
      });
      if (simNow() - acc.t0 >= NAV_DISPLAY_PERIOD) {        // numbers: averaged, 4x per second
        [...$('ranges').children].forEach((el, i) => { el.querySelector('span').textContent = (acc.sum[i] / acc.n).toFixed(2); });
        S.rangeAcc = null;
      }
      break;
    }
    case 'status':
      $('tm-batt').textContent = `${d.battery.toFixed(0)} %`;
      $('tm-coll').textContent = d.collisions;
      $('tm-cmdage').textContent = d.cmd_age_ms > 9999 ? '–' : `${d.cmd_age_ms} ms`;
      break;
    case 'events': onEvent(m); break;
  }
}

function onEvent(m) {
  const d = m.data;
  const li = document.createElement('li');
  li.className = d.type;
  const t = m.stamp.toFixed(1);
  if (d.type === 'collision') { li.textContent = `${t}s  collision (${d.speed.toFixed(2)} m/s)`; banner('Collision!', 'var(--bad)'); }
  else li.textContent = `${t}s  ${JSON.stringify(d)}`;
  $('events').prepend(li);
}

let bannerTimer = null;
function banner(text, color) {
  const b = $('banner');
  b.textContent = text; b.style.color = color; b.classList.add('show');
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => b.classList.remove('show'), 1500);
}

// ------------------------------------------------------------------ stats
function fmt(v, d = 0) { return v == null ? '–' : v.toFixed(d); }

function onStats(d) {
  const rows = [];
  let down = 0, up = 0;
  for (const [topic, s] of Object.entries(d.down)) {
    down += s.rx_kbps;
    rows.push(`<tr><td>↓ ${topic}</td><td>${fmt(s.rx_hz, 1)}</td><td>${fmt(s.rx_kbps, 1)}</td><td>${fmt(s.latency_ms)} ms</td><td>${fmt(s.loss_pct)} %</td></tr>`);
  }
  for (const [topic, s] of Object.entries(d.up)) {
    up += s.rx_kbps;
    rows.push(`<tr><td class="up">↑ ${topic}</td><td>${fmt(s.rx_hz, 1)}</td><td>${fmt(s.rx_kbps, 1)}</td><td>${fmt(s.latency_ms)} ms</td><td>${fmt(s.loss_pct)} %</td></tr>`);
  }
  $('link-table').querySelector('tbody').innerHTML = rows.join('');
  $('link-total').textContent = `total ↓ ${down.toFixed(1)} kbit/s   ↑ ${up.toFixed(1)} kbit/s`;

  const errs = Object.entries(d.errors || {});
  $('errors').innerHTML = errs.map(([k, v]) => `<div class="err">⚠ ${k}: ${escapeHtml(v)}</div>`).join('');
}

function escapeHtml(s) { return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }

// ------------------------------------------------------------------ controls
const KEYMAP = {
  KeyW: 'w', KeyA: 'a', KeyS: 's', KeyD: 'd', KeyR: 'r', KeyF: 'f', KeyQ: 'q', KeyE: 'e',
  ArrowUp: 'arrowup', ArrowDown: 'arrowdown',
};
function sendKeys() { send({ type: 'keys', keys: [...S.keys] }); }
window.addEventListener('keydown', (e) => {
  const k = KEYMAP[e.code];
  if (!k) return;
  e.preventDefault();
  if (!S.keys.has(k)) { S.keys.add(k); sendKeys(); }
});
window.addEventListener('keyup', (e) => {
  const k = KEYMAP[e.code];
  if (k && S.keys.delete(k)) sendKeys();
});
window.addEventListener('blur', () => { S.keys.clear(); sendKeys(); });

$('tg-follow').onchange = (e) => { S.map.follow = e.target.checked; };

document.addEventListener('visibilitychange', () => send({ type: 'visible', visible: !document.hidden }));
connect();
requestAnimationFrame(tickOverlay);

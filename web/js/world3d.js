// Builds the Kibo interior from the world description sent by Python.
// All geometry lives in a group whose frame is the ROS/simulation frame
// (x along the module, y left, z up); the group itself is rotated so that
// three.js' y-up convention is satisfied.
import * as THREE from 'three';
import { ColladaLoader } from 'three/addons/loaders/ColladaLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const RACK_W = 1.06;
export let MAX_ANISO = 8;
export function setMaxAnisotropy(n) { MAX_ANISO = n; }

// ---------------------------------------------------------------- textures
function canvasTex(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

function rng(seed) {           // small deterministic PRNG so racks look the same every time
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

const WALL_NAMES = { floor: 'D', ceil: 'O', left: 'P', right: 'S' };   // deck, overhead, port, starboard

function rackTexture(wall, idx) {
  const r = rng(idx * 97 + wall.charCodeAt(0) * 13);
  return canvasTex(256, 512, (g, W, H) => {
    // base panel
    g.fillStyle = wall === 'ceil' ? '#d9dcdf' : wall === 'floor' ? '#b9bdc2' : '#cfd3d6';
    g.fillRect(0, 0, W, H);
    // rack frame
    g.fillStyle = '#9aa1a8';
    g.fillRect(0, 0, 8, H); g.fillRect(W - 8, 0, 8, H);
    // sub panels / drawers
    let y = 14;
    while (y < H - 30) {
      const h = 40 + Math.floor(r() * 110);
      const kind = r();
      g.fillStyle = kind < 0.15 ? '#3b4250' : kind < 0.3 ? '#e6e7e3' : '#c4c8cc';
      g.fillRect(14, y, W - 28, h - 6);
      g.strokeStyle = 'rgba(0,0,0,.35)'; g.lineWidth = 2; g.strokeRect(14, y, W - 28, h - 6);
      if (kind < 0.15) {               // vent grid
        g.fillStyle = '#272c35';
        for (let vx = 24; vx < W - 30; vx += 10) g.fillRect(vx, y + 8, 5, h - 22);
      } else if (kind < 0.45) {        // drawer handles
        g.fillStyle = '#5a6068';
        g.fillRect(W / 2 - 30, y + h / 2 - 6, 60, 6);
      }
      if (r() < 0.35) {                // velcro / sticker
        g.fillStyle = ['#2d6cdf', '#f2c230', '#ffffff', '#e04f3f'][Math.floor(r() * 4)];
        g.fillRect(20 + r() * (W - 80), y + 6 + r() * Math.max(1, h - 30), 22 + r() * 30, 10 + r() * 10);
      }
      // screws
      g.fillStyle = '#7d848c';
      for (const sx of [20, W - 24]) { g.beginPath(); g.arc(sx, y + 6, 3, 0, 7); g.fill(); }
      y += h;
    }
    // rack label
    const label = `JPM1${WALL_NAMES[wall]}${idx + 1}`;
    g.fillStyle = '#1a2a6c'; g.fillRect(W / 2 - 52, 18, 104, 30);
    g.fillStyle = '#fff'; g.font = 'bold 22px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(label, W / 2, 34);
    // big location marker (helps navigation)
    g.fillStyle = 'rgba(30,40,60,.75)'; g.font = 'bold 54px sans-serif';
    g.fillText(String(idx + 1), W / 2, H - 50);
  });
}

function endWallTexture(text, sub) {
  return canvasTex(512, 512, (g, W, H) => {
    g.fillStyle = '#c9cdd1'; g.fillRect(0, 0, W, H);
    g.fillStyle = '#9aa1a8';
    g.beginPath(); g.arc(W / 2, H / 2, 200, 0, 7); g.fill();
    g.fillStyle = '#5f6670';
    g.beginPath(); g.arc(W / 2, H / 2, 175, 0, 7); g.fill();
    g.fillStyle = '#7b828b';
    for (let a = 0; a < 6; a++) {
      const x = W / 2 + 188 * Math.cos(a * Math.PI / 3), y = H / 2 + 188 * Math.sin(a * Math.PI / 3);
      g.beginPath(); g.arc(x, y, 9, 0, 7); g.fill();
    }
    g.fillStyle = '#f2c230'; g.fillRect(W / 2 - 120, 40, 240, 34);
    g.fillStyle = '#111'; g.font = 'bold 24px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text, W / 2, 58);
    g.fillStyle = '#e9ecef'; g.font = 'bold 30px sans-serif';
    g.fillText(sub, W / 2, H / 2);
  });
}

function bagTexture(name) {
  return canvasTex(256, 256, (g, W, H) => {
    g.fillStyle = '#e8e2d0'; g.fillRect(0, 0, W, H);
    g.strokeStyle = '#cfc7b1'; g.lineWidth = 3;
    for (let i = 0; i < W; i += 18) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, H); g.stroke(); }
    g.fillStyle = '#ffffff'; g.fillRect(40, 90, 176, 76);
    g.fillStyle = '#222'; g.font = 'bold 34px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(name, W / 2, 128);
  });
}

// ---------------------------------------------------------------- helpers
function planeAt(w, h, center, normal, up, material) {
  const geo = new THREE.PlaneGeometry(w, h);
  const n = new THREE.Vector3(...normal), u = new THREE.Vector3(...up);
  const right = new THREE.Vector3().crossVectors(u, n);
  const m = new THREE.Matrix4().makeBasis(right, u, n);
  const mesh = new THREE.Mesh(geo, material);
  mesh.quaternion.setFromRotationMatrix(m);
  mesh.position.set(...center);
  return mesh;
}

const KIND_COLORS = { hardware: 0x8d949c, laptop: 0x24272c, cable: 0x15171a, rail: 0x7fa6c8, bag: 0xe8e2d0 };

// ---------------------------------------------------------------- world
function addBoxModule(root, world, inside, { x0, y0, z0, x1, y1, z1, L, W, H, side }) {
  // racks: 10 per wall
  const n = Math.round(L / RACK_W);
  const segW = L / n;
  for (let i = 0; i < n; i++) {
    const cx = x0 + (i + 0.5) * segW;
    const mk = (wall) => new THREE.MeshLambertMaterial({
      map: rackTexture(wall, i), side,
      transparent: !inside, opacity: inside ? 1 : 0.55, depthWrite: inside });
    root.add(planeAt(segW, H, [cx, y1, 0], [0, -1, 0], [0, 0, 1], mk('left')));
    root.add(planeAt(segW, H, [cx, y0, 0], [0, 1, 0], [0, 0, 1], mk('right')));
    root.add(planeAt(segW, W, [cx, 0, z0], [0, 0, 1], [0, 1, 0], mk('floor')));
    if (inside) root.add(planeAt(segW, W, [cx, 0, z1], [0, 0, -1], [0, 1, 0], mk('ceil')));
  }
  root.add(planeAt(W, H, [x0, 0, 0], [1, 0, 0], [0, 0, 1],
    new THREE.MeshLambertMaterial({ map: endWallTexture('NODE 2', '◀ NODE 2'), side })));
  root.add(planeAt(W, H, [x1, 0, 0], [-1, 0, 0], [0, 0, 1],
    new THREE.MeshLambertMaterial({ map: endWallTexture('JEM AIRLOCK', 'AIRLOCK ▶'), side })));

  // light strips along the ceiling edges
  if (inside) {
    const lightMat = new THREE.MeshBasicMaterial({ color: 0xfff8e8 });
    for (const y of [y0 + 0.25, y1 - 0.25]) {
      const strip = new THREE.Mesh(new THREE.BoxGeometry(L * 0.9, 0.08, 0.02), lightMat);
      strip.position.set(x0 + L / 2, y, z1 - 0.012);
      root.add(strip);
    }
  }

}

const moduleCache = {};
function loadModule(url, inside) {
  moduleCache[url] ??= new Promise((resolve) => {
    new GLTFLoader().load(url, (g) => resolve(g.scene), undefined, (e) => { console.error('module load failed', e); resolve(new THREE.Group()); });
  });
  return moduleCache[url].then((scene) => {
    const m = scene.clone(true);
    m.traverse((o) => {
      if (!o.isMesh) return;
      const src = o.material;
      if (src.map) { src.map.anisotropy = MAX_ANISO; src.map.needsUpdate = true; }  // racks are seen at grazing angles
      // The ISS textures have baked-in shading -> show them unlit (true colours, crisp, cheap to render).
      const mat = new THREE.MeshBasicMaterial({ map: src.map ?? null, color: src.map ? 0xf2f2f2 : src.color });
      if (!inside) { mat.transparent = true; mat.opacity = 0.6; mat.depthWrite = false; }
      o.material = mat;
    });
    return m;
  });
}

// mode: 'inside' (camera sensor: textured, lit from the ceiling)
//       'map'    (3D overview: walls seen from outside are culled)
export function buildWorld(world, mode = 'inside') {
  const root = new THREE.Group();
  root.rotation.x = -Math.PI / 2;               // ROS z-up -> three y-up
  const [x0, y0, z0] = world.min, [x1, y1, z1] = world.max;
  const L = x1 - x0, W = y1 - y0, H = z1 - z0;
  const inside = mode === 'inside';
  const side = THREE.FrontSide;                 // planes face inward; from outside they are invisible

  if (world.mesh) {
    // the real module, cut out of the ISS interior model (tools/build_kibo.py)
    loadModule(world.mesh, inside).then((m) => root.add(m));
  } else {
    addBoxModule(root, world, inside, { x0, y0, z0, x1, y1, z1, L, W, H, side });
  }
  // obstacles
  for (const o of world.obstacles) {
    const size = o.max.map((v, k) => v - o.min[k]);
    const c = o.max.map((v, k) => (v + o.min[k]) / 2);
    const mat = o.kind === 'bag'
      ? new THREE.MeshLambertMaterial({ map: bagTexture(o.name) })
      : new THREE.MeshLambertMaterial({ color: KIND_COLORS[o.kind] ?? 0x888888 });
    const box = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
    box.position.set(...c);
    root.add(box);
    if (o.kind === 'laptop') {
      const scr = new THREE.Mesh(new THREE.PlaneGeometry(size[0] * 0.85, size[2] * 0.8),
        new THREE.MeshBasicMaterial({ color: 0x2b6cb0 }));
      scr.position.set(c[0], o.max[1] + 0.002, c[2]);
      scr.rotation.x = Math.PI / 2;
      root.add(scr);
    }
  }

  // lighting
  const lights = new THREE.Group();
  lights.add(new THREE.HemisphereLight(0xffffff, 0x9aa0aa, world.mesh ? (inside ? 2.6 : 3.0) : (inside ? 1.6 : 2.2)));
  if (inside) {
    for (let x = x0 + 1; x < x1; x += 2.5) {
      const p = new THREE.PointLight(0xfff5e0, 2.0, 5, 1.2);
      p.position.set(x, 0, z1 - 0.15);
      root.add(p);
    }
  } else {
    const d = new THREE.DirectionalLight(0xffffff, 1.2);
    d.position.set(3, 6, 4);
    lights.add(d);
  }

  return { root, lights };
}

// ---------------------------------------------------------------- Int-Ball model
let modelPromise = null;
export function loadIntBall() {
  if (!modelPromise) {
    modelPromise = new Promise((resolve) => {
      new ColladaLoader().load('/assets/intball2/intball2.dae', (c) => {
        c.scene.rotation.set(0, 0, 0);          // we are already in a z-up frame
        resolve(c.scene);
      }, undefined, () => {                     // fallback: a sphere
        resolve(new THREE.Mesh(new THREE.SphereGeometry(0.09, 24, 16),
          new THREE.MeshLambertMaterial({ color: 0xf0f0f0 })));
      });
    });
  }
  return modelPromise.then((m) => m.clone(true));
}

export function setPose(obj, p, q) {          // q = [w, x, y, z]
  obj.position.set(p[0], p[1], p[2]);
  obj.quaternion.set(q[1], q[2], q[3], q[0]);
}

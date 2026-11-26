// 3D overview ("digital twin") at the operator station. The robot shown here is
// placed from the nav/pose telemetry that came through the downlink - so it is as
// old as that telemetry. The orange "truth" ghost is only available in simulation.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildWorld, loadIntBall, setPose } from './world3d.js';

export class MapView {
  constructor(canvas, world) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e14);
    this.world = buildWorld(world, 'map');
    this.scene.add(this.world.root, this.world.lights);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.05, 100);
    this.camera.position.set(-1.5, 2.6, 3.2);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(1.5, 0, 0);
    this.controls.enableDamping = true;
    this.follow = true;
    this.showTruth = false;

    this.twin = new THREE.Group();
    this.truth = new THREE.Group();
    this.truth.visible = false;
    this.world.root.add(this.twin, this.truth);
    loadIntBall().then((m) => { m.scale.setScalar(1.6); this.twin.add(m); });   // a bit larger to be visible
    loadIntBall().then((m) => {
      m.scale.setScalar(1.6);
      m.traverse((o) => {
        if (o.isMesh) o.material = new THREE.MeshBasicMaterial({ color: 0xff9a3c, wireframe: true, transparent: true, opacity: 0.5 });
      });
      this.truth.add(m);
    });
    // camera direction indicator on the twin
    const arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), 0.45, 0x4cc2ff, 0.1, 0.06);
    this.twin.add(arrow);

    this.trailPts = [];
    this.trail = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x4cc2ff, transparent: true, opacity: 0.6 }));
    this.world.root.add(this.trail);
    this.hasPose = false;

    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    this.resize();
    const loop = () => { this.render(); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  resize() {
    const el = this.canvas.parentElement;
    const w = el.clientWidth, h = el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setNav(p, q) {
    setPose(this.twin, p, q);
    this.hasPose = true;
    const last = this.trailPts[this.trailPts.length - 1];
    if (!last || Math.hypot(p[0] - last[0], p[1] - last[1], p[2] - last[2]) > 0.03) {
      this.trailPts.push(p.slice());
      if (this.trailPts.length > 600) this.trailPts.shift();
      this.setTrail(this.trailPts);
    }
  }

  setTrail(pts) {
    this.trail.geometry.dispose();
    this.trail.geometry = new THREE.BufferGeometry().setFromPoints(pts.map((v) => new THREE.Vector3(...v)));
  }

  clearTrail() { this.trailPts = []; this.setTrail([]); }

  setTruth(p, q) { setPose(this.truth, p, q); }

  render() {
    this.truth.visible = this.showTruth;
    if (this.follow && this.hasPose) {
      const wp = new THREE.Vector3();
      this.twin.getWorldPosition(wp);
      const delta = wp.clone().sub(this.controls.target).multiplyScalar(0.08);
      this.controls.target.add(delta);
      this.camera.position.add(delta);
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

// The robot's main camera. It renders on request from Python using the TRUE
// robot pose (this is the "sensor" on board Int-Ball, before the link) and sends
// raw RGBA pixels back. Python compresses the frame and pushes it through the
// simulated downlink - what you see in the camera panel is what came out of it.
import * as THREE from 'three';
import { buildWorld, setPose, setMaxAnisotropy } from './world3d.js';

export class CameraSensor {
  constructor(world) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, canvas: document.createElement('canvas') });
    setMaxAnisotropy(Math.min(16, this.renderer.capabilities.getMaxAnisotropy()));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x202428);
    this.world = buildWorld(world, 'inside');
    this.scene.add(this.world.root, this.world.lights);

    this.body = new THREE.Object3D();              // Int-Ball body frame
    this.world.root.add(this.body);
    this.camera = new THREE.PerspectiveCamera(60, 4 / 3, 0.02, 30);
    this.camera.position.set(0.14, 0, 0);          // camera sits on the front face (URDF cameraF_joint)
    // three.js cameras look along -Z with +Y up; we want body +X forward with +Z up.
    this.camera.quaternion.setFromEuler(new THREE.Euler(Math.PI / 2, 0, -Math.PI / 2, 'ZXY'));
    this.body.add(this.camera);
    this.target = null;
  }

  render(req) {
    const { w, h } = req;
    if (!this.target || this.target.width !== w || this.target.height !== h) {
      this.target?.dispose();
      this.target = new THREE.WebGLRenderTarget(w, h, { samples: 4 });
      this.target.texture.colorSpace = THREE.SRGBColorSpace;
      this.pixels = new Uint8Array(w * h * 4);
    }
    const aspect = w / h;
    this.camera.aspect = aspect;
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(req.hfov) / 2) / aspect));
    this.camera.updateProjectionMatrix();
    setPose(this.body, req.p, req.q);
    this.scene.updateMatrixWorld(true);

    this.renderer.setRenderTarget(this.target);
    this.renderer.render(this.scene, this.camera);
    this.renderer.readRenderTargetPixels(this.target, 0, 0, w, h, this.pixels);
    this.renderer.setRenderTarget(null);
    return this.pixels;
  }
}

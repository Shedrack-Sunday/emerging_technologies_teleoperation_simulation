#!/usr/bin/env python3
"""Build the Kibo assets from the full ISS interior model (instructor tool, not
needed by students).

    pip install -r tools/requirements-dev.txt
    python3 tools/build_kibo.py /path/to/iss.dae

Produces
    assets/kibo/kibo.glb       Kibo (JPM) only, textured, for the browser
    assets/kibo/kibo_sdf.npz   signed distance field for collisions / range sensors

Frame of the output (= simulation frame): x along the module from the Node 2
hatch (x=0) towards the airlock end cone, y to the left, z towards the
"overhead" racks. Source units are decimetres.
"""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path

import collada
import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "kibo"

# Source -> sim: x_sim = 0.1*(y - Y0), y_sim = -0.1*(x - X0), z_sim = 0.1*z.
# (A proper rotation; checked with the "To NODE 2" label and the end cone.)
X0, Y0 = 150.5, 58.4


def to_sim(v):
    return np.stack([(v[..., 1] - Y0) * 0.1, -(v[..., 0] - X0) * 0.1, v[..., 2] * 0.1], -1)


def find(node, name):
    if getattr(node, "id", None) == name:
        return node
    for c in getattr(node, "children", []):
        if isinstance(c, collada.scene.Node):
            r = find(c, name)
            if r is not None:
                return r
    return None


def load_kibo(src: str):
    d = collada.Collada(src, ignore=[collada.common.DaeUnsupportedError, collada.common.DaeBrokenRefError])
    jpm = next(r for r in (find(n, "JPM") for n in d.scene.nodes) if r is not None)
    groups = {}
    for bg in jpm.objects("geometry"):
        for prim in bg.primitives():
            if not isinstance(prim, collada.triangleset.BoundTriangleSet) or len(prim.vertex_index) == 0:
                continue
            key = prim.material.id if prim.material else "none"
            g = groups.setdefault(key, {"v": [], "uv": [], "mat": prim.material})
            g["v"].append(prim.vertex[prim.vertex_index])
            if len(prim.texcoordset):
                g["uv"].append(prim.texcoordset[0][prim.texcoord_indexset[0]])
            else:
                g["uv"].append(np.zeros(prim.vertex[prim.vertex_index].shape[:2] + (2,)))
    return groups


def build_glb(groups, srcdir: str, max_tex: int, out: Path):
    scene = trimesh.Scene()
    all_v, all_f = [], []
    n0 = 0
    for key, g in groups.items():
        v = to_sim(np.concatenate(g["v"]).reshape(-1, 3))
        uv = np.concatenate(g["uv"]).reshape(-1, 2)
        faces = np.arange(len(v)).reshape(-1, 3)
        diff = getattr(g["mat"].effect, "diffuse", None) if g["mat"] else None
        if diff is not None and hasattr(diff, "sampler"):
            im = Image.open(os.path.join(srcdir, os.path.basename(diff.sampler.surface.image.path))).convert("RGB")
            if max(im.size) > max_tex:
                im = im.resize((max_tex, max_tex), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            buf.seek(0)
            vis = trimesh.visual.TextureVisuals(uv=uv, image=Image.open(buf))
        else:
            vis = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=[180, 180, 180, 255], metallicFactor=0.0, roughnessFactor=0.9))
        scene.add_geometry(trimesh.Trimesh(vertices=v, faces=faces, visual=vis, process=False), geom_name=key)
        all_v.append(v)
        all_f.append(faces + n0)
        n0 += len(v)
        print(f"  {key:32s} {len(faces):6d} triangles")
    scene.export(out)
    print(f"  -> {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.1f} MB")
    return trimesh.Trimesh(np.concatenate(all_v), np.concatenate(all_f), process=False)


def build_sdf(mesh: trimesh.Trimesh, h: float, out: Path):
    """Signed distance (m) on a grid: >0 in the free aisle, <0 inside racks/walls."""
    lo = mesh.bounds[0] - 2 * h
    hi = mesh.bounds[1] + 2 * h
    shape = np.ceil((hi - lo) / h).astype(int)
    print(f"  grid {shape.tolist()} at {h * 100:.0f} cm")
    # 1. mark voxels touched by the surface (dense surface sampling)
    n = int(mesh.area / (h / 3) ** 2)
    pts, _ = trimesh.sample.sample_surface_even(mesh, n, radius=h / 4)
    idx = np.floor((pts - lo) / h).astype(int)
    surf = np.zeros(shape, bool)
    surf[tuple(np.clip(idx, 0, shape - 1).T)] = True
    surf = ndimage.binary_dilation(surf, iterations=1)          # close small gaps between panels
    # 2. free space. The model only has the inner surfaces of the racks (no outer
    #    hull), so a flood fill leaks through panel gaps. Instead: a voxel is free
    #    if it is visible from the module axis (y=z=0) radially AND from the module
    #    centre along x, without crossing a surface voxel.
    nx, ny, nz = shape
    ys = lo[1] + (np.arange(ny) + 0.5) * h
    zs = lo[2] + (np.arange(nz) + 0.5) * h
    th = np.linspace(0, 2 * np.pi, 1440, endpoint=False)
    rr = np.arange(0, max(abs(lo[1:]).max(), abs(hi[1:]).max()) * 1.5, h / 3)
    radial = np.zeros(shape, bool)
    # union over several axis-parallel "viewpoints", so slices where the axis itself is
    # blocked (the JEM airlock protrudes into the aisle at x = 8..8.7 m) still work
    for cy, cz in [(0, 0), (0, 0.6), (0, -0.6), (0.6, 0), (-0.6, 0), (0.5, 0.5), (-0.5, 0.5)]:
        py = cy + rr[None, :] * np.cos(th)[:, None]
        pz = cz + rr[None, :] * np.sin(th)[:, None]
        iy = np.floor((py - lo[1]) / h).astype(int)
        iz = np.floor((pz - lo[2]) / h).astype(int)
        inside = (iy >= 0) & (iy < ny) & (iz >= 0) & (iz < nz)
        iyc, izc = np.clip(iy, 0, ny - 1), np.clip(iz, 0, nz - 1)
        for i in range(nx):
            hit = surf[i][iyc, izc] | ~inside
            ok = ~np.logical_or.accumulate(hit, axis=1)
            radial[i][iyc[ok], izc[ok]] = True
    ic = int((5.0 - lo[0]) / h)
    axial = np.zeros(shape, bool)
    axial[ic:] = ~np.logical_or.accumulate(surf[ic:], axis=0)
    axial[:ic + 1] = ~np.logical_or.accumulate(surf[ic::-1], axis=0)[::-1]
    free = radial & axial
    xs = lo[0] + (np.arange(nx) + 0.5) * h
    free[xs < 0.0] = False                                     # don't fly into the Node 2 hatch tunnel
    free[:, [0, -1]] = False; free[:, :, [0, -1]] = False; free[[0, -1]] = False
    free = ndimage.binary_opening(free, iterations=1)          # remove 1-voxel spikes through panel gaps
    lab, _ = ndimage.label(free)
    seed = tuple(np.floor((np.array([5.0, 0.0, 0.0]) - lo) / h).astype(int))
    free = lab == lab[seed]
    print(f"  free volume {free.sum() * h ** 3:.1f} m^3")
    # 3. signed distance via Euclidean distance transforms
    d_out = ndimage.distance_transform_edt(free) * h            # distance to the nearest solid
    d_in = ndimage.distance_transform_edt(~free) * h            # depth inside solid
    sdf = np.where(free, d_out - h / 2, -(d_in - h / 2))
    sdf_cm = np.clip(np.round(sdf * 100), -32000, 32000).astype(np.int16)
    np.savez_compressed(out, sdf_cm=sdf_cm, origin=lo + h / 2, h=np.float64(h))
    print(f"  -> {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.1f} MB")
    return free, lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dae", help="full ISS interior COLLADA file (textures next to it)")
    ap.add_argument("--texture-size", type=int, default=4096)
    ap.add_argument("--voxel", type=float, default=0.03, help="SDF voxel size in m")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading", a.dae)
    groups = load_kibo(a.dae)
    print("writing GLB")
    mesh = build_glb(groups, os.path.dirname(os.path.abspath(a.dae)), a.texture_size, OUT / "kibo.glb")
    print("computing distance field")
    build_sdf(mesh, a.voxel, OUT / "kibo_sdf.npz")


if __name__ == "__main__":
    main()

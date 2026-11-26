"""Web server: serves the operator UI and runs the lab in real time.

Browser <-> Python over one WebSocket (/ws):
  text frames   JSON messages (telemetry, stats, keyboard, lab controls)
  binary frames [uint32 header length][JSON header][payload]
                Python -> browser: camera images (JPEG)
                browser -> Python: raw RGBA frames from the camera renderer
"""
from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path

from aiohttp import WSMsgType, web

from teleop.lab import Lab, read_results

ROOT = Path(__file__).resolve().parent.parent
DT = 0.01


def pack(header: dict, payload: bytes) -> bytes:
    h = json.dumps(header, separators=(",", ":")).encode()
    return struct.pack(">I", len(h)) + h + payload


def unpack(data: bytes):
    n = struct.unpack(">I", data[:4])[0]
    return json.loads(data[4:4 + n]), data[4 + n:]


class Server:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.clients: list[web.WebSocketResponse] = []
        self.sensor: web.WebSocketResponse | None = None   # client that renders the camera
        self.renderers: dict = {}            # ws -> visible?  (every operator tab can render)
        self.waiting_since: float | None = None             # first unanswered render request

    def choose_sensor(self, avoid=None):
        """Render the camera in a visible tab if there is one (hidden tabs may be
        throttled by the browser)."""
        cands = [w for w in self.renderers if w is not avoid] or list(self.renderers)
        cands.sort(key=lambda w: not self.renderers[w])         # visible first
        best = cands[0] if cands else None
        if self.sensor in self.renderers and self.sensor is not avoid and \
                (self.renderers[self.sensor] or best is None or not self.renderers[best]):
            return
        if best is not self.sensor:
            self.sensor = best
            self.lab.render_pending = None
            self.waiting_since = None

    async def ws_handler(self, request):
        ws = web.WebSocketResponse(max_msg_size=32 * 1024 * 1024, heartbeat=10)
        await ws.prepare(request)
        self.clients.append(ws)
        await ws.send_str(json.dumps(self.lab.info()))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    d = json.loads(msg.data)
                    if d.get("type") == "hello" and d.get("renderer"):
                        self.renderers[ws] = bool(d.get("visible", True))
                        self.choose_sensor()
                    elif d.get("type") == "visible":
                        self.renderers[ws] = bool(d.get("visible"))
                        self.choose_sensor()
                    else:
                        self.lab.handle_ui(d)
                elif msg.type == WSMsgType.BINARY:
                    try:
                        hdr, payload = unpack(msg.data)
                    except (ValueError, struct.error):     # e.g. tab closed mid-frame
                        continue
                    if hdr.get("kind") == "frame":
                        self.waiting_since = None
                        self.lab.on_frame(hdr["id"], hdr["w"], hdr["h"], payload)
        finally:
            self.clients.remove(ws)
            self.renderers.pop(ws, None)
            if self.sensor is ws:
                self.sensor = None
                self.choose_sensor()
        return ws

    async def broadcast_str(self, s: str):
        for c in list(self.clients):
            try:
                await c.send_str(s)
            except ConnectionError:
                pass

    async def flush(self):
        out, self.lab.ui_out = self.lab.ui_out, []
        if not self.clients:
            return
        batch = []
        for item in out:
            kind = item[0]
            if kind == "json":
                batch.append(item[1])
            elif kind == "bin":
                data = pack(item[1], item[2])
                for c in list(self.clients):
                    try:
                        await c.send_bytes(data)
                    except ConnectionError:
                        pass
            elif kind == "render" and self.sensor is not None:
                now = asyncio.get_running_loop().time()
                if self.waiting_since is None:
                    self.waiting_since = now
                elif now - self.waiting_since > 3.0 and len(self.renderers) > 1:
                    self.choose_sensor(avoid=self.sensor)    # this tab doesn't answer: try another one
                    self.waiting_since = None
                try:
                    await self.sensor.send_str(json.dumps({"type": "render", **item[1]}))
                except ConnectionError:
                    pass
        if batch:
            await self.broadcast_str(json.dumps({"type": "batch", "items": batch}))

    async def sim_loop(self):
        loop = asyncio.get_running_loop()
        t_next = loop.time()
        while True:
            n = 0
            while t_next <= loop.time() and n < 10:
                self.lab.tick(DT)
                t_next += DT
                n += 1
            if n == 10:                      # far behind (e.g. laptop suspended): don't try to catch up
                t_next = loop.time()
            await self.flush()
            await asyncio.sleep(max(0.0, t_next - loop.time()))

    async def results_handler(self, request):
        return web.json_response(read_results(self.lab.results_dir))

    async def on_startup(self, app):
        app["sim"] = asyncio.create_task(self.sim_loop())

    async def on_cleanup(self, app):
        app["sim"].cancel()


@web.middleware
async def no_cache(request, handler):
    """Always serve the current files - a reload after changing the code must
    never mix old and new JavaScript from the browser cache."""
    resp = await handler(request)
    if not request.path.startswith("/assets"):        # big 3D models may stay cached
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def make_app(lab: Lab) -> web.Application:
    srv = Server(lab)
    app = web.Application(middlewares=[no_cache])
    app.router.add_get("/ws", srv.ws_handler)
    app.router.add_get("/api/results", srv.results_handler)
    # The page loads its code from /web-<start time>/...: a new URL after every
    # restart, so a browser can never run stale cached JavaScript.
    ver = "web-" + lab.session.replace(".", "")

    def page(name):
        async def handler(request):
            html = (ROOT / "web" / name).read_text(encoding="utf-8").replace('"/web/', f'"/{ver}/')
            return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})
        return handler

    app.router.add_get("/", page("index.html"))
    app.router.add_get("/results", page("results.html"))
    app.router.add_static(f"/{ver}", ROOT / "web")
    app.router.add_static("/web", ROOT / "web")
    app.router.add_static("/assets", ROOT / "assets")
    app.on_startup.append(srv.on_startup)
    app.on_cleanup.append(srv.on_cleanup)
    return app


def serve(lab: Lab, host: str, port: int):
    app = make_app(lab)
    url = f"http://localhost:{port}"
    lab.results_url = f"{url}/results"
    impl, c, cam = lab.impl, lab.config, lab.robot.camera
    def src_name(s):
        if s.startswith("solutions "):
            return f"reference solution up to task {s.split(' ')[1]}"
        return {"exercises": "your code", "solutions": "reference solution", "builtin": "built-in"}[s]
    print(f"\n  Int-Ball teleop lab - step {impl.step}")
    print(f"  keyboard mapping (1): {src_name(impl.sources[1])}")
    print(f"  channel + watchdog (2): {src_name(impl.sources[2])}"
          + ("  -> ideal link, no delay or loss" if impl.sources[2] == "builtin" else ""))
    if impl.sources[2] == "builtin" and (c.delay_ms or c.jitter_ms or c.loss or lab.outages):
        print("  NOTE: --delay/--jitter/--loss/--outage have no effect before step 2 (or --solution 2)")
    else:
        print(f"  link: {c.delay_ms:g} ms delay, {c.jitter_ms:g} ms jitter, {100 * c.loss:g} % loss"
              + "".join(f", outage {s:g}s+{d:g}s" for s, d in lab.outages))
    print(f"  camera: {cam.width}x{cam.height}, {cam.fps:g} fps, JPEG q{cam.quality}"
          + (", gray" if cam.grayscale else ""))
    if lab.course:
        t = lab.world.target
        print(f"  timed task: fly to the {t.name} at the far end of Kibo,")
        print(f"  stop {t.lo[0]:g}-{t.hi[0]:g} m along the module, facing it, and hold still for {t.hold_s:g} s.")
        print("  The clock starts with your first key press.")
    print(f"\n  operator station: {url}   (Ctrl+C to stop)\n")
    web.run_app(app, host=host, port=port, print=None)

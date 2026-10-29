#!/usr/bin/env python3
"""Private interactive player for the self-built ndsrecomp runner.

This is local test tooling, not a distributed product. It launches the runner
in serve mode, boots the user-supplied ROM headlessly and presents both DS
screens in a Tk window, forwarding keyboard input.

Controls: arrows = D-pad, Z = A, X = B, Enter = Start, Backspace = Select,
A/S = L/R. Mouse click/drag on the lower screen = stylus.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from serve_capture import LOCAL, ROM, RUNNER, Server  # noqa: E402

SCALE = 2
W, H = 256, 192

KEYS = {"a": 0, "b": 1, "select": 2, "start": 3, "right": 4, "left": 5,
        "up": 6, "down": 7, "r": 8, "l": 9}

BINDINGS = {
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "z": "a", "x": "b", "Return": "start", "BackSpace": "select",
    "a": "l", "s": "r",
}


class Player:
    def __init__(self, root: tk.Tk, srv: Server, boot_cycles: int,
                 frames_per_tick: int):
        self.root = root
        self.srv = srv
        self.held: set[str] = set()
        self.last = time.time()
        self.frame_ns = 1_000_000_000 // 60
        self.cycles_per_frame = 1_100_000
        self.frames_per_tick = frames_per_tick
        self.target = boot_cycles
        self.running = True
        self.show_both = True
        self.photo_a = tk.PhotoImage(width=W, height=H)
        self.photo_b = tk.PhotoImage(width=W, height=H)

        root.title("vore-nx private desktop runtime")
        self.canvas = tk.Canvas(root, width=W * SCALE, height=H * SCALE * 2,
                                bg="black", highlightthickness=0)
        self.canvas.pack()
        self.status = tk.Label(root, anchor="w", font=("Consolas", 9))
        self.status.pack(fill="x")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_a,
                                 tags="a")
        self.canvas.create_image(0, H * SCALE, anchor="nw", image=self.photo_b,
                                 tags="b")

        root.bind("<KeyPress>", self.on_press)
        root.bind("<KeyRelease>", self.on_release)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.canvas.bind("<Button-1>", self.on_touch)
        self.canvas.bind("<B1-Motion>", self.on_touch)
        self.canvas.bind("<ButtonRelease-1>", self.on_untouch)

    # ── input ────────────────────────────────────────────────────────────
    def mask(self) -> int:
        m = 0x3FF
        for k in self.held:
            m &= ~(1 << KEYS[k])
        return m

    def send_keys(self):
        try:
            self.srv.cmd(cmd="keys", mask=self.mask())
        except Exception:
            pass

    def on_press(self, ev):
        k = BINDINGS.get(ev.keysym)
        if k:
            self.held.add(k)
            self.send_keys()

    def on_release(self, ev):
        k = BINDINGS.get(ev.keysym)
        if k:
            self.held.discard(k)
            self.send_keys()

    def on_touch(self, ev):
        y = ev.y - H * SCALE
        if y < 0:
            return
        x = max(0, min(W - 1, ev.x // SCALE))
        yy = max(0, min(H - 1, y // SCALE))
        try:
            self.srv.cmd(cmd="touch", x=x, y=yy, down=True)
        except Exception:
            pass

    def on_untouch(self, _ev):
        try:
            self.srv.cmd(cmd="touch", x=0, y=0, down=False)
        except Exception:
            pass

    # ── frame loop ───────────────────────────────────────────────────────
    def blit(self):
        for engine, photo in (("A", self.photo_a), ("B", self.photo_b)):
            if engine == "B" and not self.show_both:
                continue
            try:
                w, h, raw = self.srv.cmd_raw_framebuffer(engine)
            except Exception:
                continue
            ppm = b"P6\n%d %d\n255\n" % (w, h) + raw
            photo.configure(data=ppm)

    def tick(self):
        if not self.running:
            return
        now = time.time()
        if now - self.last < (1.0 / 30.0):
            self.root.after(5, self.tick)
            return
        self.last = now
        try:
            self.target += self.cycles_per_frame * self.frames_per_tick
            st = self.srv.cmd(cmd="run_cycles", arm9=self.target)
            if not st.get("reached"):
                self.target = max(self.target, st["cycles"][0] + 1)
            self.blit()
            self.status.configure(
                text=f"ARM9 {st['cycles'][0]//1_000_000:>6}M  "
                     f"ARM7 {st['cycles'][1]//1_000_000:>6}M   "
                     f"Z=A X=B Enter=Start arrows=move")
        except Exception as e:  # server died or window closed
            self.status.configure(text=f"stopped: {e}")
            self.running = False
            return
        self.root.after(1, self.tick)

    def close(self):
        self.running = False
        try:
            self.srv.cmd(cmd="frontend_exit")
            self.srv.close()
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    boot = int(sys.argv[1]) if len(sys.argv) > 1 else 1_200_000_000
    log = open(os.path.join(LOCAL, "serve-play-tk.log"), "wb")
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    proc = subprocess.Popen(
        [RUNNER, os.path.join(LOCAL, "runner-build"), "0",
         "--rom", ROM, "--freebios", "--boot", "direct",
         "--generated-firmware", "--no-save", "--diagnostics", "off",
         "--network", "off", "--serve", "--port", "19890"],
        cwd=os.path.join(LOCAL, "runner-build"),
        stdout=log, stderr=subprocess.STDOUT, env=env)

    root = tk.Tk()
    root.withdraw()
    deadline = time.time() + 60
    while True:
        try:
            srv = Server(19890)
            break
        except OSError:
            if proc.poll() is not None:
                print("runner exited rc=", proc.returncode, file=sys.stderr)
                return 1
            if time.time() > deadline:
                print("runner did not open the debug port", file=sys.stderr)
                return 1
            time.sleep(0.25)

    print(f"booting to {boot} ARM9 cycles ...", file=sys.stderr)
    srv.cmd(cmd="run_cycles", arm9=boot)
    print("starting interactive window", file=sys.stderr)
    root.deiconify()
    player = Player(root, srv, boot, frames_per_tick=2)
    if len(sys.argv) > 2 and sys.argv[2] == "--selftest":
        player.last = 0
        player.tick()
        root.update()
        player.close()
        log.close()
        proc.terminate()
        return 0
    root.after(50, player.tick)
    try:
        root.mainloop()
    finally:
        log.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(json.dumps(srv.cmd(cmd="ping")) if srv else "", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Per-topic link statistics measured at the receiving end (what a real operator
station could measure too: rate, throughput, latency, lost messages)."""
from __future__ import annotations

from collections import defaultdict, deque

from teleop.messages import Message


class LinkMonitor:
    def __init__(self, window_s: float = 2.0):
        self.window = window_s
        self._rx: dict[str, deque] = defaultdict(deque)      # (t_recv, size, latency)
        self._tx: dict[str, deque] = defaultdict(deque)      # (t_sent, size)
        self._seq_range: dict[str, list[int]] = {}           # [first, last] seq seen
        self._received: dict[str, int] = defaultdict(int)

    def on_send(self, msg: Message, now: float):
        self._tx[msg.topic].append((now, msg.size))

    def on_receive(self, msg: Message, now: float):
        self._rx[msg.topic].append((now, msg.size, now - msg.stamp))
        self._received[msg.topic] += 1
        r = self._seq_range.setdefault(msg.topic, [msg.seq, msg.seq])
        r[0], r[1] = min(r[0], msg.seq), max(r[1], msg.seq)

    def lost(self, topic: str) -> int:
        """Messages never received (gaps in the sequence numbers; reordering is fine)."""
        r = self._seq_range.get(topic)
        return max(0, r[1] - r[0] + 1 - self._received[topic]) if r else 0

    def _trim(self, now):
        for q in list(self._rx.values()) + list(self._tx.values()):
            while q and q[0][0] < now - self.window:
                q.popleft()

    def summary(self, now: float) -> dict:
        self._trim(now)
        out = {}
        for topic in sorted(set(self._rx) | set(self._tx)):
            rx, tx = self._rx[topic], self._tx[topic]
            n_rx = len(rx)
            lat = [r[2] for r in rx]
            lost = self.lost(topic)
            total = self._received[topic] + lost
            out[topic] = {
                "rx_hz": n_rx / self.window,
                "rx_kbps": sum(r[1] for r in rx) * 8 / 1000 / self.window,
                "tx_kbps": sum(t[1] for t in tx) * 8 / 1000 / self.window,
                "latency_ms": 1000 * sum(lat) / n_rx if n_rx else None,
                "latency_max_ms": 1000 * max(lat) if lat else None,
                "loss_pct": 100 * lost / total if total else 0.0,
                "avg_bytes": sum(r[1] for r in rx) / n_rx if n_rx else None,
            }
        return out

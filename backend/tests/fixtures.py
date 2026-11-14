"""Deterministic synthetic candles for tests (not market data)."""
import math
import random

H = 3_600_000
T0 = 1_794_643_200_000 - 300 * H


def candles(n=300, seed=7, start=100.0):
    rnd = random.Random(seed)
    t, o, h, l, c, v = [], [], [], [], [], []
    p = start
    for i in range(n):
        drift = math.sin(i / 17) * 0.004 + (0.002 if (i // 60) % 2 else -0.002)
        op = p
        cl = max(1.0, op * (1 + drift + rnd.gauss(0, 0.008)))
        hi = max(op, cl) * (1 + abs(rnd.gauss(0, 0.004)))
        lo = min(op, cl) * (1 - abs(rnd.gauss(0, 0.004)))
        # sprinkle exact patterns: dojis and engulfings
        if i % 37 == 0:
            cl = op
        t.append(T0 + i * H); o.append(op); h.append(hi); l.append(lo); c.append(cl); v.append(100 + rnd.random() * 900)
        p = cl
    return t, o, h, l, c, v

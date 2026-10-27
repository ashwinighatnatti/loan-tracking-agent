"""Correct code with style quirks only. A reviewer should report nothing here."""


def prem_close_enough(p1, p2):
    # tolerance is one dollar by design
    d = p1 - p2
    if d < 0:
        d = -d
    if d <= 1:
        return True
    else:
        return False


def fmt(n):
    s = str(n)
    r = ""
    for ch in s:
        r = r + ch
    return r

#!/usr/bin/env python3
"""Renders the animated SVG cards on github.com/ChiR24 from live GitHub + npm data.

    GITHUB_TOKEN=... python scripts/build.py     fetch data, write dist/*-{dark,light}.svg
    python scripts/build.py --offline            re-render from dist/data.json

Every SVG embeds a subset of its fonts (only the glyphs it draws), so each card is a few
KB, needs no external requests and renders the same everywhere. Runs daily in
.github/workflows/profile.yml, which publishes dist/ to the `output` branch.
Needs: pip install fonttools brotli
"""
import base64
import datetime as dt
import html
import io
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace as NS

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ASSETS = ROOT / "assets"
USER = "ChiR24"
FEATURED = "Unreal_mcp"
NPM = {"Unreal_mcp": "unreal-engine-mcp-server", "opencode-tps-meter": "opencode-tps-meter"}

# The hero graph cycles through these: prompt -> Unreal MCP tool -> editor action.
PROMPTS = [
    ("Plant a pine forest in the valley", "build_environment", "Paint Foliage"),
    ("Make the door open on approach", "manage_blueprint", "Edit Blueprint"),
    ("Add fog and drifting fireflies", "manage_effect", "Spawn Niagara FX"),
    ("Render a drone flythrough", "manage_sequence", "Render Sequence"),
]

THEMES = {
    "dark": NS(
        name="dark", bg="#0b0f15", bg2="#10161e", line="#1f2731", line2="#29323d",
        text="#e9eef3", muted="#a0aab5", faint="#6b7682",
        grid="#a8bdd4", grid_a=".04", grid_b=".075",
        node="#131a23", node_a=".95", node_line="#2c3643", node_text="#dfe5eb",
        exec="#f4f7fa", pink="#ff7ad6", teal="#3ddbb4", gold="#f7c948", blue="#5aa9ff", violet="#b79bff",
        head_ev="#c42f2b", head_fn="#2862c7", head_sw="#6f47c9", head_fade=".16",
        shadow=".55", warm=("#ffd166", "#ff8f4d", "#ff5fa0"),
        heat=("#151b23", "#0f3a5f", "#155d98", "#2585d6", "#5aa9ff"),
    ),
    "light": NS(
        name="light", bg="#f6f8fa", bg2="#ffffff", line="#d7dde3", line2="#e2e7ec",
        text="#1c2128", muted="#56606b", faint="#858f99",
        grid="#2f4a66", grid_a=".05", grid_b=".09",
        node="#ffffff", node_a="1", node_line="#d3dae1", node_text="#2a3038",
        exec="#1c2128", pink="#c02d86", teal="#0d8a6f", gold="#9a6400", blue="#0a66d8", violet="#7447d1",
        head_ev="#d9453f", head_fn="#2f6fdb", head_sw="#7a52dc", head_fade=".78",
        shadow=".10", warm=("#d97706", "#ea580c", "#db2777"),
        heat=("#e6ebf0", "#b3d4ff", "#6fb0ff", "#2f7fe8", "#0a5bc4"),
    ),
}

# ─────────────────────────────────────────────────────────────── data ──

def http(url, body=None, auth=True):
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None,
                                 {"User-Agent": USER, "Accept": "application/vnd.github+json"})
    if auth and url.startswith("https://api.github.com"):
        req.add_header("Authorization", "bearer " + os.environ["GITHUB_TOKEN"])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r), r.headers
    except urllib.error.HTTPError as e:
        if auth and body is None and e.code in (401, 403):  # Actions token refused: data is public anyway
            return http(url, auth=False)
        raise


def gql(query, **variables):
    data, _ = http("https://api.github.com/graphql", {"query": query, "variables": variables})
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


USER_Q = """query($login: String!) { user(login: $login) {
  followers { totalCount }
  contributionsCollection {
    totalCommitContributions totalPullRequestContributions totalIssueContributions
    totalPullRequestReviewContributions
    contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
  }
  repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) { nodes {
    name description createdAt stargazerCount forkCount primaryLanguage { name color }
    languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
  } }
} }"""

def npm_downloads(pkg, since):
    """All-time daily downloads, fetched in yearly chunks (the API caps ranges at 18 months)."""
    start, end, days = since, dt.date.today(), []
    while start <= end:
        stop = min(start + dt.timedelta(days=364), end)
        r, _ = http(f"https://api.npmjs.org/downloads/range/{start}:{stop}/{pkg}")
        days += [d["downloads"] for d in r["downloads"]]
        start = stop + dt.timedelta(days=1)
    return {"total": sum(days), "month": sum(days[-30:])}


def star_history(count, today):
    """Stargazer timestamps need a user token, which the Actions token isn't, so each run records
    the day's count. History = committed seed (exact, up to 2026-09-30) + earlier runs + today."""
    history = json.loads((ASSETS / "star-history.json").read_text(encoding="utf-8"))
    try:
        history |= http(f"https://raw.githubusercontent.com/{USER}/{USER}/output/data.json")[0].get("star_history", {})
    except urllib.error.HTTPError:  # nothing published yet
        pass
    history[today] = count
    return dict(sorted(history.items()))


def count_on(history, day):
    """Star count recorded on or before `day` (history maps ISO date -> count)."""
    return max(((d, c) for d, c in history.items() if d <= day.isoformat()), default=(None, 0))[1]


def fetch():
    u = gql(USER_Q, login=USER)["user"]
    repos = {r["name"]: r for r in u["repositories"]["nodes"]}
    today = dt.date.today().isoformat()
    release = http(f"https://api.github.com/repos/{USER}/{FEATURED}/releases?per_page=1")[0]
    link = http(f"https://api.github.com/repos/{USER}/{FEATURED}/contributors?per_page=1")[1].get("Link", "")
    last = re.search(r'page=(\d+)>; rel="last"', link)
    langs, colors = defaultdict(int), {}
    for r in repos.values():
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] += e["size"]
            colors[e["node"]["name"]] = e["node"]["color"] or "#8b949e"
    c = u["contributionsCollection"]
    return {
        "today": today,
        "followers": u["followers"]["totalCount"],
        "stars_total": sum(r["stargazerCount"] for r in repos.values()),
        "forks_total": sum(r["forkCount"] for r in repos.values()),
        "repos": {k: {f: r[f] for f in ("description", "createdAt", "stargazerCount", "forkCount")}
                  | {"language": (r["primaryLanguage"] or {}).get("name"),
                     "color": (r["primaryLanguage"] or {}).get("color")} for k, r in repos.items()},
        "star_history": star_history(repos[FEATURED]["stargazerCount"], today),
        "release": {"tag": release[0]["tag_name"], "date": release[0]["published_at"][:10]} if release else None,
        "contributors": int(last.group(1)) if last else 1,
        "npm": {name: npm_downloads(pkg, dt.date.fromisoformat(repos[name]["createdAt"][:10]))
                for name, pkg in NPM.items()},
        "activity": {
            "contributions": c["contributionCalendar"]["totalContributions"],
            "commits": c["totalCommitContributions"],
            "prs": c["totalPullRequestContributions"],
            "issues": c["totalIssueContributions"],
            "reviews": c["totalPullRequestReviewContributions"],
            "days": [(d["date"], d["contributionCount"])
                     for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]],
        },
        "languages": sorted(([k, v, colors[k]] for k, v in langs.items()), key=lambda x: -x[1]),
    }


def streaks(days):
    """(current, longest) runs of days with contributions; an empty today doesn't break the run."""
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    for i, (_, n) in enumerate(reversed(days)):
        if n:
            current += 1
        elif i:
            break
    return current, longest

# ────────────────────────────────────────────────────────────── fonts ──

STYLES = {  # css class -> (font file, variation axes)
    "fd": ("HubotSans.woff2", {"wght": 800, "wdth": 100}),  # display
    "fn": ("MonaSans.woff2", {"wght": 800, "wdth": 112}),   # numbers (Hubot's zero reads as a theta)
    "fx": ("MonaSans.woff2", {"wght": 400, "wdth": 100}),   # body
    "fs": ("MonaSans.woff2", {"wght": 600, "wdth": 100}),   # strong
    "fm": ("GeistMono.woff2", {"wght": 400}),                # mono
    "fb": ("GeistMono.woff2", {"wght": 600}),                # mono bold
}
_fonts = {}


def font(cls):
    """Static instance of a variable font -> (ttf bytes, advance widths in em by codepoint)."""
    if cls not in _fonts:
        file, axes = STYLES[cls]
        f = instancer.instantiateVariableFont(TTFont(ASSETS / "fonts" / file), axes)
        buf = io.BytesIO()
        f.save(buf)
        upm, hmtx = f["head"].unitsPerEm, f["hmtx"].metrics
        _fonts[cls] = buf.getvalue(), {cp: hmtx[g][0] / upm for cp, g in f.getBestCmap().items()}
    return _fonts[cls]


def measure(s, cls, size, track=0):
    adv = font(cls)[1]
    return sum(adv.get(ord(ch), .6) for ch in s) * size + track * len(s)


def font_face(cls, chars):
    # OFL: a subset is a modified font, so it must not keep the Reserved Font Name.
    f = TTFont(io.BytesIO(font(cls)[0]))
    opt = subset.Options()
    opt.flavor, opt.name_IDs, opt.layout_features = "woff2", [0, 13, 14], ["kern", "liga", "calt"]
    sub = subset.Subsetter(opt)
    sub.populate(text="".join(chars))
    sub.subset(f)
    for nid, val in ((1, f"cp-{cls}"), (2, "Regular"), (4, f"cp-{cls}"), (6, f"cp-{cls}")):
        f["name"].setName(val, nid, 3, 1, 0x409)
    buf = io.BytesIO()
    subset.save_font(f, buf, opt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:{cls};src:url(data:font/woff2;base64,{b64})}}.{cls}{{font-family:{cls}}}"

# ──────────────────────────────────────────────────────── svg helpers ──

def esc(s):
    return html.escape(str(s), quote=True)


def n(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Svg:
    """One card: markup plus the glyphs each font class needs."""

    def __init__(self, w, h, t, alt):
        self.w, self.h, self.t, self.alt = w, h, t, alt
        self.used, self.css, self.defs, self.body = defaultdict(set), [], [], []

    def text(self, x, y, s, cls, size, fill, anchor="start", track=0, attrs=""):
        return self.rich(x, y, [(s, cls, fill)], size, anchor, track, attrs)

    def rich(self, x, y, runs, size, anchor="start", track=0, attrs=""):
        """Text made of (string, font class, fill) runs on one baseline."""
        spans = []
        for s, cls, fill in runs:
            self.used[cls].update(s)
            spans.append(f'<tspan class="{cls}" fill="{fill}">{esc(s)}</tspan>')
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        ls = f' letter-spacing="{track}"' if track else ""
        return f'<text x="{n(x)}" y="{n(y)}" font-size="{size}"{a}{ls}{attrs}>{"".join(spans)}</text>'

    def frame(self, x=0, w=None, r=16):
        """Card background, clipped content group opened; close with '</g>'."""
        w, t = w or self.w, self.t
        self.defs.append(f'<clipPath id="card"><rect x="{x}" width="{w}" height="{self.h}" rx="{r}"/></clipPath>')
        return (f'<rect x="{x + .5}" y=".5" width="{w - 1}" height="{self.h - 1}" rx="{r}" fill="{t.bg}" stroke="{t.line}"/>'
                f'<g clip-path="url(#card)">')

    def __str__(self):
        faces = "".join(font_face(c, ch) for c, ch in sorted(self.used.items()))
        motion = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'height="{self.h}" role="img" aria-label="{esc(self.alt)}"><title>{esc(self.alt)}</title>'
                f'<style>{faces}{"".join(self.css)}{motion}</style><defs>{"".join(self.defs)}</defs>'
                f'{"".join(self.body)}</svg>')


def grid(t, id="grid", minor=20, major=100):
    return (f'<pattern id="{id}m" width="{minor}" height="{minor}" patternUnits="userSpaceOnUse">'
            f'<path d="M{minor} 0H0V{minor}" fill="none" stroke="{t.grid}" stroke-opacity="{t.grid_a}"/></pattern>'
            f'<pattern id="{id}" width="{major}" height="{major}" patternUnits="userSpaceOnUse">'
            f'<rect width="{major}" height="{major}" fill="url(#{id}m)"/>'
            f'<path d="M{major} 0H0V{major}" fill="none" stroke="{t.grid}" stroke-opacity="{t.grid_b}"/></pattern>')


def eyebrow(s, x, y, label, color):
    """Section label with a Blueprint data pin in the section's color."""
    return (f'<circle cx="{x + 5}" cy="{y - 4}" r="4.5" fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<circle cx="{x + 5}" cy="{y - 4}" r="2" fill="{color}"/>'
            + s.text(x + 18, y, label, "fb", 11.5, s.t.faint, track=1.8))


def chip(s, x, y, label, cls="fm", size=12, fill=None, stroke=None, color=None, pad=10, h=26):
    t = s.t
    w = measure(label, cls, size) + pad * 2
    return (f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{h}" rx="{h / 2}" fill="{fill or t.bg2}" '
            f'stroke="{stroke or t.line2}"/>' + s.text(x + pad, y + h / 2 + size * .36, label, cls, size, color or t.muted)), w


def wrap(text, cls, size, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and measure(trial, cls, size) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


def star(cx, cy, r, fill):
    pts = " ".join(f"{n(cx + (r if i % 2 == 0 else r * .47) * math.cos(-math.pi / 2 + i * math.pi / 5))},"
                   f"{n(cy + (r if i % 2 == 0 else r * .47) * math.sin(-math.pi / 2 + i * math.pi / 5))}" for i in range(10))
    return f'<polygon points="{pts}" fill="{fill}" stroke="{fill}" stroke-width="1.2" stroke-linejoin="round"/>'


def icon(kind, x, y, color, size=14):
    """Tiny line icons on a 16-unit grid."""
    k = size / 16
    paths = {
        "fork": '<circle cx="4" cy="3" r="1.8"/><circle cx="12" cy="3" r="1.8"/><circle cx="8" cy="13" r="1.8"/>'
                '<path d="M4 5v1.5a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V5M8 8.5v2.7"/>',
        "people": '<circle cx="6" cy="5" r="2.6"/><path d="M1.5 14c0-2.8 2-4.6 4.5-4.6s4.5 1.8 4.5 4.6"/>'
                  '<path d="M10.5 2.7a2.6 2.6 0 0 1 0 4.7M12.2 9.6c1.4.5 2.3 2 2.3 4.4"/>',
        "download": '<path d="M8 2v8.5M4.5 7.2 8 10.7l3.5-3.5M2.5 13.5h11"/>',
        "arrow": '<path d="M5 11 11 5M6 5h5v5"/>',
    }[kind]
    return (f'<g transform="translate({n(x)} {n(y)}) scale({k:.3f})" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{paths}</g>')


def human(v):
    return f"{v / 1000:.1f}k".replace(".0k", "k") if v >= 1000 else str(v)


def ago(date, today):
    d = (today - dt.date.fromisoformat(date)).days
    if d < 1:
        return "today"
    if d < 2:
        return "yesterday"
    if d < 14:
        return f"{d} days ago"
    if d < 60:
        return f"{d // 7} weeks ago"
    return f"{d // 30} months ago"


ICONS = json.loads((ASSETS / "icons.json").read_text(encoding="utf-8"))


def logo(slug, x, y, size, color):
    return f'<path transform="translate({n(x)} {n(y)}) scale({size / 24:.4f})" d="{ICONS[slug]}" fill="{color}"/>'

# ─────────────────────────────────────────────────────────────── hero ──

def bp_node(s, x, y, w, head, title, sub=None, ins=(), outs=(), flash=None, extra=0):
    """Unreal Blueprint node. ins/outs: (label, pin color) or (label, None) for exec pins;
    `extra` reserves rows below the pins. Returns markup, pin centres {('in'|'out', i): (x, y)}, height."""
    t = s.t
    hh = 46 if sub else 32
    rows = max(len(ins), len(outs)) + extra
    h = hh + 10 + rows * 26
    pins, g = {}, []
    g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{t.node}" fill-opacity="{t.node_a}" '
             f'stroke="{t.node_line}" filter="url(#shadow)"/>')
    g.append(f'<path d="M{x + 1} {y + hh}V{y + 9}a8 8 0 0 1 8-8H{x + w - 9}a8 8 0 0 1 8 8V{y + hh}z" fill="url(#h{head})"/>')
    g.append(f'<path d="M{x + 1} {y + hh}H{x + w - 1}" stroke="{t.node_line}"/>')
    ic = x + 17
    if head == "ev":  # event: a diamond, like UE's event icon
        g.append(f'<path d="M{ic} {y + 10}l6 6-6 6-6-6z" fill="none" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>'
                 f'<circle cx="{ic}" cy="{y + 16}" r="1.8" fill="#fff"/>')
    else:  # function: italic f in a rounded square
        g.append(f'<rect x="{ic - 7}" y="{y + 9}" width="14" height="14" rx="3.5" fill="#fff" fill-opacity=".18"/>'
                 + s.text(ic, y + 20.5, "f", "fb", 12, "#fff", "middle"))
    g.append(s.text(x + 32, y + 21, title, "fs", 13.5, "#fff"))
    if sub:
        g.append(s.text(x + 32, y + 37, sub, "fx", 11, "#fff", attrs=' fill-opacity=".72"'))
    for side, items in (("in", ins), ("out", outs)):
        for i, (label, color) in enumerate(items):
            cy = y + hh + 10 + i * 26 + 11
            px = x + 15 if side == "in" else x + w - 15
            pins[(side, i)] = (px, cy)
            if color is None:  # exec pin: filled arrow
                g.append(f'<path d="M{px - 5} {cy - 6}h5l6 6-6 6h-5z" fill="{t.exec}" stroke="{t.exec}" stroke-linejoin="round"/>')
            else:
                g.append(f'<circle cx="{px}" cy="{cy}" r="5" fill="{color}" stroke="{color}" stroke-width="1.5"/>')
            if label:
                lx, anchor = (px + 14, "start") if side == "in" else (px - 14, "end")
                g.append(s.text(lx, cy + 4.5, label, "fx", 12.5, t.node_text, anchor))
    if flash:  # debugger-style highlight when execution reaches the node
        g.append(f'<rect x="{x - 2}" y="{y - 2}" width="{w + 4}" height="{h + 4}" rx="11" fill="none" '
                 f'stroke="{t.gold}" stroke-width="2" class="{flash}" filter="url(#glow)"/>')
    return "".join(g), pins, h


def wire(a, b):
    (x1, y1), (x2, y2) = a, b
    k = max(40, (x2 - x1) * .55)
    return f"M{n(x1)} {n(y1)}C{n(x1 + k)} {n(y1)} {n(x2 - k)} {n(y2)} {n(x2)} {n(y2)}"


def hero(d, t):
    s = Svg(1000, 540, t, "Chirag Panwar: I build the tools that let AI agents build worlds. "
                          "Creator of Unreal MCP, the open-source bridge between AI assistants and Unreal Engine.")
    fade = t.head_fade
    s.defs += [
        grid(t),
        f'<radialGradient id="vig" cx="50%" cy="38%" r="75%"><stop offset=".55" stop-color="{t.bg}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{t.bg}" stop-opacity=".9"/></radialGradient>',
        f'<linearGradient id="calm" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{t.bg}" stop-opacity=".92"/>'
        f'<stop offset=".42" stop-color="{t.bg}" stop-opacity=".78"/><stop offset=".58" stop-color="{t.bg}" stop-opacity="0"/></linearGradient>',
        *(f'<linearGradient id="h{k}" x1="0" x2="1"><stop offset="0" stop-color="{c}"/><stop offset="1" stop-color="{c}" stop-opacity="{fade}"/></linearGradient>'
          for k, c in (("ev", t.head_ev), ("fn", t.head_fn), ("sw", t.head_sw))),
        f'<filter id="shadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="8" stdDeviation="10" '
        f'flood-color="#000" flood-opacity="{t.shadow}"/></filter>',
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
    ]
    s.css.append(
        ".zin{animation:zin .9s cubic-bezier(.2,.7,.2,1) both}"
        "@keyframes zin{from{opacity:0;transform:translateY(10px)}}"
        ".zp{fill:none;stroke-linecap:round;stroke-dasharray:12 140;stroke-dashoffset:12;animation:zp 2.5s linear infinite}"
        "@keyframes zp{0%{stroke-dashoffset:12}36%,100%{stroke-dashoffset:-102}}"
        ".zd{animation-delay:.9s}"
        # cycling items: negative delays keep the loop periodic from the first frame, and the
        # first prompt stays visible in static renders / reduced motion
        ".zq{opacity:0;animation:zq 10s infinite}.zq.k0{opacity:1}"
        "@keyframes zq{0%,23%{opacity:1}25%,98%{opacity:0}100%{opacity:1}}"
        ".zo{opacity:0;animation:zo 10s infinite}"
        "@keyframes zo{0%,17.5%{opacity:0}18.5%,23.5%{opacity:1}25.5%,100%{opacity:0}}"
        ".zs{fill:none;stroke-linecap:round;stroke-dasharray:14 140;stroke-dashoffset:14;animation:zs 10s linear infinite}"
        "@keyframes zs{0%,18%{stroke-dashoffset:14}26%,100%{stroke-dashoffset:-102}}"
        ".za{opacity:0;animation:za 2.5s infinite}@keyframes za{0%{opacity:1}22%,100%{opacity:0}}"
        ".zb{opacity:0;animation:zb 2.5s infinite}@keyframes zb{0%,34%{opacity:0}38%{opacity:1}62%,100%{opacity:0}}"
        ".zc{opacity:0;animation:zc 2.5s infinite}@keyframes zc{0%,70%{opacity:0}74%{opacity:1}97%,100%{opacity:0}}"
        ".zdot{animation:zdot 2s ease-in-out infinite}@keyframes zdot{50%{opacity:.35}}"
        + "".join(f".k{i}{{animation-delay:{(i - 4) * 2.5:g}s}}" for i in range(1, 4))
    )
    b = s.body
    b.append(s.frame())
    b.append(f'<rect width="1000" height="540" fill="url(#grid)"/><rect width="1000" height="540" fill="url(#calm)"/>'
             f'<rect width="1000" height="540" fill="url(#vig)"/>')
    # ── headline
    x0 = 56
    b.append(f'<g class="zin"><circle cx="{x0 + 4}" cy="60" r="4" fill="{t.teal}" class="zdot"/>'
             + s.text(x0 + 18, 64.5, "CHIRAG PANWAR", "fb", 12.5, t.muted, track=2.6)
             + s.text(944, 64.5, "Zoom 1:1", "fm", 12, t.faint, "end") + "</g>")
    size = 54
    line1, pre, hot = "I build the tools that let", "AI agents ", "build worlds."
    x_hot = x0 + measure(pre, "fd", size)
    s.defs.append(f'<linearGradient id="warm" gradientUnits="userSpaceOnUse" x1="{n(x_hot)}" x2="{n(x_hot + measure(hot, "fd", size))}">'
                  f'<stop offset="0" stop-color="{t.warm[0]}"/><stop offset=".5" stop-color="{t.warm[1]}"/>'
                  f'<stop offset="1" stop-color="{t.warm[2]}"/></linearGradient>')
    b.append(f'<g class="zin" style="animation-delay:.08s">{s.text(x0 - 2, 138, line1, "fd", size, t.text, track=-.8)}</g>')
    b.append(f'<g class="zin" style="animation-delay:.16s">'
             + s.rich(x0 - 2, 200, [(pre, "fd", t.text), (hot, "fd", "url(#warm)")], size, track=-.8) + "</g>")
    b.append(f'<g class="zin" style="animation-delay:.24s">'
             + s.rich(x0, 244, [("Creator of ", "fx", t.muted), ("Unreal MCP", "fs", t.text),
                                (", the open-source bridge between AI assistants and Unreal Engine.", "fx", t.muted)], 18)
             + "</g>")
    # ── blueprint graph
    ax, ay, bx, by, cx, cy = 56, 342, 332, 372, 628, 322
    na, pa, _ = bp_node(s, ax, ay, 200, "ev", "Event On Prompt", None,
                        outs=[("", None), ("Prompt", t.pink)], flash="za")
    nb, pb, hb = bp_node(s, bx, by, 226, "fn", "Unreal MCP", "Target is unreal gateway",
                         ins=[("", None), ("Prompt", t.pink)], outs=[("", None), ("Tool", t.blue)], flash="zb", extra=1)
    nc, pc, hc = bp_node(s, cx, cy, 236, "sw", "Unreal Editor", "Switch on Tool",
                         ins=[("", None), ("Tool", t.blue)], outs=[(p[2], None) for p in PROMPTS], flash="zc")
    wires = [(pa[("out", 0)], pb[("in", 0)], t.exec, 2.6), (pa[("out", 1)], pb[("in", 1)], t.pink, 2),
             (pb[("out", 0)], pc[("in", 0)], t.exec, 2.6), (pb[("out", 1)], pc[("in", 1)], t.blue, 2)]
    g = ['<g class="zin" style="animation-delay:.35s">']
    for a, z, color, w in wires:
        g.append(f'<path d="{wire(a, z)}" fill="none" stroke="{color}" stroke-width="{w}" stroke-opacity=".9"/>')
    for i in range(4):  # editor outputs trail off the card, "and more"
        px, py = pc[("out", i)]
        s.defs.append(f'<linearGradient id="tr{i}" gradientUnits="userSpaceOnUse" x1="{px + 8}" x2="1000">'
                      f'<stop offset="0" stop-color="{t.exec}" stop-opacity=".55"/><stop offset="1" stop-color="{t.exec}" stop-opacity="0"/></linearGradient>')
        g.append(f'<path d="M{px + 8} {py}H1000" stroke="url(#tr{i})" stroke-width="2.2"/>')
    g.append(nb + nc + na)
    g.append(f'<rect x="{bx + 10}" y="{by + hb - 31}" width="206" height="24" rx="5" fill="{t.bg}" stroke="{t.node_line}"/>')
    # prompt bubble above the event node (UE node comment style), cycling with the outputs
    bw = max(measure(f"“{p[0]}”", "fx", 14.5) for p in PROMPTS) + 34
    g.append(f'<rect x="{ax}" y="{ay - 52}" width="{n(bw)}" height="36" rx="10" fill="{t.bg2}" stroke="{t.line2}"/>'
             f'<path d="M{ax + 24} {ay - 16.5}l8 9 8-9" fill="{t.bg2}" stroke="{t.line2}"/>'
             f'<path d="M{ax + 25} {ay - 17}h14" stroke="{t.bg2}" stroke-width="2"/>')
    for i, (prompt, tool, _) in enumerate(PROMPTS):
        g.append(f'<g class="zq k{i}">' + s.rich(ax + 17, ay - 29, [("“", "fx", t.pink), (prompt, "fx", t.text), ("”", "fx", t.pink)], 14.5) + "</g>")
        # tool name on the MCP node, and the editor output it fires
        g.append(f'<g class="zq k{i}">' + s.rich(bx + 15, by + hb - 14, [("tool: ", "fm", t.faint), (tool, "fm", t.blue)], 11.5) + "</g>")
        ox, oy = pc[("out", i)]
        g.append(f'<g class="zo k{i}"><rect x="{cx + 6}" y="{oy - 12}" width="224" height="24" rx="6" fill="{t.gold}" fill-opacity=".14"/>'
                 f'<path d="M{ox - 5} {oy - 6}h5l6 6-6 6h-5z" fill="{t.gold}" filter="url(#glow)"/></g>')
        g.append(f'<path d="M{ox + 8} {oy}H1000" stroke="{t.gold}" stroke-width="3" pathLength="100" class="zs k{i}" filter="url(#glow)"/>')
    for a, z, color, w in wires[::2]:  # execution pulses
        cls = "zp" if a == pa[("out", 0)] else "zp zd"
        g.append(f'<path d="{wire(a, z)}" stroke="{t.gold}" stroke-width="4" pathLength="100" class="{cls}" filter="url(#glow)"/>')
    g.append("</g>")
    b.append("".join(g))
    b.append(f'<text x="952" y="518" font-size="34" text-anchor="end" letter-spacing="1" class="fd" fill="{t.text}" '
             f'fill-opacity=".07">BLUEPRINT</text>')
    s.used["fd"].update("BLUEPRINT")
    b.append("</g>")
    return s

# ─────────────────────────────────────────────────────────── featured ──

def star_chart(s, x, y, w, h, history, start, today, color):
    t = s.t
    days = max((today - start).days, 1)
    steps = 120
    cum = [count_on(history, start + dt.timedelta(days=round(days * i / steps))) for i in range(steps + 1)]
    top = max(max(cum), 1) * 1.08
    pts = [(x + w * i / steps, y + h - h * c / top) for i, c in enumerate(cum)]
    line = "M" + "L".join(f"{n(px)} {n(py)}" for px, py in pts)
    s.defs.append(f'<linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".32"/>'
                  f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
    s.css.append(".zl{stroke-dasharray:1;animation:zl 2.2s cubic-bezier(.3,.6,.2,1) .3s both}@keyframes zl{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
                 ".zfa{animation:zfa 1.6s ease .9s both}@keyframes zfa{from{opacity:0}}"
                 ".zr{transform-box:fill-box;transform-origin:center;animation:zr 2.4s ease-out infinite}"
                 "@keyframes zr{from{transform:scale(1);opacity:.7}to{transform:scale(3.2);opacity:0}}")
    ex, ey = pts[-1]
    guides = "".join(f'<path d="M{x} {n(y + h * f)}H{x + w}" stroke="{t.line2}" stroke-dasharray="2 5"/>' for f in (.25, .5, .75))
    return (guides + f'<path d="{line}L{x + w} {y + h}L{x} {y + h}z" fill="url(#area)" class="zfa"/>'
            f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round" pathLength="1" class="zl"/>'
            f'<circle cx="{n(ex)}" cy="{n(ey)}" r="4" fill="{color}" class="zr"/><circle cx="{n(ex)}" cy="{n(ey)}" r="4" fill="{color}"/>'
            f'<path d="M{x} {y + h}H{x + w}" stroke="{t.line2}"/>')


def featured(d, t):
    s = Svg(1000, 400, t, f"Featured project: Unreal MCP. {d['repos'][FEATURED]['stargazerCount']} stars, "
                          f"{d['repos'][FEATURED]['forkCount']} forks, {d['contributors']} contributors.")
    s.defs.append(grid(t))
    today = dt.date.fromisoformat(d["today"])
    repo = d["repos"][FEATURED]
    b = s.body
    b.append(s.frame())
    b.append(eyebrow(s, 48, 58, "FEATURED PROJECT", t.blue))
    b.append(logo("unrealengine", 48, 82, 38, t.text))
    b.append(s.text(100, 115, "Unreal MCP", "fd", 40, t.text, track=-.5))
    desc = ("An MCP server that lets AI assistants drive Unreal Engine 5 through a native C++ editor plugin. "
            "One gateway tool reaches 23 toolsets, from actors and Blueprints to Niagara, PCG and Sequencer.")
    for i, line in enumerate(wrap(desc, "fx", 16.5, 452)):
        b.append(s.text(48, 158 + i * 25.5, line, "fx", 16.5, t.muted))
    x, y = 48, 264
    for label in ("UE 5.0 – 5.8", "stdio + HTTP/SSE", "C++ · TypeScript", "MIT"):
        m, w = chip(s, x, y, label)
        if x + w > 500:  # never spill into the chart column
            break
        b.append(m)
        x += w + 8
    # install command
    cmd = "npx unreal-engine-mcp-server"
    b.append(f'<rect x="48" y="310" width="452" height="42" rx="10" fill="{t.bg2}" stroke="{t.line2}"/>'
             + s.rich(66, 336, [("$ ", "fm", t.teal), (cmd, "fm", t.text)], 14))
    b.append(f'<g transform="translate(470 322)" fill="none" stroke="{t.faint}" stroke-width="1.4">'
             f'<rect x="4" y="4" width="11" height="11" rx="2.5"/><path d="M1 11V3a2 2 0 0 1 2-2h8"/></g>')
    # star history panel
    px, py, pw, ph = 548, 32, 404, 236
    b.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="14" fill="{t.bg2}" stroke="{t.line2}"/>')
    month = count_on(d["star_history"], today) - count_on(d["star_history"], today - dt.timedelta(days=30))
    b.append(star(px + 30, py + 34, 8.5, t.gold))
    b.append(s.text(px + 46, py + 39, "STARS", "fb", 11.5, t.faint, track=1.8))
    b.append(s.text(px + 24, py + 88, f"{repo['stargazerCount']:,}", "fn", 46, t.text, track=-1))
    tag, w = chip(s, 0, 0, f"+{month} in 30 days", "fb", 11.5, fill="none", stroke=t.teal, color=t.teal, h=24)
    b.append(f'<g transform="translate({n(px + pw - 24 - w)} {py + 20})">{tag}</g>')
    start = dt.date.fromisoformat(repo["createdAt"][:10])
    b.append(star_chart(s, px + 24, py + 108, pw - 48, 96, d["star_history"], start, today, t.gold))
    b.append(s.text(px + 24, py + ph - 12, start.strftime("%b %Y"), "fm", 11, t.faint))
    b.append(s.text(px + pw - 24, py + ph - 12, "today", "fm", 11, t.faint, "end"))
    # stat tiles
    npm = d["npm"][FEATURED]
    tiles = [("fork", f"{repo['forkCount']:,}", "forks"), ("people", str(d["contributors"]), "contributors"),
             ("download", human(npm["total"]), "npm installs")]
    tw = (pw - 16) / 3
    for i, (ic, val, label) in enumerate(tiles):
        tx = px + i * (tw + 8)
        b.append(f'<rect x="{n(tx)}" y="280" width="{n(tw)}" height="72" rx="12" fill="{t.bg2}" stroke="{t.line2}"/>')
        b.append(icon(ic, tx + 18, 296, t.faint, 14))
        b.append(s.text(tx + 40, 308, label, "fm", 11.5, t.faint))
        b.append(s.text(tx + 18, 338, val, "fn", 22, t.text))
    if d["release"]:
        rel = d["release"]
        b.append(f'<circle cx="52" cy="377" r="3.5" fill="{t.teal}" class="zdot"/>')
        s.css.append(".zdot{animation:zdot 2s ease-in-out infinite}@keyframes zdot{50%{opacity:.35}}")
        b.append(s.rich(64, 381, [("Latest release ", "fm", t.faint), (rel["tag"], "fb", t.text),
                                  (f"  ·  {ago(rel['date'], today)}", "fm", t.faint)], 12))
    b.append("</g>")
    return s

# ───────────────────────────────────────────────────────────── cards ──

def project(d, t, side, name, eyebrow_label, title, desc, color, visual):
    """Half-width card. `side` picks which edge carries the gutter so a pair tiles to 1000."""
    gut = 13  # half the gap between the pair; matches the ~22px row spacing on GitHub
    x0 = 0 if side == "left" else gut
    s = Svg(500, 250, t, f"{title}: {desc}")
    repo = d["repos"][name]
    b = s.body
    b.append(s.frame(x0, 500 - gut))
    L = x0 + 32
    b.append(eyebrow(s, L, 50, eyebrow_label, color))
    b.append(icon("arrow", x0 + 500 - gut - 50, 36, t.faint, 18))
    b.append(s.text(L, 92, title, "fd", 27, t.text, track=-.3))
    for i, line in enumerate(wrap(desc, "fx", 15, 420)):
        b.append(s.text(L, 122 + i * 22, line, "fx", 15, t.muted))
    b.append(visual(s, L, 164))
    # footer: language · stars · extra
    fy = 224
    lang = repo["language"] or "-"
    b.append(f'<circle cx="{L + 5}" cy="{fy - 4}" r="5" fill="{repo["color"] or t.faint}"/>')
    b.append(s.text(L + 16, fy, lang, "fm", 12, t.muted))
    x = L + 16 + measure(lang, "fm", 12) + 22
    b.append(star(x + 6, fy - 4.5, 6, t.gold))
    b.append(s.text(x + 18, fy, f"{repo['stargazerCount']:,}", "fm", 12, t.muted))
    x += 18 + measure(f"{repo['stargazerCount']:,}", "fm", 12) + 22
    if name in d["npm"]:
        b.append(icon("download", x, fy - 12, t.muted, 13))
        b.append(s.text(x + 19, fy, f"{human(d['npm'][name]['month'])} / month", "fm", 12, t.muted))
    b.append("</g>")
    return s


def tps_visual(s, x, y):
    """A tiny live meter: equaliser bars and a readout, like the plugin's status line."""
    t = s.t
    s.css.append(".zbar{transform-box:fill-box;transform-origin:bottom;animation:zbar 1.6s ease-in-out infinite alternate}"
                 "@keyframes zbar{from{transform:scaleY(.25)}to{transform:scaleY(1)}}")
    bars = []
    for i in range(34):
        h = 6 + 14 * abs(math.sin(i * .9)) + 4 * abs(math.cos(i * 2.3))
        bars.append(f'<rect x="{x + 132 + i * 6.6:.1f}" y="{y + 30 - h:.1f}" width="3.6" height="{h:.1f}" rx="1.5" '
                    f'fill="{t.pink}" fill-opacity="{.35 + .65 * i / 34:.2f}" class="zbar" style="animation-delay:-{(i * 173) % 1600}ms"/>')
    return (f'<rect x="{x}" y="{y}" width="426" height="38" rx="9" fill="{t.bg2}" stroke="{t.line2}"/>'
            + s.rich(x + 14, y + 24, [("TPS ", "fm", t.faint), ("92.4", "fb", t.text), (" avg 78", "fm", t.faint)], 12.5)
            + "".join(bars))


def unity_visual(s, x, y):
    """LLM ⇄ MCP server ⇄ Unity Editor, with a packet bouncing along the chain."""
    t = s.t
    out, cx, stops = [], x, []
    for label in ("LLM", "MCP server", "Unity Editor"):
        m, w = chip(s, cx, y + 6, label, "fm", 12, h=26)
        out.append(m)
        stops.append((cx, cx + w))
        cx += w + 44
    for (a0, a1), (b0, b1) in zip(stops, stops[1:]):
        out.insert(0, f'<path d="M{n(a1)} {y + 19}H{n(b0)}" stroke="{t.line2}" stroke-width="2" stroke-dasharray="3 4"/>')
    span = stops[-1][0] - stops[0][1] + 12
    s.css.append(f".zpk{{animation:zpk 3.2s ease-in-out infinite alternate}}@keyframes zpk{{to{{transform:translateX({span:.0f}px)}}}}")
    out.append(f'<circle cx="{n(stops[0][1] - 6)}" cy="{y + 19}" r="4" fill="{t.violet}" class="zpk" filter="url(#glow)"/>')
    s.defs.append('<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.5" result="b"/>'
                  '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    return "".join(out)

# ─────────────────────────────────────────────────────────── toolbox ──

TOOLBOX = [("unrealengine", "Unreal"), ("unity", "Unity"), ("cplusplus", "C++"), ("csharp", "C#"),
           ("typescript", "TypeScript"), ("rust", "Rust"), ("python", "Python"), ("flutter", "Flutter"),
           ("nodedotjs", "Node.js"), ("bun", "Bun"), ("docker", "Docker"), ("modelcontextprotocol", "MCP"),
           ("claude", "Claude")]


def toolbox(d, t):
    s = Svg(1000, 178, t, "Toolbox: " + ", ".join(label for _, label in TOOLBOX))
    b = s.body
    b.append(s.frame())
    b.append(eyebrow(s, 48, 52, "TOOLBOX", t.gold))
    b.append(s.text(952, 52, "engines · languages · runtimes · AI", "fm", 11.5, t.faint, "end"))
    step = 904 / len(TOOLBOX)
    for i, (slug, label) in enumerate(TOOLBOX):
        cx = 48 + step * i + step / 2
        if slug == "csharp":  # dropped from Simple Icons; a plain hexagon mark
            hexa = " ".join(f"{n(cx + 15 * math.cos(math.pi / 6 + k * math.pi / 3))},{n(103 + 15 * math.sin(math.pi / 6 + k * math.pi / 3))}" for k in range(6))
            b.append(f'<polygon points="{hexa}" fill="{t.muted}"/>' + s.text(cx, 108, "C#", "fd", 12.5, t.bg, "middle"))
        else:
            b.append(logo(slug, cx - 15, 88, 30, t.muted))
        b.append(s.text(cx, 146, label, "fm", 11, t.faint, "middle"))
    b.append("</g>")
    return s

# ─────────────────────────────────────────────────────────── activity ──

def heatmap(t, days, x, y, w):
    """Fallback when there is no snake: the contribution calendar drawn in the card palette."""
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    cell = w / len(weeks)
    busy = sorted(c for _, c in days if c) or [1]
    quartiles = [busy[len(busy) * q // 4] for q in (1, 2, 3)]
    rects = []
    for wi, week in enumerate(weeks):
        for di, (_, c) in enumerate(week):
            lvl = 0 if not c else 1 + sum(c > q for q in quartiles)
            rects.append(f'<rect x="{n(x + wi * cell)}" y="{n(y + di * cell)}" width="{n(cell - 3)}" height="{n(cell - 3)}" rx="2.5" fill="{t.heat[lvl]}"/>')
    return "".join(rects), cell * 7


def nested_snake(path, x, y, w):
    """Platane/snk's SVG inlined into the card, cropped just below the grid (its progress
    bar, class `u`, is hidden by the caller's CSS)."""
    src = path.read_text(encoding="utf-8")
    vx, vy, vw, _ = (float(v) for v in re.search(r'<svg[^>]*viewBox="([^"]+)"', src).group(1).split())
    grid_bottom = max(float(c) for c in re.findall(r'<rect class="c[^"]*"[^>]* y="([\d.]+)"', src)) + 12
    vh = grid_bottom + 16 - vy
    inner = re.sub(r"^.*?<svg[^>]*>", "", src, count=1, flags=re.S).rsplit("</svg>", 1)[0]
    h = w * vh / vw
    return f'<svg x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" viewBox="{n(vx)} {n(vy)} {n(vw)} {n(vh)}">{inner}</svg>', h


def activity(d, t):
    a = d["activity"]
    current, longest = streaks(a["days"])
    s = Svg(1000, 10, t, f"Activity in the last 12 months: {a['contributions']:,} contributions, {a['commits']:,} commits, "
                         f"{a['prs']} pull requests, {a['reviews']} code reviews. Longest streak {longest} days.")
    b = s.body
    head = []
    head.append(eyebrow(s, 48, 52, "ACTIVITY · LAST 12 MONTHS", t.teal))
    head.append(s.rich(952, 52, [("current streak ", "fm", t.faint), (f"{current} days", "fb", t.text)], 11.5, "end"))
    stats = [(a["contributions"], "", "contributions"), (a["commits"], "", "commits"),
             (a["prs"], "", "pull requests"), (a["reviews"], "", "code reviews"),
             (longest, " days", "longest streak")]
    col = 904 / len(stats)
    for i, (v, unit, label) in enumerate(stats):
        x = 48 + i * col
        if i:
            head.append(f'<path d="M{n(x - 16)} 84V142" stroke="{t.line2}"/>')
        head.append(s.text(x, 122, f"{v:,}", "fn", 36, t.text, track=-.6))
        if unit:
            head.append(s.text(x + measure(f"{v:,}", "fn", 36, -.6) + 5, 122, unit, "fs", 15, t.faint))
        head.append(s.text(x, 144, label, "fm", 11.5, t.faint))
    # contribution graph: the snake if the workflow produced one, else a heatmap
    snake = DIST / f"snake-{t.name}.svg"
    gy = 176
    if snake.exists():
        graph, gh = nested_snake(snake, 48, gy, 904)
        s.css.append(".u{display:none}")
    else:
        graph, gh = heatmap(t, a["days"], 48, gy, 904)
    # languages
    ly = gy + gh + 34
    total = sum(v for _, v, _ in d["languages"])
    top = [(k, v / total, c) for k, v, c in d["languages"][:6]]
    rest = 1 - sum(p for _, p, _ in top)
    if rest > .001:
        top.append(("Other", rest, t.faint))
    lang = [s.text(48, ly, "LANGUAGES BY CODE SIZE", "fb", 11.5, t.faint, track=1.8)]
    x = 48
    s.defs.append(f'<clipPath id="bar"><rect x="48" y="{n(ly + 14)}" width="904" height="10" rx="5"/></clipPath>')
    segs = []
    for k, p, c in top:
        w = 904 * p
        segs.append(f'<rect x="{n(x)}" y="{n(ly + 14)}" width="{n(max(w - 2, 1))}" height="10" fill="{c}"/>')
        x += w
    lang.append(f'<g clip-path="url(#bar)">{"".join(segs)}</g>')
    x = 48
    for k, p, c in top:
        label = f"{p * 100:.1f}%"
        lang.append(f'<circle cx="{n(x + 5)}" cy="{n(ly + 45)}" r="5" fill="{c}"/>')
        lang.append(s.rich(x + 16, ly + 49.5, [(k + " ", "fm", t.muted), (label, "fm", t.faint)], 12))
        x += 16 + measure(k + " " + label, "fm", 12) + 26
    s.h = round(ly + 76)
    b.append(s.frame())
    b += head + [graph] + lang
    b.append("</g>")
    return s

# ──────────────────────────────────────────────────────────── footer ──

def footer(d, t):
    s = Svg(1000, 150, t, "Let's build something. Email cprsm24@gmail.com")
    s.defs.append(f'<linearGradient id="wl" x1="0" x2="1"><stop offset="0" stop-color="{t.exec}" stop-opacity="0"/>'
                  f'<stop offset=".5" stop-color="{t.exec}" stop-opacity=".5"/><stop offset="1" stop-color="{t.exec}" stop-opacity="0"/></linearGradient>'
                  '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/>'
                  '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    s.css.append(".zp{fill:none;stroke-linecap:round;stroke-dasharray:6 140;animation:zp 5s linear infinite}"
                 "@keyframes zp{from{stroke-dashoffset:6}to{stroke-dashoffset:-102}}")
    b = s.body
    b.append(s.frame())
    b.append('<rect width="1000" height="150" fill="url(#grid)"/>')
    s.defs.append(grid(t))
    b.append(s.text(500, 72, "Let’s build something.", "fd", 32, t.text, "middle", -.4))
    b.append(s.rich(500, 104, [("cprsm24@gmail.com", "fm", t.muted), ("   ·   ", "fm", t.faint),
                               ("rebuilt daily from live data · ", "fm", t.faint), (d["today"], "fm", t.faint)], 12.5, "middle"))
    b.append(f'<path d="M0 128H1000" stroke="url(#wl)" stroke-width="1.5"/>'
             f'<path d="M0 128H1000" stroke="{t.gold}" stroke-width="3" pathLength="100" class="zp" filter="url(#glow)"/>')
    b.append("</g>")
    return s

# ────────────────────────────────────────────────────────────── main ──

def build(d):
    DIST.mkdir(exist_ok=True)
    cards = {
        "hero": hero,
        "featured": featured,
        "tps": lambda d, t: project(d, t, "left", "opencode-tps-meter", "OPENCODE PLUGIN", "TPS Meter",
                                    "Live tokens-per-second meter for AI coding sessions, on both OpenCode generations.",
                                    t.pink, tps_visual),
        "unity": lambda d, t: project(d, t, "right", "Unity_MCP", "MCP SERVER", "Unity MCP",
                                      "The same idea for Unity: assets, scenes, scripts and play mode as MCP tools.",
                                      t.violet, unity_visual),
        "toolbox": toolbox,
        "activity": activity,
        "footer": footer,
    }
    for name, fn in cards.items():
        for theme, t in THEMES.items():
            out = str(fn(d, t))
            (DIST / f"{name}-{theme}.svg").write_text(out, encoding="utf-8")
            print(f"  {name}-{theme}.svg  {len(out) / 1024:.1f} KB")


def check():
    """Smoke test: every card is well-formed XML and makes no network requests."""
    import xml.etree.ElementTree as ET
    assert streaks([("a", 1), ("b", 2), ("c", 0), ("d", 3), ("e", 0)]) == (1, 2)
    assert streaks([("a", 1), ("b", 1), ("c", 1)]) == (3, 3)
    h = {"2026-01-01": 5, "2026-01-10": 9}
    assert [count_on(h, dt.date(2025, 12, 31)), count_on(h, dt.date(2026, 1, 5)), count_on(h, dt.date(2026, 2, 1))] == [0, 5, 9]
    for f in sorted(DIST.glob("*-*.svg")):
        text = f.read_text(encoding="utf-8")
        ET.fromstring(text)
        assert not re.search(r'(href|src)="https?:', text), f"{f.name} references the network"


if __name__ == "__main__":
    cache = DIST / "data.json"
    if "--offline" in sys.argv:
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        data = fetch()
        DIST.mkdir(exist_ok=True)
        cache.write_text(json.dumps(data, indent=1), encoding="utf-8")
    build(data)
    check()
    print("ok")

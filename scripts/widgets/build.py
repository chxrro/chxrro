"""Build the profile README's widgets (light + dark SVGs) into ../../widgets.

Run from anywhere:  GITHUB_TOKEN=... python3 scripts/widgets/build.py
Needs fonttools and brotli (pip install fonttools brotli).
Every widget shares one card system so they read as a set.
"""
import base64, io, json, math, os, pathlib, urllib.request
from fontTools.ttLib import TTFont
from fontTools import subset
import logging; logging.getLogger("fontTools").setLevel(logging.ERROR)

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "widgets"
ICONS = json.loads((HERE / "icons.json").read_text())
LOGIN = "chxrro"

# ------------------------------------------------------------------ card system
FULL, HALF = 840, 412
PAD, RADIUS = 20, 12
THEMES = {
    "light": dict(bg="#ffffff", border="#d1d9e0", ink="#1f2328", body="#3d444d", muted="#59636e",
                  tile="#f6f8fa", link="#0969da", track="#eff2f5", green="#245f46", green_soft="#e9f1ec"),
    "dark": dict(bg="#0d1117", border="#3d444d", ink="#f0f6fc", body="#d1d7e0", muted="#9198a1",
                 tile="#151b23", link="#4493f8", track="#262c36", green="#5fbf92", green_soft="#16261e"),
}
FACES = {"r": "sans-400.ttf", "m": "sans-500.ttf", "b": "sans-600.ttf"}
_fonts = {k: TTFont(HERE / "fonts" / v) for k, v in FACES.items()}


def measure(text, k, size):
    f = _fonts[k]; cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in text) * size / upm


def wrap(text, k, size, width):
    lines, cur = [], ""
    for w in text.split():
        nxt = f"{cur} {w}".strip()
        if cur and measure(nxt, k, size) > width:
            lines.append(cur); cur = w
        else:
            cur = nxt
    return lines + ([cur] if cur else [])


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def luminance(hx):
    r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class Card:
    def __init__(self, t, w, h, label):
        self.t, self.w, self.h, self.label = t, w, h, label
        self.parts, self.chars = [], {}
        self.add(f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{RADIUS}" fill="{t["bg"]}" stroke="{t["border"]}"/>')

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=14, k="r", fill=None, anchor="start"):
        self.chars.setdefault(k, set()).update(s)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="f{k}, -apple-system, Segoe UI, Helvetica, Arial, sans-serif" '
                 f'font-size="{size}"{a} fill="{fill or self.t["ink"]}">{esc(s)}</text>')
        return measure(s, k, size)

    def octicon(self, name, x, y, size=16, fill=None):
        paths = "".join(f'<path d="{d}"/>' for d in ICONS["octicon"][name]["d"])
        self.add(f'<g transform="translate({x} {y}) scale({size/16})" fill="{fill or self.t["muted"]}">{paths}</g>')

    def brand(self, slug, x, y, size=16, theme=None):
        ic = ICONS["brand"][slug]
        color = ic["hex"]
        if theme == "dark" and luminance(color) < 0.3:
            color = self.t["ink"]
        self.add(f'<g transform="translate({x} {y}) scale({size/24})"><path fill="{color}" d="{ic["d"]}"/></g>')

    def tile(self, slug, x, y, size=32, theme=None):
        self.add(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="8" fill="{self.t["tile"]}" stroke="{self.t["border"]}" stroke-opacity=".6"/>')
        ic = round(size * 0.56)
        self.brand(slug, x + (size - ic) / 2, y + (size - ic) / 2, ic, theme)

    def svg(self):
        faces = ""
        for k, chars in sorted(self.chars.items()):
            o = subset.Options(); o.flavor = "woff2"
            f = TTFont(HERE / "fonts" / FACES[k]); s = subset.Subsetter(o); s.populate(text="".join(chars)); s.subset(f)
            b = io.BytesIO(); f.flavor = "woff2"; f.save(b)
            faces += f"@font-face{{font-family:f{k};src:url(data:font/woff2;base64,{base64.b64encode(b.getvalue()).decode()}) format('woff2')}}"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{esc(self.label)}"><title>{esc(self.label)}</title><style>{faces}</style>'
                + "".join(self.parts) + "</svg>\n")


def save(name, build):
    OUT.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        (OUT / f"{name}-{theme}.svg").write_text(build(t, theme).svg())


# ------------------------------------------------------------------ data
def github_stats():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("set GITHUB_TOKEN")
    q = """query($login:String!){user(login:$login){
      repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE],includeUserRepositories:false){totalCount}
      pullRequests{totalCount} issues{totalCount}
      contributionsCollection{contributionCalendar{totalContributions}}
      repositories(ownerAffiliations:OWNER,isFork:false,first:100,privacy:PUBLIC){
        nodes{stargazerCount languages(first:20){edges{size node{name color}}}}}}}"""
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": q, "variables": {"login": LOGIN}}).encode(),
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    u = json.load(urllib.request.urlopen(req))["data"]["user"]
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            if n in {"CSS", "SCSS", "HTML", "Shell", "OpenSCAD", "Makefile", "Dockerfile"}:
                continue
            langs.setdefault(n, [0, e["node"]["color"] or "#8b949e"])[0] += e["size"]
    # square-root weighting so one large repo does not drown out the rest
    weighted = sorted(((math.sqrt(s), n, c) for n, (s, c) in langs.items()), reverse=True)[:6]
    total = sum(w for w, _, _ in weighted)
    return {
        "contributions": u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "prs": u["pullRequests"]["totalCount"], "issues": u["issues"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "langs": [(n, c, w / total) for w, n, c in weighted],
    }


# ------------------------------------------------------------------ widgets
def now_card(t, theme):
    c = Card(t, FULL, 148, "mod by Module Prep: a tutoring platform for SAT and ACT centers. moduleprep.com")
    m = ICONS["mod"]; vb = [float(v) for v in m["viewBox"].split()]
    s = 26 / vb[3]
    c.add(f'<g transform="translate({PAD - vb[0]*s:.2f} {24 - vb[1]*s:.2f}) scale({s:.4f})"><path fill="{t["ink"]}" d="{m["d"]}"/>'
          f'<circle cx="{m["dot"]["cx"]}" cy="{m["dot"]["cy"]}" r="{m["dot"]["r"]}" fill="{t["green"]}"/></g>')
    c.text(PAD + vb[2] * s + 12, 45, "by Module Prep", 14, "r", t["muted"])
    desc = ("A tutoring platform for SAT and ACT centers. It reads every answer a student gives, then assigns the "
            "next practice set with the reason attached. Tutors can change any of it.")
    for i, line in enumerate(wrap(desc, "r", 14, FULL - 2 * PAD)):
        c.text(PAD, 80 + i * 21, line, 14, "r", t["body"])
    x = PAD
    for icon, txt in (("globe", "moduleprep.com"), ("mark-github", "Module-Prep")):
        c.octicon(icon, x, 116, 14)
        x += 20 + c.text(x + 20, 127.5, txt, 12.5, "r", t["muted"]) + 20
    return c


STACK = [
    ("Languages", ["python", "typescript", "openjdk", "c", "cplusplus", "rust", "swift"]),
    ("Web", ["react", "tailwindcss", "nodedotjs", "prisma"]),
    ("Infra & design", ["docker", "vercel", "railway", "figma"]),
    ("Hardware & ML", ["pytorch", "opencv", "arduino", "espressif"]),
]
NAMES = {"openjdk": "Java", "cplusplus": "C++", "nodedotjs": "Node.js", "tailwindcss": "Tailwind CSS", "espressif": "ESP32"}


def stack_card(t, theme):
    col, right, tile, gap_y = 150, FULL - PAD, 30, 12
    rows, y = [], 20
    for label, slugs in STACK:
        x, line_y, items = col, y, []
        for slug in slugs:
            name = NAMES.get(slug, ICONS["brand"][slug]["title"])
            w = tile + 8 + measure(name, "m", 13) + 18
            if x + w - 18 > right:
                x, line_y = col, line_y + tile + 8
            items.append((slug, name, x, line_y)); x += w
        rows.append((label, y, items)); y = line_y + tile + gap_y + 8
    h = y + PAD - gap_y
    c = Card(t, FULL, h, "Tech stack. " + ". ".join(f"{l}: " + ", ".join(NAMES.get(s, ICONS['brand'][s]['title']) for s in ss) for l, ss in STACK))
    for i, (label, ry, items) in enumerate(rows):
        if i:
            c.add(f'<line x1="{PAD}" y1="{ry-10}" x2="{FULL-PAD}" y2="{ry-10}" stroke="{t["border"]}" stroke-opacity=".7"/>')
        c.text(PAD, ry + 19.5, label, 13, "m", t["muted"])
        for slug, name, x, yy in items:
            c.tile(slug, x, yy, tile, theme)
            c.text(x + tile + 8, yy + 19.5, name, 13, "m", t["ink"])
    return c


def repo_card(name, desc, meta, tech, icon="repo", private=False, h=150):
    def build(t, theme):
        c = Card(t, HALF, h, f"{name}. {desc}")
        c.octicon("lock" if private else icon, PAD, 22, 16)
        c.text(PAD + 24, 35, name, 15, "b", t["ink"] if private else t["link"])
        if meta:
            c.text(HALF - PAD, 35, meta, 12, "r", t["muted"], "end")
        for i, line in enumerate(wrap(desc, "r", 13.5, HALF - 2 * PAD)[:3]):
            c.text(PAD, 62 + i * 20, line, 13.5, "r", t["body"])
        x = PAD
        for item in tech:
            if item in ICONS["brand"]:
                c.brand(item, x, h - 32, 14, theme)
                x += 20 + c.text(x + 20, h - 20.5, NAMES.get(item, ICONS["brand"][item]["title"]), 12, "r", t["muted"]) + 14
            else:
                x += c.text(x, h - 20.5, item, 12, "r", t["muted"]) + 14
        return c
    return build


def stats_card(stats):
    rows = [("pulse", "Contributions, past year", stats["contributions"]),
            ("git-pull-request", "Pull requests", stats["prs"]),
            ("issue-opened", "Issues", stats["issues"]),
            ("repo-push", "Contributed to", stats["contributed"]),
            ("star", "Stars earned", stats["stars"])]

    def build(t, theme):
        c = Card(t, HALF, 200, "GitHub activity. " + ". ".join(f"{l}: {v}" for _, l, v in rows))
        c.text(PAD, 36, "Activity", 15, "b")
        for i, (icon, label, val) in enumerate(rows):
            y = 62 + i * 27
            c.octicon(icon, PAD, y, 16)
            c.text(PAD + 26, y + 12.5, label, 13.5, "r", t["body"])
            c.text(HALF - PAD, y + 12.5, f"{val:,}", 13.5, "b", t["ink"], "end")
        return c
    return build


def langs_card(stats):
    langs = stats["langs"]

    def build(t, theme):
        c = Card(t, HALF, 200, "Most used languages. " + ", ".join(f"{n} {p:.0%}" for n, _, p in langs))
        c.text(PAD, 36, "Most used languages", 15, "b")
        bw, x = HALF - 2 * PAD, PAD
        c.add(f'<clipPath id="bar"><rect x="{PAD}" y="56" width="{bw}" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">')
        for n, col, p in langs:
            c.add(f'<rect x="{x:.2f}" y="56" width="{bw*p+0.5:.2f}" height="8" fill="{col}"/>'); x += bw * p
        c.add("</g>")
        for i, (n, col, p) in enumerate(langs):
            cx, cy = PAD + (i % 2) * (bw / 2 + 6), 96 + (i // 2) * 30
            c.add(f'<circle cx="{cx+5}" cy="{cy-4.5}" r="5" fill="{col}"/>')
            w = c.text(cx + 16, cy, n, 13.5, "m", t["ink"])
            c.text(cx + 16 + w + 6, cy, f"{p:.1%}", 13, "r", t["muted"])
        return c
    return build


def contact_card(kind, label, value):
    def build(t, theme):
        c = Card(t, HALF, 76, f"{label}: {value}")
        if kind == "discord":
            c.tile("discord", PAD, 18, 40, theme)
        else:
            c.add(f'<rect x="{PAD}" y="18" width="40" height="40" rx="8" fill="{t["tile"]}" stroke="{t["border"]}" stroke-opacity=".6"/>')
            c.octicon("globe", PAD + 11, 29, 18, t["ink"])
        c.text(PAD + 54, 34, label, 12, "r", t["muted"])
        c.text(PAD + 54, 54, value, 15, "b", t["ink"])
        c.octicon("arrow-up-right", HALF - PAD - 16, 30, 16)
        return c
    return build


if __name__ == "__main__":
    stats = github_stats()
    save("now", now_card)
    save("stack", stack_card)
    save("p-wayfeel", repo_card("Wayfeel", "Wearable collision alerts. Ray-Ban Meta glasses stream to local depth and object models, and an ESP32 belt vibrates toward obstacles.", "HackUTD 2026", ["python", "swift", "espressif"]))
    save("p-cua-bridge", repo_card("cua-bridge", "MCP bridge for cua-driver. Replaces a ~200 MB Node gateway with a ~2 MB binary that idles at 0% CPU.", "", ["rust"]))
    save("p-teslacan", repo_card("teslacan", "Decoding, logging and sending Tesla Model 3 CAN messages from a microcontroller.", "", ["c", "arduino"]))
    save("p-scrabblebot", repo_card("scrabblebot", "Letter-auction bot with an offline simulator and learned-policy experiments.", "HackUTD 2026", ["typescript", "nodedotjs"]))
    save("p-colophon", repo_card("Colophon", "A tool to make yearbook production simpler.", "Private", ["typescript"], private=True))
    save("p-whitepaper", repo_card("Auto-aim whitepaper", "A pure calculus and telemetry based approach to auto-aiming in the 2024 FRC game.", "Gist", ["FRC 2024"], icon="book"))
    save("c-2025-bot", repo_card("2025-Bot", "Robot code for VorTX 3735's 2025 FRC season.", "Vortx3735", ["openjdk"], h=140))
    save("c-vortx-obsidian", repo_card("VorTXObsidian", "Programming lessons for VorTX, kept in an Obsidian vault and hosted on GitHub Pages.", "Vortx3735", ["typescript"], h=140))
    save("stats", stats_card(stats))
    save("languages", langs_card(stats))
    save("discord", contact_card("discord", "Discord", "churro.5"))
    save("site", contact_card("site", "Website", "chxrro.dev"))
    print("built", len(list(OUT.glob("*.svg"))), "files;", {k: v for k, v in stats.items() if k != "langs"})

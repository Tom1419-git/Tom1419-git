#!/usr/bin/env python3
"""Genere les cartes de statistiques du profil en SVG (sans service tiers).

Les images vivent dans ce depot (assets-readme/), donc elles s'affichent toujours, meme si un service externe tombe.
Source des chiffres : l'API GraphQL de GitHub, avec le jeton GH_TOKEN (ou `gh auth token` en local). Bibliotheque
standard uniquement. Sortie : stats, streak et langs, en clair et en sombre, plus stats.json.

    GH_TOKEN=... python3 scripts/gen_stats.py [Tom1419-git]
"""
import datetime as dt
import html
import json
import os
import subprocess
import sys
import urllib.request

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "Tom1419-git"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets-readme")

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount languages(first: 12, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
    contributionsCollection {
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

THEMES = {
    "light": dict(bg="#ffffff", border="#d0d7de", title="#0969da", text="#57606a", strong="#1f2328", accent="#0969da", track="#eaeef2"),
    "dark": dict(bg="#0d1117", border="#30363d", title="#58a6ff", text="#8b949e", strong="#e6edf3", accent="#58a6ff", track="#21262d"),
}


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def fetch():
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", body, {
        "Authorization": "bearer " + token(), "Content-Type": "application/json", "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data or not data.get("data", {}).get("user"):
        raise SystemExit("GraphQL: " + json.dumps(data.get("errors", data))[:300])
    return data["data"]["user"]


def streaks(days):
    """(serie en cours, plus longue serie) sur les jours du calendrier. Aujourd'hui sans contribution ne casse pas la serie."""
    counts = [(dt.date.fromisoformat(d["date"]), d["contributionCount"]) for d in days]
    longest = run = 0
    for _, c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    cur = 0
    i = len(counts) - 1
    if i >= 0 and counts[i][1] == 0:
        i -= 1
    while i >= 0 and counts[i][1] > 0:
        cur += 1
        i -= 1
    return cur, longest


def card(w, h, t, title, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
            f'<style>text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}</style>'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="8" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<text x="24" y="36" font-size="17" font-weight="600" fill="{t["title"]}">{html.escape(title)}</text>{inner}</svg>')


def stats_svg(t, rows):
    out = []
    for i, (label, value) in enumerate(rows):
        y = 72 + i * 28
        out.append(f'<text x="24" y="{y}" font-size="14" fill="{t["text"]}">{html.escape(label)}</text>'
                   f'<text x="320" y="{y}" font-size="14" font-weight="600" fill="{t["strong"]}" text-anchor="end">{value}</text>')
    return card(340, 72 + len(rows) * 28 - 6, t, "Statistiques GitHub", "".join(out))


def streak_svg(t, total, cur, longest):
    cols = [(total, "Contributions (12 mois)"), (cur, "Série en cours (jours)"), (longest, "Plus longue série (jours)")]
    out = []
    for i, (v, label) in enumerate(cols):
        x = 24 + i * 150
        out.append(f'<text x="{x}" y="100" font-size="30" font-weight="700" fill="{t["strong"]}">{v}</text>'
                   f'<text x="{x}" y="126" font-size="12" fill="{t["text"]}">{html.escape(label)}</text>')
    return card(495, 150, t, "Régularité", "".join(out))


def langs_svg(t, langs):
    total = sum(s for _, s, _ in langs) or 1
    x, bar, leg = 24, [], []
    for i, (name, size, color) in enumerate(langs):
        w = max(2.0, 292 * size / total)
        bar.append(f'<rect x="{x:.1f}" y="56" width="{w:.1f}" height="10" fill="{color}"/>')
        x += w
        col, row = i % 2, i // 2
        leg.append(f'<circle cx="{30 + col * 150}" cy="{92 + row * 24}" r="5" fill="{color}"/>'
                   f'<text x="{42 + col * 150}" y="{96 + row * 24}" font-size="13" fill="{t["strong"]}">{html.escape(name)}'
                   f' <tspan fill="{t["text"]}">{100 * size / total:.1f}%</tspan></text>')
    clip = f'<clipPath id="c"><rect x="24" y="56" width="292" height="10" rx="5"/></clipPath>'
    h = 92 + ((len(langs) + 1) // 2) * 24 + 12
    return card(340, h, t, "Langages les plus utilisés", clip + f'<g clip-path="url(#c)">{"".join(bar)}</g>' + "".join(leg))


def main():
    u = fetch()
    cc = u["contributionsCollection"]
    cal = cc["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    cur, longest = streaks(days)
    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    agg = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]
            a = agg.setdefault(n["name"], [0, n["color"] or "#8b949e"])
            a[0] += e["size"]
    langs = sorted(((n, s, c) for n, (s, c) in agg.items()), key=lambda x: -x[1])[:8]
    rows = [("Contributions (12 mois)", cal["totalContributions"]), ("Commits", cc["totalCommitContributions"]),
            ("Pull requests", cc["totalPullRequestContributions"]), ("Issues", cc["totalIssueContributions"]),
            ("Dépôts publics", u["repositories"]["totalCount"]), ("Étoiles reçues", stars), ("Abonnés", u["followers"]["totalCount"])]
    os.makedirs(OUT, exist_ok=True)
    for name, t in THEMES.items():
        for fn, svg in (("stats", stats_svg(t, rows)), ("streak", streak_svg(t, cal["totalContributions"], cur, longest)),
                        ("langs", langs_svg(t, langs))):
            with open(os.path.join(OUT, f"{fn}-{name}.svg"), "w", encoding="utf-8") as f:
                f.write(svg)
    with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as f:
        json.dump({"login": LOGIN, "date": dt.date.today().isoformat(), "contributions": cal["totalContributions"],
                   "streak": cur, "longest": longest, "repos": u["repositories"]["totalCount"],
                   "langs": [[n, round(100 * s / (sum(x[1] for x in langs) or 1), 1)] for n, s, _ in langs]}, f, ensure_ascii=False, indent=1)
    print("ok", cal["totalContributions"], cur, longest, [n for n, _, _ in langs])


if __name__ == "__main__":
    main()

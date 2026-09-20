"""HTML for the board. Streamlit has no native element that puts a team
logo, a player headshot, a line, a projection and an edge bar on one dense
row, so the game panels are hand-built markup; everything else in the app is
a native widget."""
from __future__ import annotations

import html

# nflverse abbreviation -> the slug ESPN's logo CDN uses
ESPN_SLUG = {"WAS": "wsh", "LA": "lar"}

SHIELD = "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"


def logo(abbr: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ESPN_SLUG.get(abbr, (abbr or '').lower())}.png"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def american(odds) -> str:
    if odds is None:
        return "--"
    return f"+{odds:.0f}" if odds > 0 else f"{odds:.0f}"


STYLE = """
<style>
:root {
  --ink:      #08080A;
  --panel:    #101014;
  --panel-2:  #16161C;
  --rule:     #2A2A33;
  --text:     #EDEDED;
  --dim:      #7A7A88;
  --acid:     #C6FF00;
  --hot:      #FF2D7E;
  --cyan:     #00E5FF;
}

/* ---- slate header -------------------------------------------------- */
.np-head { display:flex; align-items:center; gap:18px; border-bottom:3px solid var(--acid);
           padding:4px 0 14px; margin-bottom:22px; }
.np-head img { height:54px; filter:drop-shadow(0 0 10px rgba(198,255,0,.25)); }
.np-head .t { font-family:Anton,Impact,sans-serif; font-size:40px; line-height:.95;
              letter-spacing:.5px; text-transform:uppercase; }
.np-head .t em { font-style:normal; color:var(--acid); }
.np-head .s { color:var(--dim); font-size:13px; letter-spacing:2.5px;
              text-transform:uppercase; margin-top:4px; }

/* ---- one game ------------------------------------------------------ */
.np-game { border:1px solid var(--rule); background:var(--panel); margin-bottom:26px; }
.np-bar  { display:flex; align-items:stretch; background:var(--panel-2);
           border-bottom:1px solid var(--rule); flex-wrap:wrap; }
.np-side { display:flex; align-items:center; gap:11px; padding:13px 17px; min-width:250px; flex:1; }
.np-side img { height:40px; width:40px; object-fit:contain; }
.np-abbr { font-family:Anton,Impact,sans-serif; font-size:25px; letter-spacing:1px; }
.np-where{ font-family:'Space Mono',monospace; font-size:10px; color:var(--dim);
           letter-spacing:1.5px; vertical-align:middle; }
.np-imp  { font-family:'Space Mono',monospace; font-size:11px; color:var(--dim); }
.np-imp b { color:var(--text); font-weight:700; }
.np-mid  { display:flex; flex-direction:column; justify-content:center; align-items:center;
           padding:10px 22px; border-left:1px solid var(--rule); border-right:1px solid var(--rule);
           min-width:150px; }
.np-mid .k { font-family:'Space Mono',monospace; font-size:16px; color:var(--acid); font-weight:700; }
.np-mid .v { font-size:10px; color:var(--dim); letter-spacing:1.6px; text-transform:uppercase; }

/* defense read chip */
.np-read { display:inline-block; font-size:10px; letter-spacing:1.3px; text-transform:uppercase;
           padding:3px 8px; border:1px solid currentColor; transform:skewX(-11deg);
           font-weight:700; margin-top:4px; }
.np-read span { display:inline-block; transform:skewX(11deg); }
.read-pass { color:var(--cyan); }
.read-run  { color:var(--acid); }
.read-soft { color:var(--hot); }
.read-stiff{ color:var(--dim); }
.read-bal  { color:var(--dim); }

/* ---- prop rows ----------------------------------------------------- */
.np-row { display:grid; grid-template-columns:44px minmax(150px,1.5fr) 128px 84px 84px 1fr 86px;
          align-items:center; gap:12px; padding:9px 16px;
          border-bottom:1px solid rgba(42,42,51,.55); }
.np-row:last-child { border-bottom:none; }
.np-row:hover { background:rgba(198,255,0,.035); }
.np-row.flagged { opacity:.42; }

.np-face { width:40px; height:40px; object-fit:cover; background:var(--panel-2);
           border:1px solid var(--rule); }
.np-who  { min-width:0; }
.np-name { font-weight:700; font-size:14px; white-space:nowrap; overflow:hidden;
           text-overflow:ellipsis; }
.np-meta { font-size:10.5px; color:var(--dim); letter-spacing:.7px; text-transform:uppercase; }
.np-mkt  { font-size:10px; letter-spacing:1.1px; text-transform:uppercase; color:var(--dim);
           border-left:2px solid var(--rule); padding-left:9px; }

.np-num  { font-family:'Space Mono',monospace; text-align:right; }
.np-num .big { font-size:16px; font-weight:700; display:block; line-height:1.15; }
.np-num .cap { font-size:9px; color:var(--dim); letter-spacing:1.3px; text-transform:uppercase; }
.proj .big { color:var(--cyan); }

/* edge bar */
.np-bar-wrap { display:flex; align-items:center; gap:9px; }
.np-track { position:relative; flex:1; height:7px; background:#1C1C24; min-width:60px; }
.np-fill  { position:absolute; top:0; bottom:0; left:0; }
.fill-over  { background:var(--acid); }
.fill-under { background:var(--hot); }
.np-why { font-size:10px; color:var(--dim); white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }

.np-call { text-align:right; font-family:'Space Mono',monospace; }
.np-side-tag { font-size:11px; font-weight:700; letter-spacing:1.4px; }
.tag-over  { color:var(--acid); }
.tag-under { color:var(--hot); }
.np-edge { font-size:17px; font-weight:700; display:block; line-height:1.15; }
.np-odds { font-size:10px; color:var(--dim); }

.np-flagnote { grid-column:3 / -1; font-size:10.5px; color:var(--hot); letter-spacing:.5px; }
.np-empty { padding:16px; color:var(--dim); font-size:13px; }

@media (max-width: 900px) {
  .np-row { grid-template-columns:38px 1fr 76px 76px; }
  .np-mkt, .np-bar-wrap { display:none; }
}
</style>
"""

_READ_CLASS = {
    "pass funnel": "read-pass",
    "run funnel": "read-run",
    "soft all over": "read-soft",
    "stiff all over": "read-stiff",
    "balanced": "read-bal",
}


def header(season: int, week: int, book: str, n_props: int) -> str:
    return (
        f'<div class="np-head"><img src="{SHIELD}" alt="NFL">'
        f'<div><div class="t">Prop <em>Board</em></div>'
        f'<div class="s">{season} &middot; week {week} &middot; {esc(book)} '
        f'&middot; {n_props} priced</div></div></div>'
    )


def _side(abbr: str, implied: float, read: str, home: bool) -> str:
    cls = _READ_CLASS.get(read, "read-bal")
    where = "home" if home else "away"
    return (
        f'<div class="np-side"><img src="{logo(abbr)}" alt="{esc(abbr)}">'
        f'<div><div class="np-abbr">{esc(abbr)} '
        f'<span class="np-where">{where}</span></div>'
        f'<div class="np-imp">implied <b>{implied:.1f}</b></div>'
        f'<div class="np-read {cls}"><span>{esc(read)}</span></div></div></div>'
    )


def game_panel(game: dict, props: list[dict], away_read: str, home_read: str) -> str:
    spread = game["spread"]
    fav = f'{game["home"]} -{spread:g}' if spread > 0 else f'{game["away"]} -{abs(spread):g}'
    if spread == 0:
        fav = "pick 'em"

    rows = "".join(_prop_row(p) for p in props) or (
        '<div class="np-empty">No props clear the filters for this game.</div>')

    return (
        '<div class="np-game">'
        '<div class="np-bar">'
        + _side(game["away"], game["implied_away"], away_read, home=False)
        + f'<div class="np-mid"><div class="k">{game["total"]:g}</div>'
          f'<div class="v">total</div>'
          f'<div class="k" style="margin-top:6px">{esc(fav)}</div>'
          f'<div class="v">spread</div></div>'
        + _side(game["home"], game["implied_home"], home_read, home=True)
        + '</div>' + rows + '</div>'
    )


def _prop_row(p: dict) -> str:
    over = p["side"] == "OVER"
    tag = "tag-over" if over else "tag-under"
    fill = "fill-over" if over else "fill-under"
    # 25 points of edge fills the bar
    width = max(2.0, min(100.0, abs(p["edge"]) * 400))

    if p["market"] == "anytime_td":
        line_cell = (f'<div class="np-num"><span class="big">'
                     f'{p["market_prob"] * 100:.0f}%</span>'
                     f'<span class="cap">book</span></div>')
        proj_cell = (f'<div class="np-num proj"><span class="big">'
                     f'{p["our_prob"] * 100:.0f}%</span>'
                     f'<span class="cap">ours</span></div>')
    else:
        line_cell = (f'<div class="np-num"><span class="big">{p["line"]:g}</span>'
                     f'<span class="cap">line</span></div>')
        proj_cell = (f'<div class="np-num proj"><span class="big">'
                     f'{p["projection"]:.1f}</span><span class="cap">proj</span></div>')

    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')

    status = f' &middot; <span style="color:#FF8A00">{esc(p["status"])}</span>' if p["status"] else ""
    why = esc(_why(p))

    if not p["playable"]:
        detail = f'<div class="np-flagnote">set aside &mdash; {esc(p["reason"])}</div>'
    else:
        detail = (
            f'<div class="np-bar-wrap"><div class="np-track">'
            f'<div class="np-fill {fill}" style="width:{width:.0f}%"></div></div>'
            f'<div class="np-why">{why}</div></div>'
            f'<div class="np-call"><span class="np-side-tag {tag}">{p["side"]}</span>'
            f'<span class="np-edge {tag}">{p["edge"] * 100:+.1f}</span>'
            f'<span class="np-odds">{american(p["over"] if over else p["under"])}</span></div>'
        )

    return (
        f'<div class="np-row{"" if p["playable"] else " flagged"}">'
        f'{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])} '
        f'vs {esc(p["opponent"])}{status}</div></div>'
        f'<div class="np-mkt">{esc(p["market_label"])}</div>'
        f'{line_cell}{proj_cell}{detail}</div>'
    )


def _why(p: dict) -> str:
    """One line on what actually moved the number."""
    bits = []
    mult = p["def_mult"]
    if abs(mult - 1) >= 0.03:
        verb = "softer" if mult > 1 else "tougher"
        bits.append(f'{p["opponent"]} D {abs(mult - 1) * 100:.0f}% {verb}')
    margin = p["script"]["margin"]
    if abs(margin) >= 3:
        bits.append("favoured by %.0f" % margin if margin > 0 else "dog by %.0f" % -margin)
    if p["delta"] is not None and abs(p["delta"]) >= 1:
        bits.append(f'{p["delta"]:+.0f} yd vs line')
    if p["cur_share"] < 0.30:
        bits.append(f'{p["cur_share"] * 100:.0f}% this season')
    return "  /  ".join(bits) if bits else "no strong matchup lean"

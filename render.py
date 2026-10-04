"""HTML for the board. Streamlit has no native element that puts a team
logo, a player headshot, our number, the book's number and a written reason
on one dense row, so the panels are hand-built markup; everything else in
the app is a native widget.

The layout is deliberately ordered: who, what we think he does, why we think
it, and only then what the book has posted. The price is a reference column,
never the headline.
"""
from __future__ import annotations

import datetime as dt
import html

import model
import weather

# nflverse abbreviation -> the slug ESPN's logo CDN uses
ESPN_SLUG = {"WAS": "wsh", "LA": "lar"}

SHIELD = "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"

# how many reasons fit on a row before it stops being readable
MAX_DRIVERS = 3


def logo(abbr: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ESPN_SLUG.get(abbr, (abbr or '').lower())}.png"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def american(odds) -> str:
    if odds is None:
        return "--"
    return f"+{odds:.0f}" if odds > 0 else f"{odds:.0f}"


def kickoff(game: dict) -> str:
    """"Thursday 8:15 PM" -- the slot the game actually comes on in.

    nfldata stores gameday as YYYY-MM-DD and gametime as 24h Eastern, which
    is how everyone talks about the slate anyway ("the 1 o'clock games").
    A game with no posted time sorts last and says so.
    """
    day, clock = game.get("gameday", ""), game.get("gametime", "")
    try:
        d = dt.date.fromisoformat(day)
    except ValueError:
        return "Kickoff TBD"
    name = d.strftime("%A")
    try:
        h, m = (int(x) for x in clock.split(":")[:2])
    except ValueError:
        return f"{name}, time TBD"
    suffix = "AM" if h < 12 else "PM"
    return f"{name} {(h - 1) % 12 + 1}:{m:02d} {suffix}"


def slot_key(game: dict) -> tuple:
    """What makes two games the same kickoff window. Sorting on this puts
    Thursday first, then the 1 o'clock block, the 4 o'clocks, and so on."""
    return (game.get("gameday", "9999-99-99"), game.get("gametime", "99:99"))


# the scale itself lives in model.py, next to what produces it
confidence_word = model.confidence_word


STYLE = """
<style>
:root {
  --ink:      #08080A;
  --panel:    #101014;
  --panel-2:  #16161C;
  --rule:     #2A2A33;
  --text:     #EDEDED;
  --dim:      #7A7A88;
  --dimmer:   #55555F;
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

/* ---- section rule -------------------------------------------------- */
.np-sect { display:flex; align-items:baseline; gap:14px; margin:6px 0 14px; }
.np-sect .h { font-family:Anton,Impact,sans-serif; font-size:24px; letter-spacing:.8px;
              text-transform:uppercase; color:var(--hot); }
.np-sect .d { font-size:11.5px; color:var(--dim); letter-spacing:.4px; }

/* ---- kickoff window ------------------------------------------------ */
.np-slot { display:flex; align-items:center; gap:12px; margin:26px 0 12px; }
.np-slot .w { font-family:Anton,Impact,sans-serif; font-size:17px; letter-spacing:1.4px;
              text-transform:uppercase; color:var(--acid); white-space:nowrap; }
.np-slot .n { font-family:'Space Mono',monospace; font-size:10px; color:var(--dim);
              letter-spacing:1.2px; text-transform:uppercase; white-space:nowrap; }
.np-slot .r { flex:1; height:1px; background:var(--rule); }

/* ---- one game ------------------------------------------------------ */
/* A <details> so a game opens and closes with no rerun -- clicking a
   header must not cost a round trip through Streamlit. */
.np-game { border:1px solid var(--rule); background:var(--panel); margin-bottom:10px;
  /* Sixteen games of props is most of a megabyte of markup. This lets the
     browser skip laying out and painting the ones that are off-screen until
     you scroll to them -- the page arrives in one piece either way, it just
     does not do the work up front. `auto` on the intrinsic size means it
     remembers how tall each panel actually was, so the scrollbar does not
     jump around once you have been past a game. */
  content-visibility:auto; contain-intrinsic-size:auto 68px; }
.np-game > summary { cursor:pointer; list-style:none; display:block; }
.np-game > summary::-webkit-details-marker { display:none; }
.np-game > summary::marker { content:""; }
.np-game[open] > .np-bar, .np-game[open] > summary > .np-bar {
  border-bottom:1px solid var(--rule); }
.np-game > summary:hover .np-abbr { color:var(--acid); }
.np-bar  { display:flex; align-items:stretch; background:var(--panel-2); flex-wrap:wrap; }

/* right end of the header: the headline read, so a closed game still says
   something, plus the count and the caret */
.np-tail { display:flex; align-items:center; gap:14px; padding:13px 18px;
           border-left:1px solid var(--rule); margin-left:auto;
           min-width:0; max-width:300px; }
.np-tail .c { font-family:'Space Mono',monospace; font-size:10px; color:var(--dim);
              letter-spacing:1.3px; text-transform:uppercase; text-align:right;
              min-width:0; }
.np-tail .c b { color:var(--text); font-weight:700; }
.np-lead { font-family:'Space Grotesk',system-ui,sans-serif; font-size:12px;
           letter-spacing:0; text-transform:none; color:var(--text); font-weight:700;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.np-lead em { font-style:normal; color:var(--cyan); }
.np-caret { font-size:13px; color:var(--acid); transition:transform .12s ease; }
.np-game[open] .np-caret { transform:rotate(90deg); }
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

/* the forecast, under the spread. Quiet in a dome or on a calm day; it only
   takes a colour when it is the kind of day that moves the number. */
.np-wx { font-family:'Space Mono',monospace; font-size:10px; letter-spacing:1px;
         text-transform:uppercase; color:var(--dimmer); margin-top:8px; white-space:nowrap; }
.np-wx.calm   { color:var(--dim); }
.np-wx.wet    { color:var(--cyan); }
.np-wx.rough  { color:var(--acid); }

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
.np-row { display:grid;
          grid-template-columns:44px minmax(132px,1.1fr) 104px 96px 88px minmax(200px,1.9fr) 76px;
          align-items:center; gap:12px; padding:10px 16px;
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
/* Quiet by design: it qualifies the read, it is not a recommendation. */
.np-tag  { font-size:9px; font-weight:700; letter-spacing:.8px; text-transform:uppercase;
           color:var(--dim); border:1px solid var(--rule); border-radius:3px;
           padding:1px 4px; margin-left:5px; vertical-align:1.5px; }
.np-mkt  { font-size:10px; letter-spacing:1.1px; text-transform:uppercase; color:var(--dim);
           border-left:2px solid var(--rule); padding-left:9px; }

/* our number leads; the book's sits beside it, smaller and grey */
.np-ours { font-family:'Space Mono',monospace; text-align:right; }
.np-ours .big { font-size:21px; font-weight:700; color:var(--cyan); display:block;
                line-height:1.1; }
.np-ours .cap { font-size:9px; color:var(--cyan); opacity:.75; letter-spacing:1.5px;
                text-transform:uppercase; }
.np-book { font-family:'Space Mono',monospace; text-align:right; color:var(--dimmer); }
.np-book .big { font-size:13px; font-weight:700; display:block; line-height:1.15; }
.np-book .cap { font-size:9px; letter-spacing:1.3px; text-transform:uppercase; }
.np-gap { font-size:10px; font-weight:700; }
.gap-over  { color:var(--acid); }
.gap-under { color:var(--hot); }

/* the reasons */
.np-why  { min-width:0; }
.np-drv  { font-size:11px; color:#B6B6C2; line-height:1.45; white-space:nowrap;
           overflow:hidden; text-overflow:ellipsis; }
.np-drv i { font-style:normal; font-weight:700; margin-right:5px; }
.up   { color:var(--acid); }
.down { color:var(--hot); }
.flat { color:var(--dimmer); }

/* confidence meter */
.np-conf { text-align:right; }
.np-pips { display:flex; gap:2px; justify-content:flex-end; margin-bottom:3px; }
.np-pip  { width:9px; height:6px; background:#23232C; }
.np-pip.on { background:var(--acid); }
.np-conf .w { font-size:9px; color:var(--dim); letter-spacing:.9px; text-transform:uppercase; }

/* a set-aside row keeps our number and the book's; the note takes the
   place of the reasons and the pip meter */
.np-flagnote { grid-column:6 / -1; font-size:10.5px; color:var(--hot); letter-spacing:.5px; }
.np-empty { padding:16px; color:var(--dim); font-size:13px; }

/* ---- scorers leaderboard ------------------------------------------- */
.np-board { border:1px solid var(--rule); background:var(--panel); margin-bottom:30px; }
.np-sc { display:grid;
         grid-template-columns:40px 42px minmax(140px,1.1fr) 132px 92px 84px minmax(180px,1.7fr);
         align-items:center; gap:12px; padding:10px 16px;
         border-bottom:1px solid rgba(42,42,51,.55); }
.np-sc:last-child { border-bottom:none; }
.np-sc:hover { background:rgba(255,45,126,.05); }
.np-rank { font-family:Anton,Impact,sans-serif; font-size:23px; color:var(--hot);
           text-align:center; line-height:1; }
.np-rank.cool { color:var(--dimmer); }
.np-game-of { font-size:10.5px; color:var(--dim); letter-spacing:.9px; text-transform:uppercase; }
.np-game-of b { color:var(--text); font-weight:700; }

@media (max-width: 1000px) {
  .np-lead { display:none; }
  .np-tail { border-left:none; padding:6px 18px 13px; }
  .np-row { grid-template-columns:38px 1fr 92px 84px; }
  .np-mkt, .np-why, .np-conf { display:none; }
  .np-flagnote { grid-column:1 / -1; }
  .np-sc  { grid-template-columns:34px 38px 1fr 88px 80px; }
  .np-game-of, .np-sc .np-why { display:none; }
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

_LEAN_MARK = {1: ('<i class="up">&#9650;</i>', ""),
              -1: ('<i class="down">&#9660;</i>', ""),
              0: ('<i class="flat">&#8226;</i>', "")}


def header(season: int, week: int, book: str, n_props: int) -> str:
    return (
        f'<div class="np-head"><img src="{SHIELD}" alt="NFL">'
        f'<div><div class="t">Prop <em>Board</em></div>'
        f'<div class="s">{season} &middot; week {week} &middot; our read '
        f'&middot; {n_props} players &middot; {esc(book)} shown for reference</div></div></div>'
    )


def section(title: str, note: str) -> str:
    return (f'<div class="np-sect"><div class="h">{esc(title)}</div>'
            f'<div class="d">{esc(note)}</div></div>')


def _pips(conf: float) -> str:
    on = max(1, min(5, round(conf * 5 + 0.0001)))
    cells = "".join(f'<div class="np-pip{" on" if i < on else ""}"></div>' for i in range(5))
    return (f'<div class="np-conf"><div class="np-pips">{cells}</div>'
            f'<div class="w">{esc(confidence_word(conf))}</div></div>')


def _drivers_html(p: dict, limit: int = MAX_DRIVERS) -> str:
    rows = []
    for d in p.get("drivers", [])[:limit]:
        mark = _LEAN_MARK.get(d.get("lean", 0), _LEAN_MARK[0])[0]
        rows.append(f'<div class="np-drv">{mark}{esc(d["text"])}</div>')
    return f'<div class="np-why">{"".join(rows)}</div>' if rows else '<div class="np-why"></div>'


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


def slot_header(label: str, n_games: int) -> str:
    """The rule that separates one kickoff window from the next."""
    return (f'<div class="np-slot"><div class="w">{esc(label)}</div>'
            f'<div class="n">{n_games} game{"" if n_games == 1 else "s"}</div>'
            f'<div class="r"></div></div>')


def game_panel(game: dict, props: list[dict], away_read: str, home_read: str,
               expanded: bool = False) -> str:
    """One game, closed by default.

    The header is a <summary>, so the whole matchup bar is the click target
    and the browser handles opening it. Streamlit's own expander would work
    too, but it cannot hold this markup as its label and every click would
    rerun the script.
    """
    spread = game["spread"]
    fav = f'{game["home"]} -{spread:g}' if spread > 0 else f'{game["away"]} -{abs(spread):g}'
    if spread == 0:
        fav = "pick 'em"

    rows = "".join(_prop_row(p) for p in props) or (
        '<div class="np-empty">No props clear the filters for this game.</div>')
    live = sum(1 for p in props if p["playable"])

    wx_text = weather.describe(game.get("weather"))
    wx = (f'<div class="np-wx {weather.mood(game.get("weather"))}">{esc(wx_text)}</div>'
          if wx_text else "")

    return (
        f'<details class="np-game"{" open" if expanded else ""}>'
        '<summary><div class="np-bar">'
        + _side(game["away"], game["implied_away"], away_read, home=False)
        + f'<div class="np-mid"><div class="k">{game["total"]:g}</div>'
          f'<div class="v">total</div>'
          f'<div class="k" style="margin-top:6px">{esc(fav)}</div>'
          f'<div class="v">spread</div>{wx}</div>'
        + _side(game["home"], game["implied_home"], home_read, home=True)
        + f'<div class="np-tail"><div class="c">{_headline(props)}'
          f'<b>{live}</b> read{"" if live == 1 else "s"}</div>'
          f'<div class="np-caret">&#9654;</div></div>'
        + '</div></summary>' + rows + '</details>'
    )


def _headline(props: list[dict]) -> str:
    """The one read a closed game leads with. Props arrive already sorted --
    playable first, affirmative first, strongest first -- so it is the top
    of that list, and it is our number, never the book's."""
    lead = next((p for p in props if p["playable"] and p["side"] == "OVER"), None)
    if lead is None:
        return ""
    if lead["market"] == "anytime_td":
        what = f'{lead["our_prob"] * 100:.0f}% to score'
    elif lead["market"] in ("pass_tds", "interceptions"):
        what = f'{lead["projection"]:.2f} {lead["market_label"].lower()}'
    else:
        what = f'{lead["projection"]:.0f} {lead["market_label"].lower()}'
    return (f'<div class="np-lead">{esc(lead["player"])} '
            f'<em>{esc(what)}</em></div>')


def _our_cell(p: dict) -> str:
    """What we think happens. Always the biggest thing on the row."""
    if p["market"] == "anytime_td":
        return (f'<div class="np-ours"><span class="big">{p["our_prob"] * 100:.0f}%</span>'
                f'<span class="cap">to score</span></div>')
    if p["market"] in ("pass_tds", "interceptions"):
        return (f'<div class="np-ours"><span class="big">{p["projection"]:.2f}</span>'
                f'<span class="cap">we project</span></div>')
    return (f'<div class="np-ours"><span class="big">{p["projection"]:.0f}</span>'
            f'<span class="cap">yards</span></div>')


def _book_cell(p: dict) -> str:
    """The market, kept small and grey on purpose."""
    if p["market"] == "anytime_td":
        body = (f'<span class="big">{p["market_prob"] * 100:.0f}%</span>'
                f'<span class="cap">book {american(p["over"])}</span>')
    else:
        gap = p["delta"]
        tail = ""
        if gap is not None and abs(gap) >= 0.5:
            cls = "gap-over" if gap > 0 else "gap-under"
            tail = f'<span class="np-gap {cls}">{gap:+.0f} vs line</span><br>'
        # the line leads; the two prices sit under it so the odds are on the
        # row and not just the number they are attached to
        body = (f'<span class="big">{p["line"]:g}</span>{tail}'
                f'<span class="cap">o{american(p["over"])} u{american(p["under"])}</span>')
    return f'<div class="np-book">{body}</div>'


def _tag(p: dict) -> str:
    """A rookie's read is built on a handful of games by definition, and the
    pip meter says the read is short without saying why. Naming it is the
    difference between a number you distrust and one you can place. The same
    goes for a player promoted by someone else's injury: his volume is
    inferred from the depth chart, not watched."""
    tags = ""
    if p.get("rookie"):
        tags += ' <span class="np-tag">rookie</span>'
    if p.get("promoted"):
        tags += ' <span class="np-tag">next man up</span>'
    return tags


def _prop_row(p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    status = (f' &middot; <span style="color:#FF8A00">{esc(p["status"])}</span>'
              if p["status"] else "")
    if not p["playable"]:
        # Our number and the book's stay on the row: the note is about the
        # gap between them, and a player the book has priced is on the page
        # with his odds whatever we make of him.
        detail = (_our_cell(p) + _book_cell(p)
                  + f'<div class="np-flagnote">set aside &mdash; {esc(p["reason"])}</div>')
    else:
        detail = _our_cell(p) + _book_cell(p) + _drivers_html(p) + _pips(p["confidence"])

    return (
        f'<div class="np-row{"" if p["playable"] else " flagged"}">'
        f'{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}{_tag(p)}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])} '
        f'vs {esc(p["opponent"])}{status}</div></div>'
        f'<div class="np-mkt">{esc(p["market_label"])}</div>'
        f'{detail}</div>'
    )


def scorer_board(rows: list[dict]) -> str:
    """Everyone on the slate ranked by our probability that they score."""
    if not rows:
        return '<div class="np-board"><div class="np-empty">No scorers priced yet.</div></div>'
    return '<div class="np-board">' + "".join(
        _scorer_row(i + 1, p) for i, p in enumerate(rows)) + '</div>'


def _scorer_row(rank: int, p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    cool = "" if rank <= 10 else " cool"
    return (
        f'<div class="np-sc">'
        f'<div class="np-rank{cool}">{rank}</div>{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}{_tag(p)}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])}</div></div>'
        f'<div class="np-game-of"><b>{esc(p["team"])}</b> vs {esc(p["opponent"])}<br>'
        f'{p["script"]["implied"]:.1f} implied pts &middot; '
        f'{esc(confidence_word(p["confidence"]))}</div>'
        + _our_cell(p) + _book_cell(p) + _drivers_html(p, 2) +
        f'</div>'
    )


def yardage_board(rows: list[dict]) -> str:
    """One market ranked by our projection, biggest first."""
    if not rows:
        return '<div class="np-board"><div class="np-empty">Nothing priced for that market.</div></div>'
    return '<div class="np-board">' + "".join(
        _yardage_row(i + 1, p) for i, p in enumerate(rows)) + '</div>'


def _yardage_row(rank: int, p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    cool = "" if rank <= 10 else " cool"
    return (
        f'<div class="np-sc">'
        f'<div class="np-rank{cool}">{rank}</div>{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}{_tag(p)}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])}</div></div>'
        f'<div class="np-game-of"><b>{esc(p["team"])}</b> vs {esc(p["opponent"])}<br>'
        f'{esc(confidence_word(p["confidence"]))}</div>'
        + _our_cell(p) + _book_cell(p) + _drivers_html(p, 2) +
        f'</div>'
    )

import datetime as dt

import streamlit as st

import board
import lines
import model
import render

st.set_page_config(page_title="NFL prop board", page_icon="🏈", layout="wide")

SEASON = 2026


@st.cache_data(ttl=60 * 60 * 6, show_spinner="Pulling nflverse game logs...")
def load_stats(season: int):
    return board.load_stats(season)


@st.cache_data(ttl=60 * 10, show_spinner="Pulling lines...")
def load_lines(season: int, week: int, book_id: int):
    return lines.fetch(season, week, book_id)


def current_week(schedule: list[dict]) -> int:
    """The week whose games have not all kicked off yet."""
    today = dt.date.today().isoformat()
    upcoming = [g["week"] for g in schedule if g["gameday"] >= today]
    return min(upcoming) if upcoming else max(g["week"] for g in schedule)


# --- fast UI first, slow pulls after ---------------------------------------
st.html(render.STYLE)
header_slot = st.container()
body_slot = st.container()

stats = load_stats(SEASON)
schedule = stats["schedule"]
weeks = sorted({g["week"] for g in schedule})

with st.sidebar:
    st.subheader("Board")
    week = st.selectbox("Week", weeks, index=weeks.index(current_week(schedule)))
    book = st.segmented_control("Book", ["DraftKings", "FanDuel"],
                                default="DraftKings", key="book")
    book = book or "DraftKings"

    st.divider()
    picked = st.pills(
        "Markets",
        list(lines.MARKET_LABELS),
        format_func=lambda k: lines.MARKET_LABELS[k],
        selection_mode="multi",
        default=list(lines.MARKET_LABELS),
    )
    min_edge = st.slider("Minimum edge", 0.0, 25.0, 4.0, 0.5,
                         format="%.1f%%",
                         help="Our probability minus the book's, with the vig taken out.")
    side = st.segmented_control("Side", ["Both", "Over", "Under"], default="Both")
    show_flagged = st.toggle(
        "Show set-aside props", value=False,
        help="Props where the line implies a role our game logs cannot see, "
             "or the player is listed out. Shown greyed, never ranked.")

    st.divider()
    st.caption(
        f"Defense reads blend {SEASON} with {SEASON - 1}, weighted toward "
        f"this season. Lines from BettingPros; stats from nflverse.")

market_lines = load_lines(SEASON, week, lines.BOOKS[book])
data = board.build(SEASON, week, book, stats, market_lines)

# --- filter ----------------------------------------------------------------
wanted = set(picked or lines.MARKET_LABELS)
kept_games, shown = [], 0
for game in data["games"]:
    props = [p for p in game["props"] if p["market"] in wanted]
    if side != "Both":
        props = [p for p in props if p["side"] == side.upper()]
    props = [p for p in props
             if (p["playable"] and p["edge"] * 100 >= min_edge)
             or (show_flagged and not p["playable"])]
    if props:
        shown += sum(1 for p in props if p["playable"])
        kept_games.append((game, props))

kept_games.sort(key=lambda gp: -max((p["edge"] for p in gp[1] if p["playable"]), default=-1))

with header_slot:
    st.html(render.header(SEASON, week, book, shown))

with body_slot:
    if not kept_games:
        st.info("No props clear that edge. Lower the minimum, or the books "
                "may not have posted this week's numbers yet.")
    for game, props in kept_games:
        st.html(render.game_panel(
            game, props,
            model.funnel_label(game["def_away"]),
            model.funnel_label(game["def_home"]),
        ))

    with st.expander("How the number is built"):
        st.markdown(f"""
Every projection is **player baseline × opponent defense × game environment**.

- **Player baseline** — per-game volume and efficiency from {SEASON - 1}–{SEASON}
  game logs, weighted toward recent games. Efficiency and scoring rates are
  pulled toward the position average until a player has enough games to have
  earned his own.
- **Opponent defense** — yards allowed *per play*, not per game, so a defense
  is not punished for its own offense leaving it on the field. Split into pass
  and run, and again by the position being covered. The gap between the two is
  the funnel read in each game header.
- **Game environment** — the implied team total from the spread and total.
  Favourites run more and throw less.

The edge is our probability minus the book's with the vig removed. Yardage
markets use a normal spread that includes how little we may know about a
player; touchdowns and interceptions use Poisson.

Nothing here is fitted to past results, and it has not been backtested.
""")
        if data["unmatched"]:
            st.caption(f"{len(data['unmatched'])} market entries had no game log "
                       f"to price against (team props, and players yet to take a snap).")

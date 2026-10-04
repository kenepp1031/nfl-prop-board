import collections

import streamlit as st

import board
import lines
import model
import render
import weather

st.set_page_config(page_title="NFL Props", page_icon="🏈", layout="wide")

SEASON = 2026


# refresh_mode="background" on both pulls: when the TTL runs out, the next
# person through the door gets the board they were going to get anyway and
# the refresh happens behind them. Without it, whoever happens to click
# first after the clock expires pays the whole pull while staring at a
# spinner. Prop lines a couple of minutes stale are worth far more than a
# blocked page.
@st.cache_data(ttl=60 * 60 * 6, refresh_mode="background",
               show_spinner="Pulling nflverse game logs...")
def load_stats(season: int):
    return board.load_stats(season)


@st.cache_data(ttl=60 * 10, refresh_mode="background",
               show_spinner="Pulling lines...")
def load_offers(season: int, week: int):
    """The slow half of the market pull, and it is book-agnostic: one offer
    arrives with DraftKings' price and FanDuel's on it. Cached by week alone
    so flipping the book costs nothing."""
    return lines.raw_offers(season, week)


@st.cache_data(ttl=60 * 10)
def load_lines(season: int, week: int, book_id: int):
    return lines.price(load_offers(season, week), book_id)


@st.cache_data(ttl=60 * 60 * weather.FORECAST_HOURS, refresh_mode="background",
               show_spinner="Pulling the forecast...")
def load_weather(season: int, week: int):
    """The week's forecasts, one per outdoor game. A board without them is
    still a board, so a refused pull is an empty dict, not an error page."""
    try:
        return weather.forecasts(season, week)
    except Exception:
        return {}


# --- fast UI first, slow pulls after ---------------------------------------
# st.html() sanitises with DOMPurify, which drops <style> blocks outright --
# the whole theme silently disappears and the board renders as raw logos.
# st.markdown keeps them. Everything else we emit goes through st.html.
st.markdown(render.STYLE, unsafe_allow_html=True)
header_slot = st.container()
body_slot = st.container()

stats = load_stats(SEASON)
schedule = stats["schedule"]
weeks = sorted({g["week"] for g in schedule})

VIEWS = ["Who scores", "Top projections", "By game"]

with st.sidebar:
    st.subheader("Board")
    view = st.radio("View", VIEWS, index=0,
                    help="Who scores and Top projections rank the whole slate "
                         "on our number. By game is the full matchup board.")
    week = st.selectbox("Week", weeks,
                        index=weeks.index(board.current_week(schedule)))
    book = st.segmented_control("Book", ["DraftKings", "FanDuel"],
                                default="DraftKings", key="book")
    book = book or "DraftKings"
    st.caption("The book only sets which lines are shown beside our number. "
               "It never picks a side or changes the order.")

    st.divider()
    if view == "Top projections":
        ranked_market = st.selectbox(
            "Market", [m for m in lines.MARKET_LABELS if m != "anytime_td"],
            format_func=lambda k: lines.MARKET_LABELS[k])
        picked = [ranked_market]
    elif view == "Who scores":
        picked = ["anytime_td"]
    else:
        picked = st.pills(
            "Markets",
            list(lines.MARKET_LABELS),
            format_func=lambda k: lines.MARKET_LABELS[k],
            selection_mode="multi",
            default=list(lines.MARKET_LABELS),
        )

    min_conf = st.select_slider(
        "Least I will look at",
        options=[w for _, w in reversed(model.CONF_WORDS)],
        value="fair read",
        help="How much of the read is actually earned: how many games we have "
             "on the player, how much of it is from this season, and how many "
             "games we have on the defense.")
    show_flagged = st.toggle(
        "Show set-aside props", value=False,
        help="Props where the line implies a role our game logs cannot see, "
             "or the player is listed out. Shown greyed, never ranked.")
    if view == "By game":
        open_all = st.toggle(
            "Open every game", value=False,
            help="Off, the games are collapsed to their headers and you click "
                 "one to see its reads.")
    else:
        open_all = False

    st.divider()
    st.caption(
        f"Defense reads blend {SEASON} with {SEASON - 1}, weighted toward "
        f"this season. Lines from BettingPros; stats and injury reports from "
        f"nflverse; forecasts from Open-Meteo.")

floor = dict((w, f) for f, w in model.CONF_WORDS)[min_conf]

market_lines = load_lines(SEASON, week, lines.BOOKS[book])
data = board.build(SEASON, week, book, stats, market_lines,
                   weather=load_weather(SEASON, week))


def keep(p: dict) -> bool:
    if not p["playable"]:
        return show_flagged
    return p["confidence"] >= floor


# --- filter ----------------------------------------------------------------
wanted = set(picked or lines.MARKET_LABELS)
kept_games, shown = [], 0
for game in data["games"]:
    props = [p for p in game["props"] if p["market"] in wanted and keep(p)]
    if props:
        shown += sum(1 for p in props if p["playable"])
        kept_games.append((game, props))

# Kickoff order: Thursday, the 1 o'clock block, the 4 o'clocks, Sunday night,
# Monday. It used to lead with the strongest read, which meant the game you
# were about to watch could be buried halfway down the page.
kept_games.sort(key=lambda gp: render.slot_key(gp[0]))

with header_slot:
    st.html(render.header(SEASON, week, book, shown))

with body_slot:
    if view == "Who scores":
        rows = [p for _, props in kept_games for p in props
                if p["playable"] and p["market"] == "anytime_td"]
        rows.sort(key=lambda p: -p["our_prob"])
        st.html(render.section(
            "Most likely to score",
            "Ranked by our probability that he reaches the end zone. "
            "The book's price is the grey column."))
        st.html(render.scorer_board(rows[:50]))

    elif view == "Top projections":
        label = lines.MARKET_LABELS[picked[0]]
        rows = [p for _, props in kept_games for p in props if p["playable"]]
        rows.sort(key=lambda p: -p["projection"])
        st.html(render.section(
            f"Most {label.lower()}",
            "Ranked by our projection, biggest first, with the reason beside it."))
        st.html(render.yardage_board(rows[:40]))

    else:
        if not kept_games:
            st.info("Nothing clears that read. Drop the threshold, or the books "
                    "may not have posted this week's numbers yet.")
        # One block, not one per game: Streamlit puts a gap between elements,
        # and with the games collapsed those gaps are most of the page.
        slots = collections.Counter(render.kickoff(g) for g, _ in kept_games)
        parts, current = [], None
        for game, props in kept_games:
            slot = render.kickoff(game)
            if slot != current:
                parts.append(render.slot_header(slot, slots[slot]))
                current = slot
            parts.append(render.game_panel(
                game, props,
                model.funnel_label(game["def_away"]),
                model.funnel_label(game["def_home"]),
                expanded=open_all,
            ))
        st.html("".join(parts))

    with st.expander("How the number is built"):
        st.markdown(f"""
Every projection is **player baseline × opponent defense × game environment**,
and every row shows which of the three actually moved it.

- **Player baseline** — per-game volume and efficiency from {SEASON - 1}–{SEASON}
  game logs, weighted toward recent games. Efficiency and scoring rates are
  pulled toward the position average until a player has enough games to have
  earned his own. Scoring is per *touch*, so a backup does not inherit a
  starter's touchdown rate.
- **Opponent defense** — yards allowed *per play*, not per game, so a defense
  is not punished for its own offense leaving it on the field. Split into pass
  and run, and again by the position being covered. The gap between the two is
  the funnel read in each game header.
- **Game environment** — the implied team total from the spread and the total.
  Favourites run more and throw less.
- **Weather** — the forecast over the game window at outdoor venues. Wind
  over 10 mph, rain, snow and freezing cold each take throws away and make
  the ones that are thrown worth less, and push carries up. The matchup bar
  shows the forecast; a row says so when it moved the number.

**Injuries** are this week's report only. Out and doubtful set a player's
props aside; questionable, or a missed practice before the Friday
designations are out, is a tag on the row for you to weigh.

**Next man up.** When a starter is out or on reserve, the depth chart says
where his touches go: most of a lead back's carries to the second back, a
receiver's targets spread over everyone else who catches passes. The player
promoted into the lineup carries a *next man up* tag and a lighter pip
meter, because his role is inferred rather than watched.

**The book does not get a vote.** The line is printed beside our number so you
can see the two side by side, but it never picks a side and never changes the
order. Rows are ranked on our own read and on how much of that read we have
earned — games on the player, how much of it is from this season, and games on
the defense. That is the pip meter on the right.

Nothing here is fitted to past results, and it has not been backtested.
""")
        if data["unmatched"]:
            st.caption(f"{len(data['unmatched'])} market entries had no game log "
                       f"to price against (team props, and players yet to take a snap).")

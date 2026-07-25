"""Render assets/architecture.png from the system described in ARCHITECTURE.md.

Kept as a script so the diagram is reproducible and reviewable in git rather
than a binary someone hand-edited once. Uses matplotlib only (no graphviz
binary required).

    python scripts/render_architecture.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "assets" / "architecture.png"

BG = "#ffffff"
INK = "#12161c"
MUTED = "#5b6673"

CLIENT, CLIENT_EDGE = "#e8f1fb", "#3f7fc4"
SERVER, SERVER_EDGE = "#eaf6ee", "#3f9d63"
MODEL, MODEL_EDGE = "#f6ecfb", "#8a55b8"
TOOL, TOOL_EDGE = "#fdf1e3", "#c9832f"
DATA, DATA_EDGE = "#f1f2f4", "#7b8794"

LINE_H = 0.30


def box(ax, x, y, w, h, title, lines=(), face=DATA, edge=DATA_EDGE, title_size=12, body_size=9.2):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            linewidth=1.6,
            facecolor=face,
            edgecolor=edge,
        )
    )
    block_h = 0.52 + len(lines) * LINE_H
    top = y + h / 2 + block_h / 2
    ax.text(x + w / 2, top - 0.22, title, ha="center", va="center",
            fontsize=title_size, fontweight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, top - 0.60 - i * LINE_H, line, ha="center", va="center",
                fontsize=body_size, color=MUTED)


def arrow(ax, points, label=None, label_xy=None, color=INK, dashed=False, both=False):
    style = "<|-|>" if both else "-|>"
    for i in range(len(points) - 1):
        seg_style = style if i == len(points) - 2 else "-"
        ax.add_patch(
            FancyArrowPatch(
                points[i],
                points[i + 1],
                arrowstyle=seg_style,
                mutation_scale=13,
                linewidth=1.5,
                color=color,
                linestyle="--" if dashed else "-",
                shrinkA=0,
                shrinkB=0,
            )
        )
    if label and label_xy:
        ax.text(label_xy[0], label_xy[1], label, ha="center", va="center",
                fontsize=8.6, color=MUTED)


def main() -> None:
    W, H = 17.6, 10.2
    fig, ax = plt.subplots(figsize=(W, H), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    ax.text(0.3, 9.85, "Kitchen Assistant — Executive Sous-Chef", fontsize=17,
            fontweight="bold", color=INK, ha="left")
    ax.text(0.3, 9.48,
            "One LiveGateway per browser connection proxies audio and video to Gemini Live; "
            "every tool runs server-side against a single session store.",
            fontsize=10, color=MUTED, ha="left")

    # ---- row A: client / gateway / model ---------------------------------
    box(ax, 0.3, 6.5, 3.9, 2.6, "Browser client",
        ["mic → AudioWorklet → PCM16 16 kHz",
         "speaker ← PCM16 24 kHz queue",
         "camera → JPEG frame every ~1.5 s",
         "static/ · vanilla JS, served at /",
         "frontend/ · React HUD, at /hud"],
        face=CLIENT, edge=CLIENT_EDGE, body_size=8.8)

    box(ax, 6.9, 6.5, 4.6, 2.6, "FastAPI session gateway",
        ["app/main.py — /ws/voice/{session_id}",
         "app/auth.py — APP_AUTH_TOKEN gate",
         "app/live/gateway.py · LiveGateway",
         "uplink + downlink asyncio tasks",
         "session resumption, GoAway reconnect"],
        face=SERVER, edge=SERVER_EDGE, body_size=8.8)

    box(ax, 13.9, 6.5, 3.5, 2.6, "Gemini Live API",
        ["google-genai · aio.live.connect",
         "native audio in / out, server VAD",
         "barge-in + live transcription",
         "function calling → tool_call",
         "context-window compression"],
        face=MODEL, edge=MODEL_EDGE, body_size=8.8)

    # browser <-> gateway
    arrow(ax, [(4.2, 8.35), (6.9, 8.35)], "PCM16 16 kHz  ↑", (5.55, 8.52))
    arrow(ax, [(6.9, 7.85), (4.2, 7.85)], "PCM16 24 kHz  ↓", (5.55, 8.02))
    arrow(ax, [(4.2, 7.35), (6.9, 7.35)], "user.text · video.frame", (5.55, 7.52))
    arrow(ax, [(6.9, 6.85), (4.2, 6.85)], "transcript · timer · state", (5.55, 7.02))

    # gateway <-> gemini
    arrow(ax, [(11.5, 8.1), (13.9, 8.1)], "send_realtime_input", (12.7, 8.27))
    arrow(ax, [(13.9, 7.5), (11.5, 7.5)], "audio · transcript · tool_call", (12.7, 7.67))

    # ---- row B: tool registry --------------------------------------------
    box(ax, 6.9, 4.35, 10.5, 1.65, "ToolRegistry · app/tools/registry.py",
        ["FunctionDeclaration ⇄ async callable · session_id and services injected at dispatch, never model-visible",
         "set_kitchen_timer · cancel_timer · list_timers · convert_units · scale_recipe · navigate_steps · search_recipes · load_recipe"],
        face=TOOL, edge=TOOL_EDGE, body_size=8.8)

    arrow(ax, [(15.1, 6.5), (15.1, 6.0)], "tool_call", (14.45, 6.25))
    arrow(ax, [(16.2, 6.0), (16.2, 6.5)], "send_tool_response", (16.85, 6.25))

    # ---- row C: implementations ------------------------------------------
    box(ax, 6.9, 2.85, 10.5, 1.1, "cooking_tools · app/tools/cooking_tools.py",
        ["pure async functions — no module globals; every dependency arrives as an argument"],
        face=TOOL, edge=TOOL_EDGE, body_size=8.8)
    arrow(ax, [(12.15, 4.35), (12.15, 3.95)])

    # ---- row D: services --------------------------------------------------
    box(ax, 0.3, 0.45, 4.4, 1.85, "StateManager",
        ["app/state_manager.py",
         "RecipeState per session_id",
         "atomic update() behind a lock",
         "in-memory | optional Redis",
         "gateway reads it for state.snapshot"],
        face=SERVER, edge=SERVER_EDGE, body_size=8.6)

    box(ax, 5.1, 0.45, 3.6, 1.85, "TimerEngine",
        ["app/services/timer_engine.py",
         "real asyncio countdowns",
         "keyed (session_id, timer_id)",
         "expiry → gateway callback"],
        face=TOOL, edge=TOOL_EDGE, body_size=8.6)

    box(ax, 9.1, 0.45, 3.9, 1.85, "RecipeStore (RAG)",
        ["app/services/recipe_store.py",
         "DuckDB data/recipes.db",
         "gemini-embedding-001, 3072-d",
         "array_distance + vss index"],
        face=TOOL, edge=TOOL_EDGE, body_size=8.6)

    box(ax, 13.6, 0.45, 3.8, 1.85, ".gemini/skills",
        ["recipe-scaler",
         "timer-manager",
         "authored specs behind",
         "the scaling + timer tools"],
        face=DATA, edge=DATA_EDGE, body_size=8.6)

    arrow(ax, [(8.7, 2.85), (2.5, 2.30)], "read / atomic update", (4.35, 2.74))
    arrow(ax, [(10.9, 2.85), (6.9, 2.30)], "start / cancel", (9.15, 2.72))
    arrow(ax, [(13.1, 2.85), (11.05, 2.30)], "search / get_recipe", (13.75, 2.60))
    arrow(ax, [(15.5, 2.30), (15.5, 2.85)], dashed=True, color=DATA_EDGE)

    # proactive timer expiry loop, routed up the empty corridor
    arrow(ax, [(5.4, 2.30), (5.4, 6.15), (6.9, 6.15)],
          "timer expiry → announce unprompted", (3.0, 6.30), color=TOOL_EDGE, dashed=True)

    ax.text(0.3, 0.12,
            "Regenerate with:  python scripts/render_architecture.py     "
            "Full component contracts and ADRs: ARCHITECTURE.md",
            fontsize=8.2, color=MUTED, ha="left")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=BG, bbox_inches="tight", pad_inches=0.22)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

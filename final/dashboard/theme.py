"""Shared look for every member's charts, so the dashboard looks like one app."""
BLUE = "#2a78d6"          # single-series charts
GRAY = "#9a9a96"          # "unknown" / de-emphasized categories
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e6e3"
# Ordered categories (e.g. older -> newer) use light -> dark shades of one hue.
BLUE_SEQUENTIAL = ["#a9c9f2", "#5f9be6", "#1f5aa6"]


def style(fig, title, height=420):
    """Apply the shared layout to a Plotly figure."""
    fig.update_layout(
        title={"text": title, "x": 0, "xanchor": "left", "font": {"size": 16, "color": TEXT}},
        template="plotly_white",
        height=height,
        margin={"l": 10, "r": 20, "t": 60, "b": 10},
        font={"family": "Arial, sans-serif", "size": 13, "color": MUTED},
        hoverlabel={"bgcolor": "white", "font_size": 13},
        bargap=0.35,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig

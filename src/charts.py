import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_candlestick_chart(
    ohlc_df: pd.DataFrame,
    symbol: str,
    year_high: float = 0,
    year_low: float = 0,
) -> go.Figure:
    if ohlc_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No chart data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=ohlc_df["date"],
            open=ohlc_df["open"],
            high=ohlc_df["high"],
            low=ohlc_df["low"],
            close=ohlc_df["close"],
            name=symbol,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    # 52-week high/low reference lines
    if year_high > 0:
        fig.add_hline(
            y=year_high,
            line_dash="dash",
            line_color="rgba(255,165,0,0.6)",
            annotation_text=f"52W High: ₹{year_high:,.2f}",
            annotation_position="top right",
            row=1,
            col=1,
        )
    if year_low > 0:
        fig.add_hline(
            y=year_low,
            line_dash="dash",
            line_color="rgba(100,149,237,0.6)",
            annotation_text=f"52W Low: ₹{year_low:,.2f}",
            annotation_position="bottom right",
            row=1,
            col=1,
        )

    # Volume bars
    colors = [
        "#26a69a" if c >= o else "#ef5350"
        for c, o in zip(ohlc_df["close"], ohlc_df["open"])
    ]
    fig.add_trace(
        go.Bar(
            x=ohlc_df["date"],
            y=ohlc_df["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.6,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
        xaxis2=dict(
            showgrid=True,
            gridcolor="#2a2a2a",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#2a2a2a",
            tickprefix="₹",
        ),
        yaxis2=dict(
            showgrid=False,
            title="Vol",
            title_font_size=10,
        ),
    )

    return fig


def build_trend_sparkline(values: list[float], color: str = "#26a69a") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=values, mode="lines", line=dict(color=color, width=2)))
    fig.update_layout(
        height=60,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig

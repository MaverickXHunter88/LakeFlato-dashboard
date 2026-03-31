import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

# -----------------------------
# Load data
# -----------------------------
df = pd.read_csv('/home/designperformancelf/data_log.csv')

# Fix typo in temperature column if it exists
if 'temperautre_f' in df.columns:
    if 'temperature_f' in df.columns:
        df['temperature_f'] = df['temperature_f'].fillna(df['temperautre_f'])
    else:
        df['temperature_f'] = df['temperautre_f']

# Remove bad typo column
df = df.drop(columns=[col for col in df.columns if col == 'temperautre_f'], errors='ignore')

# Remove duplicate columns
df = df.loc[:, ~df.columns.duplicated()]

# Fix PM1 typo if needed
if 'pm1_uhm3' in df.columns and 'pm1_ugm3' not in df.columns:
    df['pm1_ugm3'] = df['pm1_uhm3']

# Expected sensor columns
cols = [
    'temperature_f',
    'pressure_inhg',
    'humidity_pct',
    'light_lux',
    'co2_ppm',
    'pm1_ugm3',
    'pm25_ugm3',
    'pm10_ugm3'
]

# Convert sensor columns to numeric
for col in cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    else:
        print(f"Missing column: {col}")
        df[col] = pd.NA

# Parse timestamps
if 'timestamp' not in df.columns:
    raise ValueError("CSV is missing required 'timestamp' column.")

df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
df = df.dropna(subset=['timestamp'])

if df.empty:
    raise ValueError("No valid data in CSV after parsing.")

# Convert UTC to local time
df['timestamp'] = df['timestamp'].dt.tz_convert('America/Chicago').dt.tz_localize(None)

# Re-check after conversion/drop
if df.empty:
    raise ValueError("No valid data available after timestamp conversion.")

# -----------------------------
# Define time window
# Yesterday + today to now
# -----------------------------
now_time = df['timestamp'].max()
start_today = now_time.normalize()
start_yesterday = start_today - pd.Timedelta(days=1)

df = df[(df['timestamp'] >= start_yesterday) & (df['timestamp'] <= now_time)].copy()

if df.empty:
    raise ValueError("No data found in the selected yesterday/today time window.")

# Split yesterday vs today
df_older = df[df['timestamp'] < start_today].copy()
df_today = df[df['timestamp'] >= start_today].copy()

# Compress yesterday, keep today more detailed
if not df_older.empty:
    df_older = (
        df_older
        .set_index('timestamp')
        .resample('1h')[cols]
        .mean()
        .reset_index()
    )

if not df_today.empty:
    df_today = (
        df_today
        .set_index('timestamp')
        .resample('15min')[cols]
        .mean()
        .reset_index()
    )

# Recombine for smoothing
df = pd.concat([df_older, df_today]).sort_values('timestamp').reset_index(drop=True)

# Smoothed temperature
df['temp_smooth'] = df['temperature_f'].rolling(window=5, min_periods=1).mean()

# Split again after smoothing
df_older = df[df['timestamp'] < start_today].copy()
df_today = df[df['timestamp'] >= start_today].copy()

midnight = start_today


# -----------------------------
# Helpers
# -----------------------------
def get_latest_valid_point(dataframe, y_col):
    """
    Return latest valid (timestamp, value) pair for a metric.
    """
    if dataframe.empty or y_col not in dataframe.columns:
        return None, None

    valid = dataframe[['timestamp', y_col]].dropna()
    if valid.empty:
        return None, None

    latest_row = valid.iloc[-1]
    return latest_row['timestamp'], latest_row[y_col]


def compute_y_range(older_y, today_y, nonnegative=False):
    """
    Compute a readable y-axis range.
    """
    series_list = []

    if older_y is not None:
        series_list.append(pd.Series(older_y).dropna())
    if today_y is not None:
        series_list.append(pd.Series(today_y).dropna())

    if not series_list:
        return None

    combined = pd.concat(series_list)
    if combined.empty:
        return None

    y_min = combined.min()
    y_max = combined.max()

    if pd.isna(y_min) or pd.isna(y_max):
        return None

    if y_min == y_max:
        pad = max(abs(y_min) * 0.1, 1)
    else:
        pad = (y_max - y_min) * 0.10

    low = y_min - pad
    high = y_max + pad

    if nonnegative:
        low = 0
        if high <= 0:
            high = 1

    return [low, high]


def make_chart(
    title,
    older_x,
    older_y,
    today_x,
    today_y,
    color,
    latest_label_suffix="",
    thresholds=None,
    nonnegative=False,
    y_format=None
):
    fig = go.Figure()

    # Older trace
    if older_x is not None and older_y is not None and len(older_x) > 0:
        fig.add_trace(go.Scatter(
            x=older_x,
            y=older_y,
            mode="lines",
            line=dict(color=color, width=2),
            opacity=0.40,
            showlegend=False,
            hovertemplate="%{x|%m/%d %-I:%M %p}<br>%{y}<extra></extra>"
        ))

    # Today trace
    if today_x is not None and today_y is not None and len(today_x) > 0:
        fig.add_trace(go.Scatter(
            x=today_x,
            y=today_y,
            mode="lines",
            line=dict(color=color, width=3),
            opacity=1.0,
            showlegend=False,
            hovertemplate="%{x|%m/%d %-I:%M %p}<br>%{y}<extra></extra>"
        ))

    # Thresholds
    if thresholds:
        for y in thresholds:
            fig.add_hline(
                y=y,
                line_dash="dash",
                line_color="white",
                opacity=0.30
            )

    # Today divider
    fig.add_vline(
        x=midnight,
        line_width=2,
        line_dash="dot",
        line_color="gray",
        opacity=0.8
    )

    # Today label
    fig.add_annotation(
        x=midnight,
        y=1.02,
        xref="x",
        yref="paper",
        text="Today",
        showarrow=False,
        font=dict(color="white", size=12),
        xanchor="left",
        yanchor="bottom"
    )

    # Latest valid point for this metric
    latest_x, latest_y = get_latest_valid_point(
        pd.concat([
            pd.DataFrame({'timestamp': older_x, 'value': older_y}) if older_x is not None and older_y is not None else pd.DataFrame(),
            pd.DataFrame({'timestamp': today_x, 'value': today_y}) if today_x is not None and today_y is not None else pd.DataFrame()
        ], ignore_index=True).rename(columns={'value': 'metric_value'}),
        'metric_value'
    )

    if latest_x is not None and latest_y is not None:
        if isinstance(latest_y, float):
            if abs(latest_y) >= 100:
                latest_text = f"{latest_y:.0f}{latest_label_suffix}"
            elif abs(latest_y) >= 10:
                latest_text = f"{latest_y:.1f}{latest_label_suffix}"
            else:
                latest_text = f"{latest_y:.2f}{latest_label_suffix}"
        else:
            latest_text = f"{latest_y}{latest_label_suffix}"

        fig.add_trace(go.Scatter(
            x=[latest_x],
            y=[latest_y],
            mode="markers+text",
            text=[latest_text],
            textposition="top right",
            marker=dict(size=9, color="white"),
            showlegend=False,
            hovertemplate="%{x|%m/%d %-I:%M %p}<br>%{y}<extra></extra>"
        ))

    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="white")
        ),
        template="plotly_dark",
        paper_bgcolor="black",
        plot_bgcolor="black",
        font=dict(color="white", size=11),
        margin=dict(l=50, r=20, t=45, b=45),
        height=290,
        showlegend=False,
        dragmode="pan"
    )

    fig.update_xaxes(
        tickformat="%-I %p",
        dtick=7200000,
        tickangle=0,
        showgrid=True,
        zeroline=False,
        range=[start_yesterday, now_time]
    )

    y_range = compute_y_range(older_y, today_y, nonnegative=nonnegative)
    if y_range is not None:
        fig.update_yaxes(range=y_range)

    if y_format:
        fig.update_yaxes(tickformat=y_format)

    return fig


# -----------------------------
# Build charts
# -----------------------------
temp_fig = make_chart(
    title="Temperature (F)",
    older_x=df_older["timestamp"],
    older_y=df_older["temperature_f"],
    today_x=df_today["timestamp"],
    today_y=df_today["temperature_f"],
    color="#FF6B6B",
    latest_label_suffix="F"
)

# Optional smoothed temperature overlay
if "temp_smooth" in df_older.columns and not df_older["temp_smooth"].isna().all():
    temp_fig.add_trace(go.Scatter(
        x=df_older["timestamp"],
        y=df_older["temp_smooth"],
        mode="lines",
        line=dict(color="#FFD166", width=2),
        opacity=0.50,
        showlegend=False,
        hovertemplate="%{x|%m/%d %-I:%M %p}<br>%{y}<extra></extra>"
    ))

if "temp_smooth" in df_today.columns and not df_today["temp_smooth"].isna().all():
    temp_fig.add_trace(go.Scatter(
        x=df_today["timestamp"],
        y=df_today["temp_smooth"],
        mode="lines",
        line=dict(color="#FFD166", width=3),
        opacity=1.0,
        showlegend=False,
        hovertemplate="%{x|%m/%d %-I:%M %p}<br>%{y}<extra></extra>"
    ))

pressure_fig = make_chart(
    title="Pressure (inHg)",
    older_x=df_older["timestamp"],
    older_y=df_older["pressure_inhg"],
    today_x=df_today["timestamp"],
    today_y=df_today["pressure_inhg"],
    color="#9ECBFF",
    latest_label_suffix=" inHg"
)

humidity_fig = make_chart(
    title="Humidity (%)",
    older_x=df_older["timestamp"],
    older_y=df_older["humidity_pct"],
    today_x=df_today["timestamp"],
    today_y=df_today["humidity_pct"],
    color="#4ECDC4",
    latest_label_suffix="%",
    nonnegative=True
)

light_fig = make_chart(
    title="Light (lux)",
    older_x=df_older["timestamp"],
    older_y=df_older["light_lux"],
    today_x=df_today["timestamp"],
    today_y=df_today["light_lux"],
    color="#FFD5DF",
    latest_label_suffix=" lux",
    nonnegative=True
)

co2_fig = make_chart(
    title="CO2 (ppm)",
    older_x=df_older["timestamp"],
    older_y=df_older["co2_ppm"],
    today_x=df_today["timestamp"],
    today_y=df_today["co2_ppm"],
    color="#A29BFE",
    latest_label_suffix=" ppm",
    thresholds=[800, 1000],
    nonnegative=True
)

pm1_fig = make_chart(
    title="PM1.0 (ug/m3)",
    older_x=df_older["timestamp"],
    older_y=df_older["pm1_ugm3"],
    today_x=df_today["timestamp"],
    today_y=df_today["pm1_ugm3"],
    color="#82B1FF",
    latest_label_suffix=" ug/m3",
    nonnegative=True
)

pm25_fig = make_chart(
    title="PM2.5 (ug/m3)",
    older_x=df_older["timestamp"],
    older_y=df_older["pm25_ugm3"],
    today_x=df_today["timestamp"],
    today_y=df_today["pm25_ugm3"],
    color="#FFD166",
    latest_label_suffix=" ug/m3",
    thresholds=[12, 35],
    nonnegative=True
)

pm10_fig = make_chart(
    title="PM10 (ug/m3)",
    older_x=df_older["timestamp"],
    older_y=df_older["pm10_ugm3"],
    today_x=df_today["timestamp"],
    today_y=df_today["pm10_ugm3"],
    color="#FF8A80",
    latest_label_suffix=" ug/m3",
    thresholds=[54, 154],
    nonnegative=True
)

# -----------------------------
# Export each chart to HTML div
# -----------------------------
temp_div = temp_fig.to_html(full_html=False, include_plotlyjs="cdn", config={"responsive": True})
pressure_div = pressure_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
humidity_div = humidity_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
light_div = light_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
co2_div = co2_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
pm1_div = pm1_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
pm25_div = pm25_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
pm10_div = pm10_fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})

# -----------------------------
# Final responsive page
# -----------------------------
html = f"""
<html>
<head>
<meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
html, body {{
    margin: 0;
    padding: 0;
    background: black;
    color: white;
    font-family: Arial, sans-serif;
}}

* {{
    box-sizing: border-box;
}}

.dashboard-header {{
    padding: 16px 20px 8px 20px;
}}

.dashboard-header h1 {{
    margin: 0;
    font-size: 32px;
    line-height: 1.15;
}}

.dashboard-header p {{
    margin: 6px 0 0 0;
    font-size: 14px;
    color: #cccccc;
}}

.dashboard-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    padding: 16px 20px 24px 20px;
}}

.chart-card {{
    background: black;
    border-radius: 10px;
    overflow: hidden;
    min-width: 0;
}}

.chart-card .plotly-graph-div {{
    width: 100% !important;
    height: 320px !important;
}}

@media (max-width: 900px) {{
    .dashboard-header {{
        padding: 14px 14px 6px 14px;
    }}

    .dashboard-header h1 {{
        font-size: 24px;
    }}

    .dashboard-header p {{
        font-size: 12px;
    }}

    .dashboard-grid {{
        grid-template-columns: 1fr;
        gap: 14px;
        padding: 12px;
    }}

    .chart-card .plotly-graph-div {{
        height: 300px !important;
    }}
}}
</style>
</head>
<body>
    <div class="dashboard-header">
        <h1>Miguel - Lake Flato Dashboard</h1>
        <p>San Antonio, Texas | {start_yesterday:%m/%d %I:%M %p} to {now_time:%m/%d %I:%M %p}</p>
    </div>

    <div class="dashboard-grid">
        <div class="chart-card">{temp_div}</div>
        <div class="chart-card">{pressure_div}</div>
        <div class="chart-card">{humidity_div}</div>
        <div class="chart-card">{light_div}</div>
        <div class="chart-card">{co2_div}</div>
        <div class="chart-card">{pm1_div}</div>
        <div class="chart-card">{pm25_div}</div>
        <div class="chart-card">{pm10_div}</div>
    </div>
</body>
</html>
"""

with open("microclimate_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Dashboard created")

import pandas as pd
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from datetime import timedelta

#Load Data First
df = pd.read_csv('/home/designperformancelf/data_log.csv')

#Fix type column if it exists
if 'temperautre_f' in df.columns:
   df['temperature_f'] = df['temperature_f'].fillna(df['temperautre_f'])
#Remove bad Column 
df = df.drop(columns=[col for col in df.columns if col == 'temperautre_f'], errors='ignore')
#Remove duplicate columns (just in case)
df = df.loc[:, ~df.columns.duplicated()]

#Convert all sensor columns to numeric
cols=['temperature_f','humidity_pct', 'co2_ppm', 'pm25_ugm3']
for col in cols:
   if col in df.columns:
      if isinstance (df[col], pd.Series):
         df[col] = pd.to_numeric(df[col],errors='coerce')
      else:
         print(f"Skipping {col} - not a Series")
         df[col] = None
   else:
      print (f"Missing column: {col}")
      df[col] = None

print(df.columns)
print(df.head())

#Convert timestamp from UTC-aware to local time
df['timestamp']=pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
df= df.dropna(subset=['timestamp'])
df['timestamp']=df['timestamp'].dt.tz_convert('America/Chicago').dt.tz_localize(None)

#Define Calendar-day Window: Yesterday + today to now
now_time= df['timestamp'].max()
if df.empty:
   raise ValueError("No valid data in CSV after parsing.")
start_today= now_time.normalize()
start_yesterday= start_today - pd.Timedelta(days=1)

df= df[(df['timestamp'] >= start_yesterday) & (df['timestamp'] <= now_time)].copy()

#Split yesterday vs today
df_older = df[df['timestamp']< start_today].copy()
df_today = df[df['timestamp']>= start_today].copy()

#Compress Yesterday, keep today more detailed
if not df_older.empty:
   df_older= (
      df_older
      .set_index('timestamp')
      .resample('1h')[cols]
      .mean()
      .reset_index()
      )
if not df_today.empty:
   df_today= (
      df_today
      .set_index('timestamp')
      .resample('15min')[cols]
      .mean()
      .reset_index()
      )

opacity_older=0.35
opacity_today=1.0

#Recombine for Plotting
df= pd.concat([df_older, df_today]).sort_values('timestamp').reset_index(drop=True)

#Smoothed Temperature
df['temp_smooth']=df['temperature_f'].rolling(window=5).mean()

#Split again after Smoothing
df_older=df[df['timestamp']< start_today].copy()
df_today=df[df['timestamp']>= start_today].copy()

#Window Shown in Chart Title
start_time = start_yesterday
end_time = now_time

#Create Subplots
fig = make_subplots(
   rows=4, cols=1,
   shared_xaxes=True,
   vertical_spacing=0.08,
   subplot_titles=("Temperature (F)","Humidity (%)", "CO2 (ppm)", "PM2.5 (uf/m3)")
)

#Add traces

#Temp Yesterday (Faded)
fig.add_trace(go.Scatter(
   x=df_older['timestamp'],
   y=df_older['temperature_f'],
   line=dict(color="#FF6B6B"),
   opacity=0.35,
   showlegend=False),row=1, col=1)
#Temp Today (bold)
fig.add_trace(go.Scatter(
   x=df_today['timestamp'],
   y=df_today['temperature_f'],
   line=dict(color="#FF6B6B"),
   opacity=1.0), row=1, col=1)
#TempS Yesterday (Faded)
fig.add_trace(go.Scatter(
   x=df_older['timestamp'], 
   y=df_older['temp_smooth'], 
   line=dict(color="#FFD166"),
   opacity=0.35,
   showlegend=False), row=1, col=1)
#TempS Today
fig.add_trace(go.Scatter(
   x=df_today['timestamp'], 
   y=df_today['temp_smooth'], 
   line=dict(color="#FFD166"),
   opacity=1.0), row=1, col=1)
#Humidity Yesterday (Faded)
fig.add_trace(go.Scatter(
   x=df_older['timestamp'],
   y=df_older['humidity_pct'],
   line=dict(color="#4ECDC4"),
   opacity=0.35,
   showlegend=False),row=2, col=1)
#Humidity Today (bold)
fig.add_trace(go.Scatter(
   x=df_today['timestamp'],
   y=df_today['humidity_pct'],
   line=dict(color="#4ECDC4"),
   opacity=1.0), row=2, col=1)   
#Co2 Yesterday (Faded)
fig.add_trace(go.Scatter(
   x=df_older['timestamp'],
   y=df_older['co2_ppm'],
   line=dict(color="#A29BFE"),
   opacity=0.35,
   showlegend=False),row=3, col=1)
#Co2 Today (bold)
fig.add_trace(go.Scatter(
   x=df_today['timestamp'],
   y=df_today['co2_ppm'],
   line=dict(color="#A29BFE"),
   opacity=1.0), row=3, col=1)
fig.add_hline(y=800,line_dash="dash", line_color="white", opacity=0.4,row=3, col=1)
fig.add_hline(y=1000,line_dash="dash", line_color="white", opacity=0.4, row=3, col=1)
#PM25 Yesterday (Faded)
fig.add_trace(go.Scatter(
   x=df_older['timestamp'],
   y=df_older['pm25_ugm3'],
   line=dict(color="#FFD166"),
   opacity=0.35,
   showlegend=False),row=4, col=1)
#PM25 Today (bold)
fig.add_trace(go.Scatter(
   x=df_today['timestamp'],
   y=df_today['pm25_ugm3'],
   line=dict(color="#FFD166"),
   opacity=1.0), row=4, col=1)
fig.add_hline(y=12,line_dash="dash", line_color="white", opacity=0.4, row=4, col=1)

midnight=start_today
fig.add_vline(x=midnight, line_width=2, line_dash="dot", line_color="gray")
fig.add_annotation(x=midnight, y=1, xref="x", yref="paper", text="Today", showarrow=False, font=dict(color="white"), align="center")

#---Current time marker (latest point)-----
latest = df_today.iloc[-1]

#Temperature
fig.add_trace(
   go.Scatter(
      x=[latest["timestamp"]],
      y=[latest["temperature_f"]],
      mode="markers+text",
      text=[f"{latest['temperature_f']:.0f}F"],
      textposition="top right",
      marker=dict(size=10, color="white"),
      showlegend=False
   ),
   row=1, col=1
)

#Smoothed Temperature
fig.add_trace(
   go.Scatter(
      x=[latest["timestamp"]],
      y=[latest["temp_smooth"]],
      mode="markers",
      marker=dict(size=10, color="white"),
      showlegend=False
   ),
   row=1, col=1
)

#Humidity
fig.add_trace(
   go.Scatter(
      x=[latest["timestamp"]],
      y=[latest["humidity_pct"]],
      mode="markers+text",
      text=[f"{latest['humidity_pct']:.0f}%"],
      textposition="top right",
      marker=dict(size=10, color="white"),
      showlegend=False
   ),
   row=2, col=1
)

#C02
fig.add_trace(
   go.Scatter(
      x=[latest["timestamp"]],
      y=[latest["co2_ppm"]],
      mode="markers+text",
      text=[f"{latest['co2_ppm']:.0f}ppm"],
      textposition="top right",
      marker=dict(size=10, color="white"),
      showlegend=False
   ),
   row=3, col=1
)

#PM25
fig.add_trace(
   go.Scatter(
      x=[latest["timestamp"]],
      y=[latest["pm25_ugm3"]],
      mode="markers+text",
      text=[f"{latest['pm25_ugm3']:.0f}ug/m3"],
      textposition="top right",
      marker=dict(size=10, color="white"),
      showlegend=False
   ),
   row=4, col=1
)

#Layout
fig.update_layout(
   title=dict(
      text=(
         "Miguel - Lake Flato Dashboard"
         "<br><span style='font-size:12px;'>"
         "San Antonio, Texas | "
         f"{start_yesterday:%m/%d %I:%M %p} to {now_time:%m/%d %I:%M %p}"
         "</span>"
      ),
      x=0.03,
      xanchor="left",
      y=0.92,
      yanchor="top",
      font=dict(size=28, color="white")
      ),
   height=1000,
   showlegend=False,
   template="plotly_dark", #This is Key
   paper_bgcolor="black",
   plot_bgcolor="black",
   font=dict(color="white"),
   dragmode="pan",
   margin=dict(l=60, r=40, t=140, b=120)
)
end_of_today = start_today + timedelta(days=1)
fig.update_xaxes (tickformat="%I:%M %p", dtick=3600000, range=[start_today, end_of_today])

#Save (IMPORTANT: use CDN)
fig.write_html('microclimate_dashboard.html',include_plotlyjs='cdn')
with open('microclimate_dashboard.html','r', encoding='utf-8') as f:
   html=f.read()
html=html.replace(
   "<head>",
   '<head><meta http-equiv="refresh" contect="60">'
   )
with open('microclimate_dashboard.html', 'w', encoding='utf-8') as f:
   f.write(html)

print("Dashboard created")

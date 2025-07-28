import requests, pandas as pd, plotly.graph_objects as go
from datetime import datetime, timedelta
import time, os, json, webbrowser, random, glob
from dash import Dash, dcc, html, dash_table
from dash.dependencies import Input, Output
import logging

# 关闭 Flask 请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

USERNAME = "Majorwoo58"
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAFkI3AEAAAAAvxJAUMizbugAcl28sToyE9eEP8Y%3DuDb3vdNPusaqxISTSxTLqDQXG8pjlz1yUflJIvWJ3R2tXL"
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}
CSV_FILENAME = f"{USERNAME}_tweets.csv"
USER_ID_CACHE_FILE = f"{USERNAME}_user_id.json"

# ====== Twitter 数据逻辑 ======
def log_msg(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"🌐 {now} ｜Status｜→ {msg}")

def get_rate_limit_reset(headers):
    reset_str = headers.get("x-rate-limit-reset")
    if reset_str:
        try:
            reset_timestamp = int(reset_str)
            now_ts = int(time.time())
            wait_seconds = max(0, reset_timestamp - now_ts)
            return wait_seconds, datetime.fromtimestamp(reset_timestamp)
        except:
            pass
    return None, None

def load_cached_user_id():
    if os.path.exists(USER_ID_CACHE_FILE):
        with open(USER_ID_CACHE_FILE, 'r') as f:
            return json.load(f).get("user_id")
    return None

def save_cached_user_id(user_id):
    with open(USER_ID_CACHE_FILE, 'w') as f:
        json.dump({"user_id": user_id}, f)

def get_user_id(username):
    cached = load_cached_user_id()
    if cached:
        log_msg(f"✅ 使用缓存用户ID: {cached}")
        return cached
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        user_id = res.json()["data"]["id"]
        save_cached_user_id(user_id)
        return user_id
    else:
        raise Exception("❌ 获取用户ID失败")

def get_tweets(user_id, max_results=90):
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,organic_metrics",
        "exclude": "retweets,replies"
    }
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code == 429:
        wait, reset_time = get_rate_limit_reset(res.headers)
        log_msg(f"🚫 限流中 → 重置时间: {reset_time}，等待 {wait}秒")
        raise Exception(f"Rate limited, wait {wait}s")
    elif res.status_code != 200:
        raise Exception(f"❌ 抓取失败，状态码: {res.status_code}")
    return res.json().get("data", [])

def prepare_data(tweets):
    if not tweets:
        return pd.DataFrame()
    df = pd.DataFrame(tweets)
    metrics = df["public_metrics"].apply(pd.Series)
    df = pd.concat([df, metrics], axis=1)
    df["impression_count"] = 0
    if "organic_metrics" in df.columns:
        df["impression_count"] = df["organic_metrics"].apply(
            lambda x: x.get("impression_count", 0) if isinstance(x, dict) else 0)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["date_only"] = df["created_at"].dt.date
    df["hour"] = df["created_at"].dt.hour
    for col in ["like_count", "retweet_count", "reply_count", "quote_count", "impression_count"]:
        df[col] = df[col].apply(lambda x: max(x, 0))
    return df

def save_data_csv(df):
    df.to_csv(CSV_FILENAME, index=False)
    log_msg(f"💾 推文数据保存完成，共 {len(df)} 条")

def load_data_csv():
    if not os.path.exists(CSV_FILENAME):
        return pd.DataFrame()
    df = pd.read_csv(CSV_FILENAME, parse_dates=["created_at"])
    df["date_only"] = df["created_at"].dt.date
    df["hour"] = df["created_at"].dt.hour
    return df

def create_figure(df, mode="separate"):
    daily = df.groupby("date_only")[["like_count", "retweet_count", "impression_count"]].sum().reset_index()
    daily = daily.sort_values("date_only")
    date_min = daily["date_only"].min().strftime("%Y-%m-%d") if not daily.empty else "N/A"
    date_max = daily["date_only"].max().strftime("%Y-%m-%d") if not daily.empty else "N/A"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["date_only"], y=daily["impression_count"],
        name="Impressions / 展现", marker_color="rgba(135,206,250,0.7)"
    ))
    fig.add_trace(go.Bar(
        x=daily["date_only"], y=daily["retweet_count"],
        name="Retweets / 转推", marker_color="rgba(50,205,50,0.8)"
    ))
    fig.add_trace(go.Bar(
        x=daily["date_only"], y=daily["like_count"],
        name="Likes / 点赞", marker_color="rgba(30,144,255,1)"
    ))
    fig.update_layout(
        title=f"{USERNAME} Tweet Stats [{date_min} - {date_max}]",
        barmode="group" if mode == "separate" else "stack",
        height=600,
        xaxis=dict(tickangle=45, showline=True, linecolor='#ccc'),
        yaxis=dict(title="数量 / Count"),
        margin=dict(l=40, r=40, t=80, b=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified", dragmode=False, uirevision=True
    )
    return fig

def stat_card(title, value, color):
    return html.Div([
        html.H3(title, style={"margin": "0", "color": "white", "fontSize": "18px"}),
        html.H2(f"{value}", style={"margin": "0", "color": "white", "fontWeight": "bold"})
    ], className="stat-card", style={"background": color})

# ===== 读取图片并打乱顺序（最多 12 张） =====
def load_images():
    folder = os.path.join("assets", "pictures")
    all_imgs = glob.glob(os.path.join(folder, "NGX_*.jpg"))
    imgs = ["/assets/pictures/" + os.path.basename(x) for x in all_imgs]
    random.shuffle(imgs)
    imgs = imgs[:12]  # ✅ 限制最多 12 张，避免太多 DOM 卡顿
    half = len(imgs)//2
    return imgs[:half], imgs[half:]  # 两行拆开

row1_imgs, row2_imgs = load_images()

# ===== Dash 实例 =====
app = Dash(__name__)
app.title = f"Majorwoo/ウーの港"

# ✅ 页面加载淡入动画
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script>
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(function(){
                const wrapper = document.getElementById("page-wrapper");
                if(wrapper){
                    wrapper.style.opacity = "1";
                }
            }, 500);
        });
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

# 初始化推文数据
def load_data():
    try:
        user_id = get_user_id(USERNAME)
        log_msg("📡 请求最新推文中...")
        tweets = get_tweets(user_id, max_results=90)
        if not tweets:
            raise Exception("❌ 未获取到推文")
        df = prepare_data(tweets)
        save_data_csv(df)
    except Exception as e:
        log_msg(f"⚠️ 使用缓存数据，原因: {e}")
        df = load_data_csv()
        if df.empty:
            raise SystemExit("❌ 无可用数据")
    return df

df_global = load_data()

total_impressions = int(df_global["impression_count"].sum())
total_likes = int(df_global["like_count"].sum())
total_retweets = int(df_global["retweet_count"].sum())
avg_impressions = int(df_global["impression_count"].mean())
avg_likes = int(df_global["like_count"].mean())
avg_retweets = int(df_global["retweet_count"].mean())

summary_df = df_global.groupby("date_only").agg({
    "impression_count": "sum", "like_count": "sum", "retweet_count": "sum",
    "reply_count": "sum", "quote_count": "sum"
}).reset_index().sort_values(by="date_only", ascending=False)

# ===== 页面布局 =====
app.layout = html.Div(
    id="page-wrapper",
    style={"opacity": "0", "transition": "opacity 1s ease"},
    children=[
        html.Div(id="time-display"),
        html.A(
            "📊 Majorwoo/ウーの港",
            href="https://x.com/Majorwoo58",
            target="_blank",
            id="title",
            style={"marginBottom": "20px", "textDecoration": "none", "color": "white"}
        ),

        # === 胶片窗口 ===
        # 第一行胶片
html.Div([
    html.Div([html.Img(src=img) for img in row1_imgs]*2,
             className="film-track"),
], className="film-window"),

# 第二行胶片
html.Div([
    html.Div([html.Img(src=img) for img in row2_imgs]*2,
             className="film-track reverse"),
], className="film-window"),

        html.Div([
            html.Button("分开模式 / Separate Mode", id="separate-btn", n_clicks=1),
            html.Button("整合模式 / Combined Mode", id="combined-btn", n_clicks=0),
        ], id="btn-container", style={
            "marginBottom": "30px",
            "display": "flex", "justifyContent": "center", "gap": "20px"
        }),

        html.Div([
            stat_card("❤️ Likes 点赞（累计 / Total）", total_likes, "#1E90FF"),
            stat_card("🔁 Retweets 转推（累计 / Total）", total_retweets, "#32CD32"),
            stat_card("👁️ Impressions 展现（累计 / Total）", total_impressions, "#FF8C00"),
        ], id="total-stats", style={"display": "flex", "gap": "30px", "marginTop": "30px"}),

        html.Div([
            stat_card("🔷 Likes 点赞（平均 / Avg）", avg_likes, "#4682B4"),
            stat_card("🟩 Retweets 转推（平均 / Avg）", avg_retweets, "#228B22"),
            stat_card("🟨 Impressions 展现（平均 / Avg）", avg_impressions, "#FF7F50"),
        ], id="avg-stats", style={
            "display": "flex", "gap": "30px", "marginTop": "30px", "marginBottom": "40px"
        }),

        html.Div([
            dcc.Graph(
                id="bar-chart",
                figure=create_figure(df_global, mode="separate"),
                config={"displayModeBar": False, "scrollZoom": False, "dragMode": False}
            )
        ], id="chart-container", style={"marginBottom": "40px"}),

        html.Div([
            dash_table.DataTable(
                id="tweet-table",
                columns=[
                    {"name": "Date", "id": "date_only"},
                    {"name": "Impressions", "id": "impression_count"},
                    {"name": "Likes", "id": "like_count"},
                    {"name": "Retweets", "id": "retweet_count"},
                    {"name": "Replies", "id": "reply_count"},
                    {"name": "Quotes", "id": "quote_count"},
                ],
                data=summary_df.to_dict("records"),
                fixed_rows={"headers": True},
                style_table={"height": "350px", "overflowY": "auto"},
                style_cell={"textAlign": "center", "padding": "8px"},
                style_header={"backgroundColor": "#3a87ad", "color": "white", "fontWeight": "bold"},
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#f9f9f9"},
                    {"if": {"state": "active"}, "backgroundColor": "#d0ebff", "border": "1px solid #007BFF"}
                ],
                sort_action="native",
            )
        ], id="table-container", style={"marginBottom": "60px"}),

        dcc.Interval(id="interval", interval=1000, n_intervals=0),
    ]
)

# ===== 回调 =====
@app.callback(
    Output("time-display", "children"),
    Input("interval", "n_intervals")
)
def update_time(n):
    now_jst = datetime.utcnow() + timedelta(hours=9)
    return now_jst.strftime("%Y-%m-%d %H:%M:%S JST (UTC+9)")

from dash import ctx

@app.callback(
    Output("bar-chart", "figure"),
    Output("separate-btn", "style"),
    Output("combined-btn", "style"),
    Input("separate-btn", "n_clicks"),
    Input("combined-btn", "n_clicks"),
    prevent_initial_call=False
)
def switch_mode(sep_clicks, comb_clicks):
    active = {
        "padding": "10px 20px",
        "border": "2px solid #007BFF",
        "borderRadius": "8px",
        "backgroundColor": "#007BFF",
        "color": "white",
        "fontWeight": "bold",
        "cursor": "pointer"
    }
    inactive = {
        "padding": "10px 20px",
        "marginRight": "10px",
        "border": "2px solid #6c757d",
        "borderRadius": "8px",
        "backgroundColor": "#f8f9fa",
        "color": "#6c757d",
        "fontWeight": "bold",
        "cursor": "pointer"
    }

    triggered = ctx.triggered_id

    if triggered == "combined-btn":
        fig = create_figure(df_global, "combined")
        return fig, inactive, active
    else:
        fig = create_figure(df_global, "separate")
        return fig, active, inactive

if __name__ == "__main__":
    import flask.cli
    flask.cli.show_server_banner = lambda *args: None
    import threading
    def open_browser():
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:8050")
    threading.Thread(target=open_browser, daemon=True).start()
    log_msg("🚀 Dash 服务已启动 → http://127.0.0.1:8050")
    app.run(debug=False, port=8050)

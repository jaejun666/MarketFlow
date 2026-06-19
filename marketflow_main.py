import json
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
import duckdb
import flet as ft


DB_PATH = "stock_analysis.db"
ASSET_DIR = Path(__file__).parent / "assets"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
MARKET_SUFFIXES = {
    "000660": ".KS",
    "005930": ".KS",
    "005380": ".KS",
    "000270": ".KS",
    "003670": ".KS",
    "006400": ".KS",
    "010120": ".KS",
    "012450": ".KS",
    "012330": ".KS",
    "034020": ".KS",
    "035420": ".KS",
    "035720": ".KS",
    "035900": ".KQ",
    "039030": ".KQ",
    "042700": ".KS",
    "051910": ".KS",
    "052690": ".KS",
    "055550": ".KS",
    "064350": ".KS",
    "067160": ".KQ",
    "068270": ".KS",
    "105560": ".KS",
    "108490": ".KQ",
    "196170": ".KQ",
    "207940": ".KS",
    "247540": ".KQ",
    "259960": ".KS",
    "274090": ".KQ",
    "277810": ".KQ",
    "323410": ".KS",
    "329180": ".KS",
    "352820": ".KS",
    "373220": ".KS",
    "394280": ".KQ",
    "454910": ".KS",
    "RKLB": "",
}

C = ft.Colors
I = ft.Icons


def border_all(width, color):
    side = ft.BorderSide(width=width, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def get_connection():
    return duckdb.connect(DB_PATH)


def yahoo_symbol_candidates(stock_code):
    stock_code = stock_code.strip().upper()
    if any(character.isalpha() for character in stock_code):
        return [stock_code]
    preferred_suffix = MARKET_SUFFIXES.get(stock_code)
    suffixes = [preferred_suffix] if preferred_suffix else []
    for suffix in [".KS", ".KQ"]:
        if suffix not in suffixes:
            suffixes.append(suffix)
    return [f"{stock_code}{suffix}" for suffix in suffixes]


def fetch_yahoo_quote(stock_code):
    context = ssl.create_default_context(cafile=certifi.where())
    last_error = None

    for symbol in yahoo_symbol_candidates(stock_code):
        request = Request(
            YAHOO_CHART_URL.format(symbol=symbol),
            headers={"User-Agent": "Mozilla/5.0"},
        )

        try:
            with urlopen(request, timeout=10, context=context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            continue

        result = payload.get("chart", {}).get("result")
        if not result:
            last_error = ValueError(f"{symbol} 조회 결과가 없습니다.")
            continue

        chart = result[0]
        meta = chart.get("meta", {})
        quote = (chart.get("indicators", {}).get("quote") or [{}])[0]

        price = meta.get("regularMarketPrice")
        volume = meta.get("regularMarketVolume")

        if price is None:
            closes = [value for value in quote.get("close", []) if value is not None]
            price = closes[-1] if closes else None
        if volume is None:
            volumes = [value for value in quote.get("volume", []) if value is not None]
            volume = volumes[-1] if volumes else None

        if price is None:
            last_error = ValueError(f"{symbol} 현재가를 찾을 수 없습니다.")
            continue

        price = int(round(float(price)))
        volume = int(volume or 0)
        trading_value = int(round(price * volume / 100_000_000))
        return price, trading_value, symbol

    raise ValueError(f"{stock_code} 시세 조회 실패: {last_error}")


def init_database():
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS MarketData;")
    conn.execute("DROP TABLE IF EXISTS StockTheme;")
    conn.execute("DROP TABLE IF EXISTS Stock;")
    conn.execute("DROP TABLE IF EXISTS Theme;")
    conn.execute("DROP SEQUENCE IF EXISTS market_data_seq;")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS market_data_seq START 1;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS Theme (
            theme_id VARCHAR PRIMARY KEY,
            theme_name VARCHAR NOT NULL,
            image_path VARCHAR
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS Stock (
            stock_code VARCHAR PRIMARY KEY,
            stock_name VARCHAR NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS StockTheme (
            stock_code VARCHAR,
            theme_id VARCHAR,
            PRIMARY KEY (stock_code, theme_id),
            FOREIGN KEY (stock_code) REFERENCES Stock(stock_code),
            FOREIGN KEY (theme_id) REFERENCES Theme(theme_id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS MarketData (
            data_id INTEGER PRIMARY KEY DEFAULT nextval('market_data_seq'),
            stock_code VARCHAR,
            price INTEGER NOT NULL,
            trading_value BIGINT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (stock_code) REFERENCES Stock(stock_code)
        );
        """
    )

    conn.execute(
        """
        INSERT INTO Theme (theme_id, theme_name, image_path) VALUES
        ('T01', 'AI 반도체/HBM', 'assets/qksehcp.jpg'),
        ('T02', '이차전지/배터리', 'assets/qoxjfl.png'),
        ('T03', '자동차/인포테인먼트', 'assets/ck.png'),
        ('T04', '바이오/헬스케어', 'assets/qkdldh.png'),
        ('T05', '게임/엔터테인먼트', 'assets/rpdla.png'),
        ('T06', '금융/은행', 'assets/dmsgod.png'),
        ('T07', '조선/방산', 'assets/whtjs.png'),
        ('T08', '플랫폼/인터넷', 'assets/dlsxjspt.jpg'),
        ('T09', '로봇/자동화', 'assets/fhqht.png'),
        ('T10', '전력/원전', 'assets/wjsrl.png');
        """
    )
    conn.execute(
        """
        INSERT INTO Stock (stock_code, stock_name) VALUES
        ('000660', 'SK하이닉스'),
        ('042700', '한미반도체'),
        ('039030', '이오테크닉스'),
        ('394280', '오픈엣지테크놀로지'),
        ('005930', '삼성전자'),
        ('051910', 'LG화학'),
        ('247540', '에코프로비엠'),
        ('373220', 'LG에너지솔루션'),
        ('006400', '삼성SDI'),
        ('003670', '포스코퓨처엠'),
        ('005380', '현대차'),
        ('000270', '기아'),
        ('012330', '현대모비스'),
        ('207940', '삼성바이오로직스'),
        ('068270', '셀트리온'),
        ('196170', '알테오젠'),
        ('259960', '크래프톤'),
        ('352820', '하이브'),
        ('035900', 'JYP Ent.'),
        ('105560', 'KB금융'),
        ('055550', '신한지주'),
        ('323410', '카카오뱅크'),
        ('329180', 'HD현대중공업'),
        ('012450', '한화에어로스페이스'),
        ('064350', '현대로템'),
        ('035420', 'NAVER'),
        ('035720', '카카오'),
        ('067160', 'SOOP'),
        ('277810', '레인보우로보틱스'),
        ('454910', '두산로보틱스'),
        ('108490', '로보티즈'),
        ('034020', '두산에너빌리티'),
        ('010120', 'LS ELECTRIC'),
        ('052690', '한전기술');
        """
    )
    conn.execute(
        """
        INSERT INTO StockTheme (stock_code, theme_id) VALUES
        ('000660', 'T01'),
        ('042700', 'T01'),
        ('039030', 'T01'),
        ('394280', 'T01'),
        ('005930', 'T01'),
        ('005930', 'T10'),
        ('051910', 'T02'),
        ('247540', 'T02'),
        ('373220', 'T02'),
        ('006400', 'T02'),
        ('003670', 'T02'),
        ('005380', 'T03'),
        ('000270', 'T03'),
        ('012330', 'T03'),
        ('207940', 'T04'),
        ('068270', 'T04'),
        ('196170', 'T04'),
        ('259960', 'T05'),
        ('352820', 'T05'),
        ('035900', 'T05'),
        ('105560', 'T06'),
        ('055550', 'T06'),
        ('323410', 'T06'),
        ('329180', 'T07'),
        ('012450', 'T07'),
        ('012450', 'T09'),
        ('064350', 'T07'),
        ('035420', 'T08'),
        ('035720', 'T08'),
        ('067160', 'T08'),
        ('277810', 'T09'),
        ('454910', 'T09'),
        ('108490', 'T09'),
        ('034020', 'T10'),
        ('010120', 'T10'),
        ('052690', 'T10');
        """
    )
    conn.execute(
        """
        INSERT INTO MarketData (data_id, stock_code, price, trading_value) VALUES
        (nextval('market_data_seq'), '000660', 185000, 8500),
        (nextval('market_data_seq'), '042700', 142000, 5200),
        (nextval('market_data_seq'), '039030', 178000, 1700),
        (nextval('market_data_seq'), '394280', 29500, 900),
        (nextval('market_data_seq'), '005930', 73000, 3100),
        (nextval('market_data_seq'), '051910', 380000, 2400),
        (nextval('market_data_seq'), '247540', 178000, 2600),
        (nextval('market_data_seq'), '373220', 360000, 3100),
        (nextval('market_data_seq'), '006400', 280000, 1700),
        (nextval('market_data_seq'), '003670', 205000, 1200),
        (nextval('market_data_seq'), '005380', 220000, 1800),
        (nextval('market_data_seq'), '000270', 105000, 1500),
        (nextval('market_data_seq'), '012330', 245000, 1100),
        (nextval('market_data_seq'), '207940', 780000, 3200),
        (nextval('market_data_seq'), '068270', 185000, 2100),
        (nextval('market_data_seq'), '196170', 310000, 1900),
        (nextval('market_data_seq'), '259960', 265000, 1400),
        (nextval('market_data_seq'), '352820', 210000, 1700),
        (nextval('market_data_seq'), '035900', 72000, 800),
        (nextval('market_data_seq'), '105560', 82000, 2300),
        (nextval('market_data_seq'), '055550', 52000, 1800),
        (nextval('market_data_seq'), '323410', 23500, 900),
        (nextval('market_data_seq'), '329180', 215000, 2800),
        (nextval('market_data_seq'), '012450', 310000, 3500),
        (nextval('market_data_seq'), '064350', 52000, 2200),
        (nextval('market_data_seq'), '035420', 185000, 2600),
        (nextval('market_data_seq'), '035720', 43000, 1300),
        (nextval('market_data_seq'), '067160', 85000, 700),
        (nextval('market_data_seq'), '277810', 155000, 1600),
        (nextval('market_data_seq'), '454910', 74000, 1200),
        (nextval('market_data_seq'), '108490', 28000, 550),
        (nextval('market_data_seq'), '034020', 24500, 4200),
        (nextval('market_data_seq'), '010120', 185000, 1700),
        (nextval('market_data_seq'), '052690', 72000, 900);
        """
    )
    conn.close()
    MarketDataRepository.refresh_from_yahoo()


class ThemeRepository:
    @staticmethod
    def save(theme_data):
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO Theme (theme_id, theme_name, image_path)
            VALUES (?, ?, ?);
            """,
            [
                theme_data["theme_id"],
                theme_data["theme_name"],
                theme_data.get("image_path", ""),
            ],
        )
        conn.close()
        return True

    @staticmethod
    def find_all():
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT theme_id, theme_name, image_path
            FROM Theme
            ORDER BY theme_id;
            """
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def find_name(theme_id):
        conn = get_connection()
        row = conn.execute("SELECT theme_name FROM Theme WHERE theme_id = ?;", [theme_id]).fetchone()
        conn.close()
        return row[0] if row else theme_id


class StockRepository:
    @staticmethod
    def save(stock_data):
        conn = get_connection()
        exists = conn.execute(
            "SELECT stock_code FROM Stock WHERE stock_code = ?;",
            [stock_data["stock_code"]],
        ).fetchone()
        if exists:
            conn.execute(
                """
                UPDATE Stock
                SET stock_name = ?
                WHERE stock_code = ?;
                """,
                [stock_data["stock_name"], stock_data["stock_code"]],
            )
        else:
            conn.execute(
                """
                INSERT INTO Stock (stock_code, stock_name)
                VALUES (?, ?);
                """,
                [
                    stock_data["stock_code"],
                    stock_data["stock_name"],
                ],
            )
        link_exists = conn.execute(
            """
            SELECT stock_code
            FROM StockTheme
            WHERE stock_code = ? AND theme_id = ?;
            """,
            [stock_data["stock_code"], stock_data["theme_id"]],
        ).fetchone()
        if not link_exists:
            conn.execute(
                """
                INSERT INTO StockTheme (stock_code, theme_id)
                VALUES (?, ?);
                """,
                [stock_data["stock_code"], stock_data["theme_id"]],
            )
        conn.close()
        return True

    @staticmethod
    def find_by_theme(theme_id):
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT s.stock_code, s.stock_name, st.theme_id
            FROM Stock s
            JOIN StockTheme st ON s.stock_code = st.stock_code
            WHERE st.theme_id = ?
            ORDER BY s.stock_code;
            """,
            [theme_id],
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def find_all():
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                s.stock_code,
                s.stock_name,
                COALESCE(string_agg(t.theme_name, ', ' ORDER BY t.theme_id), '') AS theme_names
            FROM Stock s
            LEFT JOIN StockTheme st ON s.stock_code = st.stock_code
            LEFT JOIN Theme t ON st.theme_id = t.theme_id
            GROUP BY s.stock_code, s.stock_name
            ORDER BY s.stock_code;
            """
        ).fetchall()
        conn.close()
        return rows


class MarketDataRepository:
    @staticmethod
    def save(market_data):
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO MarketData (data_id, stock_code, price, trading_value)
            VALUES (nextval('market_data_seq'), ?, ?, ?);
            """,
            [
                market_data["stock_code"],
                int(round(float(market_data["price"]))),
                int(market_data["trading_value"]),
            ],
        )
        conn.close()
        return True

    @staticmethod
    def find_latest_by_stock(stock_code):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT data_id, stock_code, price, trading_value, timestamp
            FROM MarketData
            WHERE stock_code = ?
            ORDER BY timestamp DESC, data_id DESC
            LIMIT 1;
            """,
            [stock_code],
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def refresh_from_yahoo():
        rows = []
        failures = []

        for stock_code, stock_name, _ in StockRepository.find_all():
            try:
                price, trading_value, _ = fetch_yahoo_quote(stock_code)
                if trading_value <= 0:
                    latest_row = MarketDataRepository.find_latest_by_stock(stock_code)
                    trading_value = int(latest_row[3]) if latest_row else 0
                rows.append(
                    {
                        "stock_code": stock_code,
                        "price": price,
                        "trading_value": trading_value,
                    }
                )
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
                failures.append(f"{stock_name}({stock_code}): {error}")

        for row in rows:
            MarketDataRepository.save(row)

        return len(rows), failures


class ThemeAnalyticsRepository:
    @staticmethod
    def find_theme_capital_flow_ranking():
        conn = get_connection()
        rows = conn.execute(
            """
            WITH latest_market AS (
                SELECT data_id, stock_code, price, trading_value, timestamp
                FROM (
                    SELECT
                        m.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY stock_code
                            ORDER BY timestamp DESC, data_id DESC
                        ) AS rn
                    FROM MarketData m
                )
                WHERE rn = 1
            )
            SELECT
                t.theme_id,
                t.theme_name,
                t.image_path,
                COALESCE(SUM(lm.trading_value), 0) AS total_flow,
                COUNT(DISTINCT s.stock_code) AS stock_count,
                CASE
                    WHEN COUNT(DISTINCT s.stock_code) = 0 THEN 0
                    ELSE CAST(COALESCE(SUM(lm.trading_value), 0) AS DOUBLE) / COUNT(DISTINCT s.stock_code)
                END AS average_flow
            FROM Theme t
            LEFT JOIN StockTheme st ON t.theme_id = st.theme_id
            LEFT JOIN Stock s ON st.stock_code = s.stock_code
            LEFT JOIN latest_market lm ON s.stock_code = lm.stock_code
            GROUP BY t.theme_id, t.theme_name, t.image_path
            ORDER BY average_flow DESC, total_flow DESC;
            """
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def find_stock_flow_by_theme(theme_id):
        conn = get_connection()
        rows = conn.execute(
            """
            WITH latest_market AS (
                SELECT data_id, stock_code, price, trading_value, timestamp
                FROM (
                    SELECT
                        m.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY stock_code
                            ORDER BY timestamp DESC, data_id DESC
                        ) AS rn
                    FROM MarketData m
                )
                WHERE rn = 1
            )
            SELECT
                s.stock_code,
                s.stock_name,
                lm.price,
                lm.trading_value,
                lm.timestamp,
                COALESCE(string_agg(other_theme.theme_name, ', ' ORDER BY other_theme.theme_id), '') AS theme_names
            FROM Stock s
            JOIN StockTheme selected_theme ON s.stock_code = selected_theme.stock_code
            LEFT JOIN latest_market lm ON s.stock_code = lm.stock_code
            LEFT JOIN StockTheme all_theme ON s.stock_code = all_theme.stock_code
            LEFT JOIN Theme other_theme ON all_theme.theme_id = other_theme.theme_id
            WHERE selected_theme.theme_id = ?
            GROUP BY s.stock_code, s.stock_name, lm.price, lm.trading_value, lm.timestamp
            ORDER BY COALESCE(lm.trading_value, 0) DESC;
            """,
            [theme_id],
        ).fetchall()
        conn.close()
        return rows


def main(page: ft.Page):
    page.title = "MarketFlow"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    selected_theme_id = "T01"

    def safe_number(value):
        return 0 if value is None else int(value)

    def money_text(value):
        return f"{safe_number(value):,} 억 원"

    def compact_money_text(value):
        number = safe_number(value)
        if number >= 10000:
            return f"{number // 10000}.{(number % 10000) // 1000}조"
        return f"{number:,}억"

    def is_us_ticker(stock_code):
        return any(character.isalpha() for character in str(stock_code))

    def price_text(value, stock_code=None):
        if value is None:
            return "시세 없음"
        if is_us_ticker(stock_code):
            return f"${float(value):,.2f}"
        return f"{int(value):,} 원"

    def normalize_stock_code(value):
        return (value or "").strip().upper()

    def is_valid_stock_code(value):
        stock_code = normalize_stock_code(value)
        if len(stock_code) == 6 and stock_code.isdigit():
            return True
        return 1 <= len(stock_code) <= 10 and stock_code.replace(".", "").isalnum() and is_us_ticker(stock_code)

    def timestamp_text(value):
        return "적재 기록 없음" if value is None else str(value).split(".")[0]

    def show_message(message, bgcolor=C.BLUE_GREY_700):
        page.overlay.append(ft.SnackBar(content=ft.Text(message), bgcolor=bgcolor, open=True))
        page.update()

    def navigate(route):
        page.route = route
        route_change()

    def refresh_market_data(_=None):
        updated_count, failures = MarketDataRepository.refresh_from_yahoo()
        route_change()
        if updated_count:
            message = f"실시간 마켓 데이터 {updated_count}건을 MarketData에 적재했습니다."
            if failures:
                message += f" 실패 {len(failures)}건은 건너뛰었습니다."
            show_message(message, C.GREEN_700)
        else:
            show_message("실시간 시세를 가져오지 못했습니다. 인터넷 연결을 확인해주세요.", C.RED_700)

    def theme_icon(image_path):
        local_path = Path(image_path) if image_path else None
        if local_path and not local_path.is_absolute():
            local_path = Path(__file__).parent / local_path
        if local_path and local_path.exists():
            return ft.Image(src=str(local_path), width=44, height=44, fit=ft.BoxFit.CONTAIN)
        return ft.Icon(I.QUERY_STATS, size=40, color=C.BLUE_ACCENT)

    def page_header(title=None, show_admin=False):
        controls = [
            ft.Text(title or "📈 MarketFlow", size=30, weight=ft.FontWeight.BOLD, expand=True),
            ft.ElevatedButton("시세 적재", icon=I.REFRESH, on_click=refresh_market_data),
        ]
        if show_admin:
            controls.append(
                ft.ElevatedButton("Admin", icon=I.ADMIN_PANEL_SETTINGS, on_click=lambda _: navigate("/admin"))
            )
        return ft.Row(
            controls=controls,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def build_money_flow_chart(analytics_data, on_select=None):
        max_flow = max([safe_number(row[5]) for row in analytics_data] or [1])
        rows = []
        medal_colors = [C.AMBER, C.GREY_400, C.ORANGE_700]
        bar_track_width = 430

        for index, (theme_id, theme_name, image_path, total_flow, stock_count, average_flow) in enumerate(analytics_data, start=1):
            flow = safe_number(average_flow)
            is_selected = theme_id == selected_theme_id
            bar_width = int((flow / max_flow) * bar_track_width) if max_flow else 0
            bar_width = max(8, min(bar_track_width, bar_width))
            rest_width = max(0, bar_track_width - bar_width)
            rows.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        str(index),
                                        color=medal_colors[index - 1] if index <= 3 else C.GREY_400,
                                        width=24,
                                    ),
                                    theme_icon(image_path),
                                    ft.Column(
                                        controls=[
                                            ft.Text(
                                                theme_name,
                                                size=15,
                                                weight=ft.FontWeight.BOLD,
                                                max_lines=1,
                                            ),
                                            ft.Text(f"{safe_number(stock_count)}종목", size=12, color=C.GREY_400),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    ft.Text(
                                        f"평균 {compact_money_text(average_flow)}",
                                        size=10,
                                        color=C.WHITE,
                                        width=74,
                                        max_lines=1,
                                    ),
                                    ft.Text(
                                        f"총 {compact_money_text(total_flow)}",
                                        size=10,
                                        color=C.GREY_400,
                                        width=74,
                                        max_lines=1,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        width=bar_width,
                                        height=12,
                                        bgcolor=C.RED_600 if is_selected else C.RED_800,
                                        border_radius=4,
                                    ),
                                    ft.Container(
                                        width=rest_width,
                                        height=12,
                                        bgcolor=C.GREY_800,
                                        border_radius=4,
                                    ),
                                ],
                                spacing=0,
                                width=bar_track_width,
                            ),
                        ],
                        spacing=7,
                    ),
                    padding=8,
                    bgcolor=C.GREY_900 if is_selected else None,
                    border_radius=8,
                    on_click=lambda _, tid=theme_id: on_select(tid) if on_select else navigate(f"/detail/{tid}"),
                )
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("[왼쪽 영역: 테마 순위(BarChart)]", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=8),
                    ft.ListView(controls=rows, spacing=6, height=306),
                ],
                spacing=8,
            ),
            padding=15,
            border=border_all(1, C.GREY_700),
            border_radius=8,
        )

    def build_theme_cards(analytics_data, on_select):
        cards = []
        for theme_id, theme_name, image_path, total_flow, stock_count, average_flow in analytics_data:
            cards.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Row(
                            controls=[
                                theme_icon(image_path),
                                ft.Column(
                                    controls=[
                                        ft.Text(theme_name, size=16, weight=ft.FontWeight.BOLD),
                                        ft.Text(
                                            f"평균 {money_text(average_flow)} / 총 {money_text(total_flow)}",
                                            color=C.GREY_400,
                                        ),
                                    ],
                                    spacing=3,
                                    expand=True,
                                ),
                                ft.Icon(I.CHEVRON_RIGHT, color=C.GREY_500),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=12,
                        on_click=lambda _, tid=theme_id: on_select(tid),
                    )
                )
            )
        return ft.ListView(controls=cards, spacing=8, height=220)

    def build_detail_table(theme_id):
        theme_name = ThemeRepository.find_name(theme_id)
        stock_list = ThemeAnalyticsRepository.find_stock_flow_by_theme(theme_id)
        data_rows = []

        for code, name, price, value, timestamp, theme_names in stock_list:
            data_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(code)),
                        ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(theme_names or "-", size=12)),
                        ft.DataCell(ft.Text(price_text(price, code))),
                        ft.DataCell(ft.Text(money_text(value), color=C.GREEN_ACCENT if safe_number(value) >= 5000 else C.WHITE)),
                        ft.DataCell(ft.Text(timestamp_text(timestamp))),
                    ]
                )
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("[오른쪽 영역: 상세종목(DataTable)]", size=16, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=8),
                    ft.Text(f"선택된 테마: [{theme_name}]", size=18, color=C.BLUE_200),
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("종목코드")),
                            ft.DataColumn(ft.Text("종목명")),
                            ft.DataColumn(ft.Text("연결 테마")),
                            ft.DataColumn(ft.Text("현재 체결가")),
                            ft.DataColumn(ft.Text("실시간 거래대금")),
                            ft.DataColumn(ft.Text("시간")),
                        ],
                        rows=data_rows,
                        heading_row_color=C.GREY_900,
                        border=border_all(1, C.GREY_700),
                    ),
                ],
                spacing=8,
            ),
            padding=15,
            border=border_all(1, C.GREY_700),
            border_radius=8,
        )

    def render_main_dashboard():
        nonlocal selected_theme_id
        analytics_data = ThemeAnalyticsRepository.find_theme_capital_flow_ranking()

        if analytics_data and selected_theme_id not in [row[0] for row in analytics_data]:
            selected_theme_id = analytics_data[0][0]

        def select_theme(theme_id):
            nonlocal selected_theme_id
            selected_theme_id = theme_id
            navigate("/")

        page.views.append(
            ft.View(
                route="/",
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                page_header("📈 MarketFlow", show_admin=True),
                                ft.Row(
                                    controls=[
                                        ft.Column(
                                            controls=[
                                                build_money_flow_chart(analytics_data, on_select=select_theme),
                                                ft.Text("테마 선택 카드", size=16, color=C.GREY_300),
                                                build_theme_cards(analytics_data, select_theme),
                                            ],
                                            spacing=12,
                                            expand=5,
                                        ),
                                        build_detail_table(selected_theme_id),
                                    ],
                                    spacing=18,
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                ),
                            ],
                            spacing=18,
                        ),
                        padding=20,
                        border=border_all(2, C.GREY_600),
                        border_radius=8,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            )
        )

    def render_theme_detail(theme_id):
        theme_name = ThemeRepository.find_name(theme_id)
        stock_list = ThemeAnalyticsRepository.find_stock_flow_by_theme(theme_id)
        data_rows = []
        for code, name, price, value, timestamp, theme_names in stock_list:
            value_num = safe_number(value)
            data_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(code)),
                        ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(theme_names or "-", size=12)),
                        ft.DataCell(ft.Text(price_text(price, code))),
                        ft.DataCell(
                            ft.Text(
                                money_text(value_num),
                                color=C.GREEN_ACCENT if value_num >= 5000 else C.WHITE,
                            )
                        ),
                        ft.DataCell(ft.Text(timestamp_text(timestamp))),
                    ]
                )
            )
        page.views.append(
            ft.View(
                route=f"/detail/{theme_id}",
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(I.ARROW_BACK, on_click=lambda _: navigate("/")),
                            ft.Text(theme_name, size=22, weight=ft.FontWeight.BOLD, expand=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("Stock과 MarketData를 조인한 최신 종목별 자금 흐름", color=C.GREY_400),
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("종목코드")),
                            ft.DataColumn(ft.Text("종목명")),
                            ft.DataColumn(ft.Text("연결 테마")),
                            ft.DataColumn(ft.Text("현재 체결가")),
                            ft.DataColumn(ft.Text("실시간 거래대금")),
                            ft.DataColumn(ft.Text("적재 시각")),
                        ],
                        rows=data_rows,
                        heading_row_color=C.GREY_900,
                        border=border_all(1, C.GREY_700),
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            )
        )

    def render_admin_panel():
        theme_id_input = ft.TextField(label="테마 ID", hint_text="예: T04", width=220)
        theme_name_input = ft.TextField(label="테마명", hint_text="예: 로봇/자동화", width=320)
        image_path_input = ft.TextField(label="이미지 경로", hint_text="assets/images/robot.png", width=360)
        code_input = ft.TextField(label="종목 코드/티커", hint_text="예: 042700 또는 RKLB", width=220)
        name_input = ft.TextField(label="종목명", hint_text="예: 한미반도체", width=320)
        theme_dropdown = ft.Dropdown(
            label="연결할 테마",
            options=[
                ft.dropdown.Option(theme_id, theme_name)
                for theme_id, theme_name, _ in ThemeRepository.find_all()
            ],
            width=320,
        )
        market_code_input = ft.TextField(label="종목 코드/티커", hint_text="예: 000660 또는 RKLB", width=220)
        price_input = ft.TextField(label="현재 체결가", hint_text="예: 185000 또는 28", width=220)
        trading_value_input = ft.TextField(label="거래대금(억 원)", hint_text="예: 8500", width=220)

        def save_theme_clicked(_):
            theme_id = (theme_id_input.value or "").strip().upper()
            theme_name = (theme_name_input.value or "").strip()
            image_path = (image_path_input.value or "").strip()
            if not theme_id or not theme_name:
                show_message("테마 ID와 테마명을 입력해주세요.", C.RED_700)
                return
            try:
                ThemeRepository.save({"theme_id": theme_id, "theme_name": theme_name, "image_path": image_path})
            except duckdb.ConstraintException:
                show_message("이미 등록된 테마 ID입니다.", C.RED_700)
                return
            show_message("신규 테마가 Theme 테이블에 등록되었습니다.", C.GREEN_700)
            navigate("/admin")

        def save_stock_clicked(_):
            stock_code = normalize_stock_code(code_input.value)
            stock_name = (name_input.value or "").strip()
            theme_id = theme_dropdown.value
            if not is_valid_stock_code(stock_code):
                show_message("종목 코드는 국내 6자리 코드 또는 미국 티커로 입력해주세요.", C.RED_700)
                return
            if not stock_name or not theme_id:
                show_message("종목명과 소속 테마를 모두 입력해주세요.", C.RED_700)
                return
            try:
                StockRepository.save({"stock_code": stock_code, "stock_name": stock_name, "theme_id": theme_id})
            except duckdb.ConstraintException:
                show_message("이미 등록된 종목 코드입니다.", C.RED_700)
                return
            show_message("종목 정보가 저장되고 선택한 테마가 StockTheme 테이블에 연결되었습니다.", C.GREEN_700)
            navigate("/")

        def save_market_clicked(_):
            stock_code = normalize_stock_code(market_code_input.value)
            price = (price_input.value or "").strip()
            trading_value = (trading_value_input.value or "").strip()
            if not is_valid_stock_code(stock_code):
                show_message("종목 코드는 국내 6자리 코드 또는 미국 티커로 입력해주세요.", C.RED_700)
                return
            if not price.replace(".", "", 1).isdigit() or not trading_value.isdigit():
                show_message("현재 체결가와 거래대금은 숫자로 입력해주세요.", C.RED_700)
                return
            try:
                MarketDataRepository.save({"stock_code": stock_code, "price": price, "trading_value": trading_value})
            except duckdb.ConstraintException:
                show_message("Stock 테이블에 없는 종목 코드입니다.", C.RED_700)
                return
            show_message("마켓 데이터가 MarketData 테이블에 적재되었습니다.", C.GREEN_700)
            navigate("/")

        def section(title, controls):
            return ft.Container(
                content=ft.Column(
                    controls=[ft.Text(title, size=18, weight=ft.FontWeight.BOLD)] + controls,
                    spacing=10,
                ),
                padding=15,
                border=border_all(1, C.GREY_700),
                border_radius=8,
            )

        page.views.append(
            ft.View(
                route="/admin",
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(I.ARROW_BACK, on_click=lambda _: navigate("/")),
                            ft.Text("시스템 데이터 관리 및 삽입", size=22, weight=ft.FontWeight.BOLD),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    section(
                        "Theme 테이블 신규 테마 등록",
                        [
                            ft.Row([theme_id_input, theme_name_input], spacing=10),
                            image_path_input,
                            ft.ElevatedButton("테마 등록", icon=I.ADD, on_click=save_theme_clicked),
                        ],
                    ),
                    section(
                        "Stock 테이블 신규 종목 등록 / StockTheme 테마 연결",
                        [
                            ft.Row([code_input, name_input], spacing=10),
                            theme_dropdown,
                            ft.ElevatedButton("종목 등록 및 테마 연결", icon=I.SAVE, on_click=save_stock_clicked),
                        ],
                    ),
                    section(
                        "MarketData 테이블 실시간 거래 데이터 적재",
                        [
                            ft.Row([market_code_input, price_input, trading_value_input], spacing=10),
                            ft.ElevatedButton("마켓 데이터 적재", icon=I.UPLOAD, on_click=save_market_clicked),
                        ],
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            )
        )

    def route_change(_=None):
        page.views.clear()
        if page.route == "/":
            render_main_dashboard()
        elif page.route.startswith("/detail/"):
            render_theme_detail(page.route.split("/")[-1])
        elif page.route == "/admin":
            render_admin_panel()
        else:
            page.route = "/"
            render_main_dashboard()
        page.update()

    page.on_route_change = route_change
    page.route = "/"
    route_change()


if __name__ == "__main__":
    init_database()
    ft.run(main, assets_dir=str(ASSET_DIR))

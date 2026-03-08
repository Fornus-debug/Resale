# “””
転売AI監視システム - 完全版

【使い方】

1. install.bat をダブルクリック（初回のみ）
1. .env ファイルに Discord URL を貼り付ける
1. start.bat をダブルクリックで起動
1. テストだけしたい場合は test.bat をダブルクリック
   “””

import os
import time
import asyncio
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ============================================================

# ⚙️ 設定（ここを変えるだけでカスタマイズできます）

# ============================================================

CONFIG = {
“discord_webhook”:    os.getenv(“DISCORD_WEBHOOK_URL”, “”),
“scan_interval”:      15,        # 監視周期（秒）
“daily_notify_limit”: 20,        # 1日の通知上限
“min_roi”:            30,        # ROI閾値（%）
“min_profit”:         8000,      # 最低利益（円）
“mercari_fee_rate”:   0.10,      # メルカリ手数料10%
“keywords”: [
“ジャンク”, “画面割れ”, “電源入らない”,
“部品取り”, “起動不可”, “水没痕”,
],
“priority_models”: [“iPhone 11”, “iPhone 12”, “iPhone 13”],
}

# ============================================================

# 📱 機種別データ（販売予測価格・修理費・難易度）

# ============================================================

MODEL_DATA = {
“iPhone 13 Pro Max”: {“sell_price”: 55000, “screen_repair”: 8000, “difficulty”: 1.3},
“iPhone 13 Pro”:     {“sell_price”: 48000, “screen_repair”: 7000, “difficulty”: 1.2},
“iPhone 13”:         {“sell_price”: 38000, “screen_repair”: 6000, “difficulty”: 1.0},
“iPhone 12 Pro Max”: {“sell_price”: 42000, “screen_repair”: 7500, “difficulty”: 1.2},
“iPhone 12 Pro”:     {“sell_price”: 35000, “screen_repair”: 6500, “difficulty”: 1.1},
“iPhone 12 mini”:    {“sell_price”: 22000, “screen_repair”: 5500, “difficulty”: 1.1},
“iPhone 12”:         {“sell_price”: 28000, “screen_repair”: 6000, “difficulty”: 1.0},
“iPhone 11 Pro Max”: {“sell_price”: 32000, “screen_repair”: 7000, “difficulty”: 1.2},
“iPhone 11 Pro”:     {“sell_price”: 28000, “screen_repair”: 6500, “difficulty”: 1.1},
“iPhone 11”:         {“sell_price”: 22000, “screen_repair”: 5500, “difficulty”: 1.0},
“DEFAULT”:           {“sell_price”: 15000, “screen_repair”: 6000, “difficulty”: 1.0},
}

# ============================================================

# 🔧 故障キーワード→修理費テーブル

# ============================================================

REPAIR_COST_TABLE = {
“画面割れ”:     6000,
“水没”:         3000,
“電源入らない”: 4000,
“起動不可”:     4000,
“バッテリー”:   3500,
“充電できない”: 2000,
“カメラ”:       5000,
“ホームボタン”: 2000,
“部品取り”:     0,
}

# ============================================================

# 📦 データクラス

# ============================================================

@dataclass
class Product:
id: str
title: str
price: int
url: str
thumbnail: str
posted_at: datetime
description: str = “”
image_count: int = 1
seller_rating: int = 999

@dataclass
class ROIResult:
product: Product
model_name: str
sell_price: int
repair_cost: int
mercari_fee: int
total_cost: int
profit: int
roi: float
risk_level: str
competition_score: int
priority_score: float
issues: list = field(default_factory=list)

# ============================================================

# 🧠 ROI計算エンジン

# ============================================================

class ROIEngine:

```
def detect_model(self, title: str) -> tuple:
    for name, data in MODEL_DATA.items():
        if name == "DEFAULT":
            continue
        if name.lower() in title.lower():
            return name, data
    return "不明", MODEL_DATA["DEFAULT"]

def estimate_repair_cost(self, title: str, description: str) -> tuple:
    text = f"{title} {description}".lower()
    total = 0
    issues = []
    for kw, cost in REPAIR_COST_TABLE.items():
        if kw in text:
            total += cost
            issues.append(f"{kw}(¥{cost:,})")
    if len(issues) >= 3:
        total = int(total * 1.3)
        issues.append("複合故障割増×1.3")
    if total == 0:
        total = 5000
        issues.append("故障詳細不明(¥5,000)")
    return total, issues

def calc_competition_score(self, product: Product) -> int:
    score = 0
    if product.image_count <= 1:
        score += 30
    elif product.image_count <= 3:
        score += 15
    if product.seller_rating <= 50:
        score += 25
    elif product.seller_rating <= 100:
        score += 10
    hour = product.posted_at.hour
    if 22 <= hour or hour <= 6:
        score += 20
    if len(product.description) < 30:
        score += 25
    return min(score, 100)

def calculate(self, product: Product) -> ROIResult:
    model_name, model_info = self.detect_model(product.title)
    sell_price = model_info["sell_price"]
    difficulty = model_info["difficulty"]

    repair_cost, issues = self.estimate_repair_cost(product.title, product.description)
    repair_cost = int(repair_cost * difficulty)

    mercari_fee = int(sell_price * CONFIG["mercari_fee_rate"])
    profit = sell_price - product.price - repair_cost - mercari_fee
    roi = (profit / product.price * 100) if product.price > 0 else 0
    competition_score = self.calc_competition_score(product)

    if roi >= 60 and competition_score >= 50:
        risk_level = "LOW"
    elif roi >= 40:
        risk_level = "MID"
    else:
        risk_level = "HIGH"

    priority_score = (roi * 0.5) + (profit / 1000 * 0.3) + (competition_score * 0.2)
    for pm in CONFIG["priority_models"]:
        if pm.lower() in product.title.lower():
            priority_score *= 1.2
            break

    return ROIResult(
        product=product,
        model_name=model_name,
        sell_price=sell_price,
        repair_cost=repair_cost,
        mercari_fee=mercari_fee,
        total_cost=product.price + repair_cost + mercari_fee,
        profit=profit,
        roi=round(roi, 1),
        risk_level=risk_level,
        competition_score=competition_score,
        priority_score=round(priority_score, 2),
        issues=issues,
    )

def is_worth_notifying(self, result: ROIResult) -> bool:
    return result.roi >= CONFIG["min_roi"] and result.profit >= CONFIG["min_profit"]
```

# ============================================================

# 💬 Discord通知エンジン

# ============================================================

class DiscordNotifier:
def **init**(self, webhook_url: str):
self.webhook_url = webhook_url
self.today_count = 0
self.today_date = datetime.now().date()

```
def _reset_if_new_day(self):
    if datetime.now().date() != self.today_date:
        self.today_count = 0
        self.today_date = datetime.now().date()

def can_notify(self) -> bool:
    self._reset_if_new_day()
    return self.today_count < CONFIG["daily_notify_limit"]

def _color(self, roi: float) -> int:
    if roi >= 60: return 0x39FF14
    if roi >= 40: return 0xFFD600
    return 0xFF6B35

def _risk_emoji(self, risk: str) -> str:
    return {"LOW": "🟢", "MID": "🟡", "HIGH": "🔴"}.get(risk, "⚪")

def send_alert(self, result: ROIResult) -> bool:
    if not self.webhook_url:
        print("  ⚠️  .env に DISCORD_WEBHOOK_URL を設定してください")
        return False
    if not self.can_notify():
        print(f"  📵 本日の通知上限({CONFIG['daily_notify_limit']}件)に達しました")
        return False

    p = result.product
    embed = {
        "title": f"🔔 購入候補アラート #{self.today_count + 1}",
        "description": f"**{p.title}**",
        "color": self._color(result.roi),
        "url": p.url,
        "fields": [
            {"name": "📊 ROI",        "value": f"**{result.roi}%**",          "inline": True},
            {"name": "💴 利益",       "value": f"**¥{result.profit:,}**",     "inline": True},
            {"name": "💰 仕入価格",   "value": f"¥{p.price:,}",              "inline": True},
            {"name": "📱 機種",       "value": result.model_name,             "inline": True},
            {"name": "🛒 販売予測",   "value": f"¥{result.sell_price:,}",    "inline": True},
            {"name": "🔧 修理費",     "value": f"¥{result.repair_cost:,}",   "inline": True},
            {"name": "📋 手数料",     "value": f"¥{result.mercari_fee:,}",   "inline": True},
            {"name": "🎯 競争回避",   "value": f"{result.competition_score}/100", "inline": True},
            {"name": f"{self._risk_emoji(result.risk_level)} リスク", "value": result.risk_level, "inline": True},
            {"name": "🔍 検出故障",   "value": "\n".join(result.issues) or "不明", "inline": False},
        ],
        "footer": {
            "text": f"転売AI監視システム | {datetime.now().strftime('%H:%M:%S')} | 本日{self.today_count+1}/{CONFIG['daily_notify_limit']}件目"
        },
    }
    if p.thumbnail:
        embed["thumbnail"] = {"url": p.thumbnail}

    try:
        res = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
        if res.status_code in (200, 204):
            self.today_count += 1
            print(f"  ✅ Discord送信 #{self.today_count} | ROI {result.roi}% | 利益 ¥{result.profit:,}")
            return True
        else:
            print(f"  ❌ Discord送信失敗: {res.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Discord送信エラー: {e}")
        return False

def send_message(self, text: str):
    if not self.webhook_url:
        return
    try:
        requests.post(self.webhook_url, json={"content": text}, timeout=10)
    except Exception:
        pass

def send_daily_summary(self, results: list):
    if not results:
        return
    avg_roi = sum(r.roi for r in results) / len(results)
    best = max(results, key=lambda r: r.roi)
    self.send_message(
        f"📈 **本日のサマリー**\n"
        f"通知件数: {len(results)}件 | 平均ROI: {avg_roi:.1f}% | 最高ROI: {best.roi}%（{best.model_name}）"
    )
```

# ============================================================

# 🌐 メルカリスクレイパー（Playwright）

# ============================================================

class MercariScraper:
def **init**(self):
self.seen_ids = set()
self.browser = None
self.page = None

```
async def setup(self):
    from playwright.async_api import async_playwright
    self._pw = await async_playwright().start()
    self.browser = await self._pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    self.page = await self.browser.new_page()
    await self.page.set_extra_http_headers({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    })

async def teardown(self):
    if self.browser:
        await self.browser.close()
    if hasattr(self, "_pw"):
        await self._pw.stop()

async def search(self, keyword: str) -> list:
    products = []
    try:
        url = f"https://jp.mercari.com/search?keyword={keyword}&status=on_sale&sort=created_time&order=desc"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(2500)

        items = await self.page.query_selector_all('[data-testid="item-cell"]')
        for item in items[:20]:
            try:
                link = await item.query_selector("a")
                href = await link.get_attribute("href") if link else ""
                pid = href.split("/")[-1] if href else ""
                if not pid or pid in self.seen_ids:
                    continue

                title_el = await item.query_selector('[data-testid="item-name"]')
                title = await title_el.inner_text() if title_el else ""

                price_el = await item.query_selector('[data-testid="price"]')
                price_text = await price_el.inner_text() if price_el else "0"
                price = int(price_text.replace("¥", "").replace(",", "").strip()) if price_el else 0

                img = await item.query_selector("img")
                thumbnail = await img.get_attribute("src") if img else ""

                products.append(Product(
                    id=pid,
                    title=title,
                    price=price,
                    url=f"https://jp.mercari.com{href}",
                    thumbnail=thumbnail,
                    posted_at=datetime.now(),
                ))
                self.seen_ids.add(pid)
            except Exception:
                continue
    except Exception as e:
        print(f"  検索エラー [{keyword}]: {e}")
    return products
```

# ============================================================

# 🔁 メイン監視ループ

# ============================================================

class ResaleMonitor:
def **init**(self):
self.roi_engine = ROIEngine()
self.discord = DiscordNotifier(CONFIG[“discord_webhook”])
self.scraper = MercariScraper()
self.today_results = []

```
async def run(self):
    print("=" * 55)
    print("  転売AI監視システム 起動")
    print(f"  監視周期    : {CONFIG['scan_interval']}秒")
    print(f"  ROI閾値     : {CONFIG['min_roi']}%")
    print(f"  最低利益    : ¥{CONFIG['min_profit']:,}")
    print(f"  通知上限    : {CONFIG['daily_notify_limit']}件/日")
    print("=" * 55)

    self.discord.send_message(
        f"🚀 **転売AI監視システム 起動**\n"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"ROI閾値:{CONFIG['min_roi']}% | 利益閾値:¥{CONFIG['min_profit']:,}"
    )

    await self.scraper.setup()
    try:
        while True:
            await self._scan()
            print(f"  💤 {CONFIG['scan_interval']}秒後に次のスキャン...")
            await asyncio.sleep(CONFIG["scan_interval"])
    except KeyboardInterrupt:
        print("\n⛔ 監視終了")
        self.discord.send_daily_summary(self.today_results)
    finally:
        await self.scraper.teardown()

async def _scan(self):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] 🔍 スキャン中...")
    candidates = []

    for kw in CONFIG["keywords"]:
        products = await self.scraper.search(kw)
        print(f"  [{kw}] {len(products)}件 新着")
        for p in products:
            result = self.roi_engine.calculate(p)
            if self.roi_engine.is_worth_notifying(result):
                candidates.append(result)

    candidates.sort(key=lambda r: r.priority_score, reverse=True)
    print(f"  📊 通知候補: {len(candidates)}件")

    for r in candidates:
        sent = self.discord.send_alert(r)
        if sent:
            self.today_results.append(r)
        if not self.discord.can_notify():
            break
```

# ============================================================

# 🧪 テストモード（スクレイピング不要）

# ============================================================

def run_test():
print(”=” * 55)
print(”  ROI計算エンジン テスト”)
print(”=” * 55)

```
engine = ROIEngine()
notifier = DiscordNotifier(CONFIG["discord_webhook"])

samples = [
    Product("t1", "iPhone 13 Pro ジャンク 画面割れ 電源入る",
            12800, "https://jp.mercari.com/item/t1", "",
            datetime.now().replace(hour=23), "画面割れあり", 1, 42),
    Product("t2", "iPhone 12 電源入らない 水没痕あり 部品取りで",
            8500,  "https://jp.mercari.com/item/t2", "",
            datetime.now().replace(hour=14), "水没させました", 3, 200),
    Product("t3", "iPhone 11 Pro 起動不可 画面割れ バッテリー膨張",
            7200,  "https://jp.mercari.com/item/t3", "",
            datetime.now().replace(hour=2), "", 2, 85),
    Product("t4", "iPhone 13 mini 画面浮き ジャンク 説明少なめ",
            9800,  "https://jp.mercari.com/item/t4", "",
            datetime.now().replace(hour=1), "", 1, 30),
]

for p in samples:
    r = engine.calculate(p)
    notify = engine.is_worth_notifying(r)
    print(f"\n{'─'*50}")
    print(f"📱  {p.title}")
    print(f"    仕入     : ¥{p.price:,}")
    print(f"    機種     : {r.model_name}")
    print(f"    販売予測 : ¥{r.sell_price:,}")
    print(f"    修理費   : ¥{r.repair_cost:,}")
    print(f"    手数料   : ¥{r.mercari_fee:,}")
    print(f"    ────────────────────")
    print(f"    利益     : ¥{r.profit:,}")
    print(f"    ROI      : {r.roi}%")
    print(f"    競争回避 : {r.competition_score}/100")
    print(f"    リスク   : {r.risk_level}")
    print(f"    検出故障 : {', '.join(r.issues)}")
    if notify:
        print(f"    ✅ → 通知対象！")
        notifier.send_alert(r)
    else:
        print(f"    ⛔ → 閾値未達")

print(f"\n{'='*55}")
print("テスト完了！Discord URLが設定済みなら通知も届いているはずです")
```

# ============================================================

# 🚀 起動

# ============================================================

if **name** == “**main**”:
import sys
if “–test” in sys.argv:
run_test()
else:
asyncio.run(ResaleMonitor().run())

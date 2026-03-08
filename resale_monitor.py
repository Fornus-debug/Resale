import os
import asyncio
import requests
from datetime import datetime
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "discord_webhook":    os.getenv("DISCORD_WEBHOOK_URL", ""),
    "scan_interval":      15,
    "daily_notify_limit": 20,
    "min_roi":            30,
    "min_profit":         8000,
    "mercari_fee_rate":   0.10,
    "keywords": [
        "junk", "screen crack", "won't turn on",
        "parts only", "won't boot", "water damage",
    ],
    "priority_models": ["iPhone 11", "iPhone 12", "iPhone 13"],
}

MODEL_DATA = {
    "iPhone 13 Pro Max": {"sell_price": 55000, "screen_repair": 8000, "difficulty": 1.3},
    "iPhone 13 Pro":     {"sell_price": 48000, "screen_repair": 7000, "difficulty": 1.2},
    "iPhone 13":         {"sell_price": 38000, "screen_repair": 6000, "difficulty": 1.0},
    "iPhone 12 Pro Max": {"sell_price": 42000, "screen_repair": 7500, "difficulty": 1.2},
    "iPhone 12 Pro":     {"sell_price": 35000, "screen_repair": 6500, "difficulty": 1.1},
    "iPhone 12 mini":    {"sell_price": 22000, "screen_repair": 5500, "difficulty": 1.1},
    "iPhone 12":         {"sell_price": 28000, "screen_repair": 6000, "difficulty": 1.0},
    "iPhone 11 Pro Max": {"sell_price": 32000, "screen_repair": 7000, "difficulty": 1.2},
    "iPhone 11 Pro":     {"sell_price": 28000, "screen_repair": 6500, "difficulty": 1.1},
    "iPhone 11":         {"sell_price": 22000, "screen_repair": 5500, "difficulty": 1.0},
    "DEFAULT":           {"sell_price": 15000, "screen_repair": 6000, "difficulty": 1.0},
}

REPAIR_COST_TABLE = {
    "screen crack":    6000,
    "water damage":    3000,
    "won't turn on":   4000,
    "won't boot":      4000,
    "battery":         3500,
    "won't charge":    2000,
    "camera":          5000,
    "home button":     2000,
    "parts only":      0,
}

KEYWORDS_JP = {
    "junk":            "junuku",
    "screen crack":    "screen-crack",
    "won't turn on":   "no-power",
    "parts only":      "parts",
    "won't boot":      "no-boot",
    "water damage":    "water",
}

MERCARI_KEYWORDS = [
    "junuku",
    "screen-wari",
    "dengen-hairanai",
    "buhin-dori",
    "kido-fuka",
    "suibotsu",
]

MERCARI_SEARCH_KEYWORDS = [
    "junk",
    "screen-crack",
    "won't turn on",
    "parts only",
    "won't boot",
    "water damage",
]

SEARCH_KEYWORDS = [
    "junuku",
    "gamen-ware",
    "dengen-hairanai",
    "buhin-dori",
    "kidou-fuka",
    "suibotsu-kon",
]


@dataclass
class Product:
    id: str
    title: str
    price: int
    url: str
    thumbnail: str
    posted_at: datetime
    description: str = ""
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


class ROIEngine:
    def detect_model(self, title):
        for name, data in MODEL_DATA.items():
            if name == "DEFAULT":
                continue
            if name.lower() in title.lower():
                return name, data
        return "Unknown", MODEL_DATA["DEFAULT"]

    def estimate_repair_cost(self, title, description):
        text = (title + " " + description).lower()
        total = 0
        issues = []
        checks = {
            "screen": ("screen crack", 6000),
            "water":  ("water damage", 3000),
            "power":  ("no power", 4000),
            "boot":   ("no boot", 4000),
            "batt":   ("battery", 3500),
            "charg":  ("charge issue", 2000),
            "camera": ("camera", 5000),
            "home":   ("home button", 2000),
        }
        for key, (label, cost) in checks.items():
            if key in text:
                total += cost
                issues.append(label + "(Y" + str(cost) + ")")
        if len(issues) >= 3:
            total = int(total * 1.3)
            issues.append("multi-fault x1.3")
        if total == 0:
            total = 5000
            issues.append("unknown fault(Y5000)")
        return total, issues

    def calc_competition_score(self, product):
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
        if hour >= 22 or hour <= 6:
            score += 20
        if len(product.description) < 30:
            score += 25
        return min(score, 100)

    def calculate(self, product):
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
            product=product, model_name=model_name, sell_price=sell_price,
            repair_cost=repair_cost, mercari_fee=mercari_fee,
            total_cost=product.price + repair_cost + mercari_fee,
            profit=profit, roi=round(roi, 1), risk_level=risk_level,
            competition_score=competition_score,
            priority_score=round(priority_score, 2), issues=issues,
        )

    def is_worth_notifying(self, result):
        return result.roi >= CONFIG["min_roi"] and result.profit >= CONFIG["min_profit"]


class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self.today_count = 0
        self.today_date = datetime.now().date()

    def _reset_if_new_day(self):
        if datetime.now().date() != self.today_date:
            self.today_count = 0
            self.today_date = datetime.now().date()

    def can_notify(self):
        self._reset_if_new_day()
        return self.today_count < CONFIG["daily_notify_limit"]

    def _color(self, roi):
        if roi >= 60:
            return 0x39FF14
        if roi >= 40:
            return 0xFFD600
        return 0xFF6B35

    def send_alert(self, result):
        if not self.webhook_url:
            print("DISCORD_WEBHOOK_URL not set")
            return False
        if not self.can_notify():
            print("Daily limit reached")
            return False
        p = result.product
        embed = {
            "title": "Alert #" + str(self.today_count + 1),
            "description": p.title,
            "color": self._color(result.roi),
            "url": p.url,
            "fields": [
                {"name": "ROI",          "value": str(result.roi) + "%",           "inline": True},
                {"name": "Profit",       "value": "Y" + str(result.profit),        "inline": True},
                {"name": "Buy Price",    "value": "Y" + str(p.price),              "inline": True},
                {"name": "Model",        "value": result.model_name,               "inline": True},
                {"name": "Sell Price",   "value": "Y" + str(result.sell_price),    "inline": True},
                {"name": "Repair Cost",  "value": "Y" + str(result.repair_cost),   "inline": True},
                {"name": "Fee",          "value": "Y" + str(result.mercari_fee),   "inline": True},
                {"name": "Competition",  "value": str(result.competition_score) + "/100", "inline": True},
                {"name": "Risk",         "value": result.risk_level,               "inline": True},
                {"name": "Issues",       "value": ", ".join(result.issues) or "unknown", "inline": False},
            ],
            "footer": {"text": "Resale Monitor | " + datetime.now().strftime("%H:%M:%S")},
        }
        try:
            res = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
            if res.status_code in (200, 204):
                self.today_count += 1
                print("Sent #" + str(self.today_count) + " ROI:" + str(result.roi) + "% Profit:Y" + str(result.profit))
                return True
            print("Failed: " + str(res.status_code))
            return False
        except Exception as e:
            print("Error: " + str(e))
            return False

    def send_message(self, text):
        if not self.webhook_url:
            return
        try:
            requests.post(self.webhook_url, json={"content": text}, timeout=10)
        except Exception:
            pass

    def send_daily_summary(self, results):
        if not results:
            return
        avg_roi = sum(r.roi for r in results) / len(results)
        best = max(results, key=lambda r: r.roi)
        self.send_message(
            "Summary: " + str(len(results)) + " alerts | "
            "Avg ROI: " + str(round(avg_roi, 1)) + "% | "
            "Best: " + str(best.roi) + "% (" + best.model_name + ")"
        )


class MercariScraper:
    def __init__(self):
        self.seen_ids = set()
        self.browser = None
        self.page = None

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

    async def search(self, keyword):
        products = []
        try:
            url = "https://jp.mercari.com/search?keyword=" + keyword + "&status=on_sale&sort=created_time&order=desc"
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
                    price = int(price_text.replace("Y", "").replace(",", "").strip()) if price_el else 0
                    img = await item.query_selector("img")
                    thumbnail = await img.get_attribute("src") if img else ""
                    products.append(Product(
                        id=pid, title=title, price=price,
                        url="https://jp.mercari.com" + href,
                        thumbnail=thumbnail, posted_at=datetime.now(),
                    ))
                    self.seen_ids.add(pid)
                except Exception:
                    continue
        except Exception as e:
            print("Search error [" + keyword + "]: " + str(e))
        return products


class ResaleMonitor:
    def __init__(self):
        self.roi_engine = ROIEngine()
        self.discord = DiscordNotifier(CONFIG["discord_webhook"])
        self.scraper = MercariScraper()
        self.today_results = []

    async def run(self):
        print("Resale Monitor Starting...")
        print("Interval: " + str(CONFIG["scan_interval"]) + "s")
        print("Min ROI: " + str(CONFIG["min_roi"]) + "%")
        print("Min Profit: Y" + str(CONFIG["min_profit"]))
        self.discord.send_message(
            "Resale Monitor Started\n"
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " | ROI>=" + str(CONFIG["min_roi"])
            + "% | Profit>=Y" + str(CONFIG["min_profit"])
        )
        await self.scraper.setup()
        try:
            while True:
                await self._scan()
                print("Waiting " + str(CONFIG["scan_interval"]) + "s...")
                await asyncio.sleep(CONFIG["scan_interval"])
        except KeyboardInterrupt:
            print("Stopped")
            self.discord.send_daily_summary(self.today_results)
        finally:
            await self.scraper.teardown()

    async def _scan(self):
        now = datetime.now().strftime("%H:%M:%S")
        print("[" + now + "] Scanning...")
        candidates = []
        for kw in CONFIG["keywords"]:
            products = await self.scraper.search(kw)
            print("  [" + kw + "] " + str(len(products)) + " new items")
            for p in products:
                result = self.roi_engine.calculate(p)
                if self.roi_engine.is_worth_notifying(result):
                    candidates.append(result)
        candidates.sort(key=lambda r: r.priority_score, reverse=True)
        print("Candidates: " + str(len(candidates)))
        for r in candidates:
            sent = self.discord.send_alert(r)
            if sent:
                self.today_results.append(r)
            if not self.discord.can_notify():
                break


if __name__ == "__main__":
    asyncio.run(ResaleMonitor().run())

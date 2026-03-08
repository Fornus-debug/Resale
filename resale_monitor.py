import os
import time
import requests
import re
from datetime import datetime
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "discord_webhook":    os.getenv("DISCORD_WEBHOOK_URL", ""),
    "scan_interval":      30,
    "daily_notify_limit": 20,
    "min_roi":            30,
    "min_profit":         8000,
    "mercari_fee_rate":   0.10,
    "keywords": [
        "ジャンク iPhone",
        "画面割れ iPhone",
        "電源入らない iPhone",
        "部品取り iPhone",
        "起動不可 iPhone",
        "水没 iPhone",
    ],
    "priority_models": ["iPhone 11", "iPhone 12", "iPhone 13"],
}

MODEL_DATA = {
    "iPhone 13 Pro Max": {"sell_price": 55000, "difficulty": 1.3},
    "iPhone 13 Pro":     {"sell_price": 48000, "difficulty": 1.2},
    "iPhone 13":         {"sell_price": 38000, "difficulty": 1.0},
    "iPhone 12 Pro Max": {"sell_price": 42000, "difficulty": 1.2},
    "iPhone 12 Pro":     {"sell_price": 35000, "difficulty": 1.1},
    "iPhone 12 mini":    {"sell_price": 22000, "difficulty": 1.1},
    "iPhone 12":         {"sell_price": 28000, "difficulty": 1.0},
    "iPhone 11 Pro Max": {"sell_price": 32000, "difficulty": 1.2},
    "iPhone 11 Pro":     {"sell_price": 28000, "difficulty": 1.1},
    "iPhone 11":         {"sell_price": 22000, "difficulty": 1.0},
    "DEFAULT":           {"sell_price": 15000, "difficulty": 1.0},
}


@dataclass
class Product:
    id: str
    title: str
    price: int
    url: str
    thumbnail: str
    posted_at: datetime
    description: str = ""

@dataclass
class ROIResult:
    product: Product
    model_name: str
    sell_price: int
    repair_cost: int
    mercari_fee: int
    profit: int
    roi: float
    risk_level: str
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
        checks = [
            ("screen",  "screen crack", 6000),
            ("water",   "water damage", 3000),
            ("power",   "no power",     4000),
            ("boot",    "no boot",      4000),
            ("batt",    "battery",      3500),
            ("charg",   "charge",       2000),
            ("camera",  "camera",       5000),
        ]
        for key, label, cost in checks:
            if key in text:
                total += cost
                issues.append(label + "(Y" + str(cost) + ")")
        if len(issues) >= 3:
            total = int(total * 1.3)
            issues.append("multi x1.3")
        if total == 0:
            total = 5000
            issues.append("unknown(Y5000)")
        return total, issues

    def calculate(self, product):
        model_name, model_info = self.detect_model(product.title)
        sell_price = model_info["sell_price"]
        difficulty = model_info["difficulty"]
        repair_cost, issues = self.estimate_repair_cost(product.title, product.description)
        repair_cost = int(repair_cost * difficulty)
        mercari_fee = int(sell_price * CONFIG["mercari_fee_rate"])
        profit = sell_price - product.price - repair_cost - mercari_fee
        roi = (profit / product.price * 100) if product.price > 0 else 0
        if roi >= 60:   risk_level = "LOW"
        elif roi >= 40: risk_level = "MID"
        else:           risk_level = "HIGH"
        priority_score = (roi * 0.6) + (profit / 1000 * 0.4)
        for pm in CONFIG["priority_models"]:
            if pm.lower() in product.title.lower():
                priority_score *= 1.2
                break
        return ROIResult(
            product=product, model_name=model_name, sell_price=sell_price,
            repair_cost=repair_cost, mercari_fee=mercari_fee,
            profit=profit, roi=round(roi, 1), risk_level=risk_level,
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
        if roi >= 60: return 0x39FF14
        if roi >= 40: return 0xFFD600
        return 0xFF6B35

    def send_alert(self, result):
        if not self.webhook_url or not self.can_notify():
            return False
        p = result.product
        embed = {
            "title": "Alert #" + str(self.today_count + 1),
            "description": p.title,
            "color": self._color(result.roi),
            "url": p.url,
            "fields": [
                {"name": "ROI",        "value": str(result.roi) + "%",          "inline": True},
                {"name": "Profit",     "value": "Y" + str(result.profit),       "inline": True},
                {"name": "Buy Price",  "value": "Y" + str(p.price),             "inline": True},
                {"name": "Model",      "value": result.model_name,              "inline": True},
                {"name": "Sell Est",   "value": "Y" + str(result.sell_price),   "inline": True},
                {"name": "Repair",     "value": "Y" + str(result.repair_cost),  "inline": True},
                {"name": "Risk",       "value": result.risk_level,              "inline": True},
                {"name": "Issues",     "value": ", ".join(result.issues),       "inline": False},
            ],
            "footer": {"text": "Resale Monitor | " + datetime.now().strftime("%H:%M:%S") + " | " + str(self.today_count+1) + "/" + str(CONFIG["daily_notify_limit"])},
        }
        if p.thumbnail:
            embed["thumbnail"] = {"url": p.thumbnail}
        try:
            res = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
            if res.status_code in (200, 204):
                self.today_count += 1
                print("  Sent #" + str(self.today_count) + " ROI:" + str(result.roi) + "%")
                return True
            return False
        except Exception as e:
            print("  Discord error: " + str(e))
            return False

    def send_message(self, text):
        if not self.webhook_url:
            return
        try:
            requests.post(self.webhook_url, json={"content": text}, timeout=10)
        except Exception:
            pass


class MercariScraper:
    def __init__(self):
        self.seen_ids = set()

    def search(self, keyword, label):
        products = []
        try:
            encoded = requests.utils.quote(keyword)
            url = "https://jp.mercari.com/search?keyword=" + encoded + "&status=on_sale&sort=created_time&order=desc"

            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
"Accept-Language": "ja",
"Accept": "text/html,application/xhtml+xml",
eWebKit/605.1.15",
            }
            res = requests.get(url, headers=headers, timeout=15)

            if res.status_code != 200:
                # フォールバック: 別のエンドポイント試行
                return self._search_fallback(keyword, label)

            ids = re.findall(r'm\d{10,}', res.text)
            titles = re.findall(r'"name"\s*:\s*"([^"]{5,80})"', res.text)
            prices = re.findall(r'"price"\s*:\s*(\d+)', res.text)

            for i in range(min(len(ids), len(titles), len(prices), 20)):
                pid = ids[i]
                if pid in self.seen_ids:
                    continue
                price = int(prices[i])
                if price <= 0:
                    continue
                products.append(Product(
                    id=pid, title=titles[i], price=price,
                    url="https://jp.mercari.com/item/" + pid,
                    thumbnail="", posted_at=datetime.now(),
                ))
                self.seen_ids.add(pid)

        except Exception as e:
            print("  Search error [" + label + "]: " + str(e))
            return self._search_fallback(keyword, label)
        return products

    def _search_fallback(self, keyword, label):
        products = []
        try:
            encoded = requests.utils.quote(keyword)
            url = "https://jp.mercari.com/search?keyword=" + encoded + "&status=on_sale&sort=created_time&order=desc"
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                "Accept-Language": "ja",
            }
            res = requests.get(url, headers=headers, timeout=15)
            ids = re.findall(r'"id":"(m\d+)"', res.text)
            titles = re.findall(r'"name":"([^"]{5,80})"', res.text)
            prices = re.findall(r'"price":(\d{3,6})', res.text)

            for i in range(min(len(ids), len(titles), len(prices), 20)):
                pid = ids[i]
                if pid in self.seen_ids:
                    continue
                price = int(prices[i])
                if price <= 0:
                    continue
                products.append(Product(
                    id=pid, title=titles[i], price=price,
                    url="https://jp.mercari.com/item/" + pid,
                    thumbnail="", posted_at=datetime.now(),
                ))
                self.seen_ids.add(pid)
            print("  [fallback] " + label + " " + str(len(products)) + " items")
        except Exception as e:
            print("  Fallback error [" + label + "]: " + str(e))
        return products


class ResaleMonitor:
    def __init__(self):
        self.roi_engine = ROIEngine()
        self.discord = DiscordNotifier(CONFIG["discord_webhook"])
        self.scraper = MercariScraper()
        self.today_results = []

    def run(self):
        print("Resale Monitor Starting...")
        print("Interval: " + str(CONFIG["scan_interval"]) + "s")
        self.discord.send_message(
            "Resale Monitor Started\n"
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " | ROI>=" + str(CONFIG["min_roi"])
            + "% | Profit>=Y" + str(CONFIG["min_profit"])
        )
        while True:
            try:
                self._scan()
            except Exception as e:
                print("Scan error: " + str(e))
            print("Waiting " + str(CONFIG["scan_interval"]) + "s...")
            time.sleep(CONFIG["scan_interval"])

    def _scan(self):
        now = datetime.now().strftime("%H:%M:%S")
        print("[" + now + "] Scanning...")
        candidates = []
        for kw in CONFIG["keywords"]:
            label = kw.split()[0]
            products = self.scraper.search(kw, label)
            print("  [" + label + "] " + str(len(products)) + " items")
            for p in products:
                result = self.roi_engine.calculate(p)
                if self.roi_engine.is_worth_notifying(result):
                    candidates.append(result)
        candidates.sort(key=lambda r: r.priority_score, reverse=True)
        print("Candidates: " + str(len(candidates)))
        for r in candidates:
            if self.discord.send_alert(r):
                self.today_results.append(r)
            if not self.discord.can_notify():
                break


if __name__ == "__main__":
    ResaleMonitor().run()

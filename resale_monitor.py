import os
import asyncio
import requests
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
        "%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF",
        "%E7%94%BB%E9%9D%A2%E5%89%B2%E3%82%8C",
        "%E9%9B%BB%E6%BA%90%E5%85%A5%E3%82%89%E3%81%AA%E3%81%84",
        "%E9%83%A8%E5%93%81%E5%8F%96%E3%82%8A",
        "%E8%B5%B7%E5%8B%95%E4%B8%8D%E5%8F%AF",
        "%E6%B0%B4%E6%B2%A1",
    ],
    "keyword_labels": [
        "junk", "screen-crack", "no-power",
        "parts", "no-boot", "water",
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
            ("screen", "screen crack", 6000),
            ("water",  "water damage", 3000),
            ("power",  "no power",     4000),
            ("boot",   "no boot",      4000),
            ("batt",   "battery",      3500),
            ("charg",  "charge issue", 2000),
            ("camera", "camera",       5000),
        ]
        for key, label, cost in checks:
            if key in text:
                total += cost
                issues.append(label + "(Y" + str(cost) + ")")
        if len(issues) >= 3:
            total = int(total * 1.3)
            issues.append("multi-fault x1.3")
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
        if roi >= 60:
            risk_level = "LOW"
        elif roi >= 40:
            risk_level = "MID"
        else:
            risk_level = "HIGH"
        return ROIResult(
            product=product, model_name=model_name, sell_price=sell_price,
            repair_cost=repair_cost, mercari_fee=mercari_fee,
            profit=profit, roi=round(roi, 1), risk_level=risk_level, issues=issues,
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
        if not self.webhook_url:
            return False
        if not self.can_notify():
            return False
        p = result.product
        embed = {
            "title": "Alert #" + str(self.today_count + 1),
            "description": p.title,
            "color": self._color(result.roi),
            "url": p.url,
            "fields": [
                {"name": "ROI",         "value": str(result.roi) + "%",         "inline": True},
                {"name": "Profit",      "value": "Y" + str(result.profit),      "inline": True},
                {"name": "Buy Price",   "value": "Y" + str(p.price),            "inline": True},
                {"name": "Model",       "value": result.model_name,             "inline": True},
                {"name": "Sell Est",    "value": "Y" + str(result.sell_price),  "inline": True},
                {"name": "Repair Est",  "value": "Y" + str(result.repair_cost), "inline": True},
                {"name": "Risk",        "value": result.risk_level,             "inline": True},
                {"name": "Issues",      "value": ", ".join(result.issues),      "inline": False},
            ],
            "footer": {"text": "Resale Monitor | " + datetime.now().strftime("%H:%M:%S")},
        }
        if p.thumbnail:
            embed["thumbnail"] = {"url": p.thumbnail}
        try:
            res = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
            if res.status_code in (200, 204):
                self.today_count += 1
                print("Sent #" + str(self.today_count) + " ROI:" + str(result.roi) + "%")
                return True
            return False
        except Exception as e:
            print("Discord error: " + str(e))
            return False

    def send_message(self, text):
        if not self.webhook_url:
            return
        try:
            requests.post(self.webhook_url, json={"content": text}, timeout=10)
        except Exception:
            pass


class MercariAPI:
    def __init__(self):
        self.seen_ids = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Accept": "application/json",
            "X-Platform": "web",
        })

    def search(self, keyword_encoded, label):
        products = []
        try:
            url = (
                "https://api.mercari.jp/v2/entities:search"
                "?pageSize=30"
                "&searchSessionId=monitor"
                "&indexRouting=INDEX_ROUTING_UNSPECIFIED"
                "&searchCondition.keyword=" + keyword_encoded +
                "&searchCondition.status=STATUS_ON_SALE"
                "&searchCondition.sort=SORT_CREATED_TIME"
                "&searchCondition.order=ORDER_DESC"
            )
            res = self.session.get(url, timeout=15)
            if res.status_code != 200:
                print("API error: " + str(res.status_code) + " [" + label + "]")
                return []
            data = res.json()
            items = data.get("items", [])
            for item in items:
                pid = item.get("id", "")
                if not pid or pid in self.seen_ids:
                    continue
                price = int(item.get("price", 0))
                if price <= 0:
                    continue
                title = item.get("name", "")
                thumbnail = item.get("thumbnails", [""])[0] if item.get("thumbnails") else ""
                products.append(Product(
                    id=pid,
                    title=title,​​​​​​​​​​​​​​​​

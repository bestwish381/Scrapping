import logging
import sys
import threading
import concurrent.futures
import time

from retrying import retry
from curl_cffi import requests
from datetime import datetime, timezone

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] - %(message)s', datefmt='%d-%m-%y %H:%M:%S')

# https://www.vinted.co.uk/catalog?size_ids[]=207&size_ids[]=208&size_ids[]=209&size_ids[]=210&size_ids[]=211&size_ids[]=212&brand_ids[]=53&brand_ids[]=14&brand_ids[]=162&brand_ids[]=21099&brand_ids[]=345&brand_ids[]=245062&brand_ids[]=359177&brand_ids[]=484362&brand_ids[]=313669&brand_ids[]=8715&brand_ids[]=378906&brand_ids[]=140618&brand_ids[]=1798422&brand_ids[]=597509&brand_ids[]=1065021&brand_ids[]=57144&brand_ids[]=345731&brand_ids[]=269830&brand_ids[]=99164&brand_ids[]=73458&brand_ids[]=670432&brand_ids[]=719079&brand_ids[]=299684&brand_ids[]=1985410&brand_ids[]=311812&brand_ids[]=291429&brand_ids[]=1037965&brand_ids[]=472855&brand_ids[]=511110&brand_ids[]=299838&brand_ids[]=8139&brand_ids[]=401801&brand_ids[]=3063&brand_ids[]=1412112&brand_ids[]=164166&brand_ids[]=190014&brand_ids[]=46923&brand_ids[]=506331&brand_ids[]=13727&brand_ids[]=345562&brand_ids[]=335419&brand_ids[]=318349&brand_ids[]=276609&order=newest_first


class Vinted:
    def __init__(self):
        # LOCKED DOWN
        self.start_epoch = 1721161154
        self.end_epoch = self.start_epoch + (3 * 24 * 60 * 60)  # 3 days in seconds
        # LOCKED DOWN

        self.rate_limit_errors = 0
        self.max_workers = 64
        self.min_workers = 32
        self.workers = self.max_workers
        self.lock = threading.Lock()

        self.last_id = 0
        self.request_timeout = 3  # Seconds
        self.maximum_delay = 15  # Seconds
        self.country_ids = [13]  # UK
        self.size_ids = [207, 208, 209, 210, 211, 212]
        self.brand_ids = [53, 14, 162, 21099, 345, 245062, 359177, 484362, 313669, 8715, 378906, 140618, 1798422, 597509, 1065021, 57144, 345731, 269830, 99164, 73458, 670432, 719079, 299684, 1985410, 311812, 291429, 1037965, 472855, 511110, 299838, 8139, 401801, 3063, 1412112, 164166, 190014, 46923, 506331, 13727, 345562, 335419, 318349, 276609]
        self.checked_item_ids = set()  # Initialize the set to keep track of checked item IDs
        self.sent_item_ids = set()  # Initialize the set to keep track of sent item IDs

        self.lowest_offset = None
        self.highest_offset = None

        self._webhook_urls = [
            # 'https://discord.com/api/webhooks/1261692483302199428/yeEIU_BOuH9FUg5OCw0slFrxnAwalXUqJPQeyfHYq8kIboyoxX5H_CmPnn_Pf0NJKFxq', # Szymon
            'https://discord.com/api/webhooks/1250024014450262016/QtU0vylPOcK4N3Oosj-k8yfg2x4pRzcubKCVxqTC0SL4Am9Z1Y1d9DIcw_INU4UZvlLI' # Personal
        ]

        logging.info("Starting new Vinted session")
        self.proxies = {
            'http': 'socks5://awsppopv-rotate:k5ly2xutgjqn@p.webshare.io:80',
            'https': 'socks5://awsppopv-rotate:k5ly2xutgjqn@p.webshare.io:80'
        }

        self.cookies = self.get_session_cookie()

    def get_session_cookie(self):
        logging.info("Getting session cookie")

        data = requests.get('https://www.vinted.co.uk', impersonate='chrome', proxies=self.proxies)
        data.raise_for_status()

        return data.cookies.get_dict()

    @retry(stop_max_attempt_number=3)
    def get_catalog_items(self, amount=1):
        logging.info(f"Getting {amount} newest items from Vinted catalog")

        data = requests.get(
            url=f'https://www.vinted.co.uk/api/v2/catalog/items?per_page={amount}&order=newest_first',
            headers={
                'Cache-Control': 'no-cache',
                'Referer': 'https://vinted.co.uk/',
                'Origin': 'https://www.vinted.co.uk/catalog',
                'Platform': 'Windows',
                'Accept-Language': 'en-GB',
                'Content-Type': "application/json",
            },
            cookies=self.cookies,
            proxies=self.proxies,
            impersonate='chrome'
        )

        if data.status_code in [401]:
            self.cookies = self.get_session_cookie()
            return self.get_catalog_items(amount)
        elif data.status_code == 429:
            time.sleep(1)

        data.raise_for_status()

        return data.json().get('items', [])

    @retry(stop_max_attempt_number=1)
    def get_item_details(self, item_id):
        data = requests.get(
            url=f'https://www.vinted.co.uk/api/v2/items/{item_id}',
            headers={
                'Cache-Control': 'no-cache',
                'Referer': 'https://vinted.co.uk/',
                'Origin': 'https://www.vinted.co.uk/catalog',
                'Platform': 'Windows',
                'Accept-Language': 'en-GB',
                'Content-Type': "application/json"
            },
            cookies=self.cookies,
            proxies=self.proxies,
            timeout=self.request_timeout,
            impersonate='chrome'
        )

        logging.info(f"item_id: {item_id}\tstatus_code: {data.status_code}\toffset: {int(item_id) - int(self.last_id)}\trate_limit_errors: {self.rate_limit_errors}\tworkers: {self.workers}")

        if data.status_code == 429:
            with self.lock:
                self.rate_limit_errors += 1
            return None

        if data.status_code in [404]:
            return None

        data.raise_for_status()

        data_json = data.json()

        if data_json.get('code') != 0:
            return None

        return data_json

    def send_discord_message(self, item):
        logging.info(f"Sending Discord message for item {item['id']}")
        label_price = f'{item["price"]["amount"]} {item["price"]["currency_code"]}'
        label_size = item['size']
        label_brand = item['brand']
        label_user_rating = ('⭐️' * round(item['user']['feedback_reputation'] * 5)) + '☆' * (
                    5 - round(item['user']['feedback_reputation'] * 5))
        label_condition = item['status']
        label_updated_at = item['updated_at_ts']
        dt_obj = datetime.fromisoformat(label_updated_at)
        dt_obj_utc = dt_obj.astimezone(timezone.utc)
        epoch_time = int(dt_obj_utc.timestamp())

        if 'photos' in item and item['photos']:
            photo_embed = item['photos'][0]['full_size_url']
        else:
            photo_embed = None  # or a default image URL
        item_id = item['id']

        offset = int(item['id']) - int(self.last_id)
        if self.highest_offset is None or offset > self.highest_offset:
            self.highest_offset = offset
        if self.lowest_offset is None or offset < self.lowest_offset:
            self.lowest_offset = offset

        embed_fields = [
            {"name": "Lowest Offset", "value": self.lowest_offset, "inline": True},
            {"name": "Highest Offset", "value": self.highest_offset, "inline": True},
            {"name": "Current Offset", "value": offset, "inline": True},
            {"name": "💰 Price", "value": label_price, "inline": True},
            {"name": "📏 Size", "value": label_size, "inline": True},
            {"name": "🏷️ Brand", "value": label_brand, "inline": True},
            {"name": "🌍 Country", "value": item['user']['country_code'], "inline": True},
            {"name": "⭐️ User Rating", "value": f"{label_user_rating} ({item['user']['feedback_count']})", "inline": True},
            {"name": "📦 Condition", "value": label_condition, "inline": True},
            {"name": '📅 Updated', "value": f'<t:{epoch_time}:R>', "inline": True},
            {"name": "🔗 View on Vinted", "value": f"[View on Vinted](https://www.vinted.co.uk/items/{item_id})", "inline": False},
            {"name": "📨 Send Message", "value": f"[Send Message](https://www.vinted.co.uk/items/{item_id}/want_it/new?button_name=receiver_id={item_id})", "inline": False},
            {"name": "💸 Buy", "value": f"[Buy](https://www.vinted.co.uk/transaction/buy/new?source_screen=item&transaction%5Bitem_id%5D={item_id})", "inline": False}
        ]

        embed_data = {
            "title": f"{label_brand} {label_size} for {label_price}",
            "description": f"Condition: {label_condition}",
            "url": f"https://www.vinted.co.uk/items/{item_id}",
            "image": {
                "url": photo_embed
            },
            "fields": embed_fields
        }

        data = {
            "embeds": [embed_data]
        }

        for webhook_url in self._webhook_urls:
            response = requests.post(webhook_url, json=data)
            response.raise_for_status()

        logging.info(f"Discord message(s) sent for item {item['id']}")

    def process_possible_item_id(self, item_id):
        if int(item_id) in self.checked_item_ids:
            return False

        if int(item_id) in self.sent_item_ids:
            return False

        item_details = self.get_item_details(item_id)
        if item_details is None:
            return None

        item = item_details.get('item')

        if item['country_id'] not in self.country_ids:
            return False

        if item['size_id'] not in self.size_ids:
            return False

        if item['brand_id'] not in self.brand_ids:
            return False

        updated_at = item['updated_at_ts']
        dt_obj = datetime.fromisoformat(updated_at)
        dt_obj_utc = dt_obj.astimezone(timezone.utc)
        epoch_time = int(dt_obj_utc.timestamp())
        current_epoch_time = int(datetime.now(timezone.utc).timestamp())

        if current_epoch_time - epoch_time > self.maximum_delay:
            return False

        self.checked_item_ids.add(int(item['id']))
        self.sent_item_ids.add(int(item['id']))
        self.send_discord_message(item)

        return True

    def adjust_workers_based_on_rate_limit(self):
        with self.lock:
            if self.rate_limit_errors > 100:
                self.workers = max(self.min_workers, self.workers // 2)
                self.rate_limit_errors = 0
            elif self.rate_limit_errors < 10:
                self.workers = min(self.max_workers, self.workers * 2)
                self.rate_limit_errors = 0

    def monitor_catalog(self):
        while True:
            self.adjust_workers_based_on_rate_limit()
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
                current_epoch = int(time.time())
                if current_epoch > self.end_epoch:
                    logging.error("The allowed running period has ended. Exiting program.")
                    sys.exit()

                catalog_items = self.get_catalog_items()
                if not catalog_items:
                    continue

                catalog_item = catalog_items[0]
                if int(catalog_item['id']) >= int(self.last_id):
                    self.last_id = catalog_item['id']

                    id_list = list(range(self.last_id + 0, self.last_id + 5000))
                    futures = {executor.submit(self.process_possible_item_id, item_id): item_id for item_id in id_list}

                    none_counter = 0
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result()
                            if result is None:
                                none_counter += 1
                                if none_counter >= 100:
                                    logging.debug("100 products failed to resolve, retrieving new catalog items.")
                                    break
                            else:
                                none_counter = 0
                        except Exception as e:
                            logging.error(f"Exception occurred: {e}")

                    # Cancel any remaining futures
                    for future in futures:
                        if not future.done():
                            future.cancel()


if __name__ == '__main__':
    vinted = Vinted()
    vinted.monitor_catalog()

import json
import logging
import threading
import concurrent.futures
import time
import csv
import os

from retrying import retry
from curl_cffi import requests
from datetime import datetime, timezone
from proxy_manager import ProxyManager

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] - %(message)s', datefmt='%d-%m-%y %H:%M:%S')

# TODO: Add a rate limiter to prevent getting rate limited by Vinted (analyze the rate limit and implement rate limiter)
# TODO: Add multi-processing (multiple process instances) in order to properly scale this application on all CPU cores
# TODO: Profile the application to find bottlenecks and optimize the code
# TODO: Add a database to store the items and their details (nice to have)


class Vinted:
    def __init__(self):
        """
        Initialize the Vinted class with default settings and configurations.
        """
        self.get_item_details_start_time = time.time()
        self.get_item_details_request_count = 0

        self.catalog_items = 5000
        self.rate_limit_errors = 0
        self.max_workers = 64
        self.min_workers = 16
        self.workers = self.max_workers
        self.lock = threading.Lock()

        self.last_id = 0
        self.request_timeout = 3  # Seconds
        self.maximum_delay = 15  # Seconds
        settings = self._read_settings()
        self.brand_ids = settings['brand_ids']
        self.size_ids = settings['size_ids']
        self.country_ids = settings['country_ids']
        self.checked_item_ids = set()  # Initialize the set to keep track of checked item IDs
        self.sent_item_ids = set()  # Initialize the set to keep track of sent item IDs

        self.lowest_offset = None
        self.highest_offset = None

        self._webhook_urls = [
            # 'https://discord.com/api/webhooks/1261692483302199428/yeEIU_BOuH9FUg5OCw0slFrxnAwalXUqJPQeyfHYq8kIboyoxX5H_CmPnn_Pf0NJKFxq'
        ]

        logging.info("Starting new Vinted session")
        self.proxy_manager = ProxyManager()
        self.cookies = self.get_session_cookie()

    def _read_settings(self):
        """
        Read settings from the configuration file.

        Returns:
            dict: A dictionary containing the settings.
        """
        with open('config/settings.json', 'r') as file:
            return json.load(file)

    def get_session_cookie(self):
        """
        Retrieve a session cookie from Vinted.

        Returns:
            dict: A dictionary containing the session cookies.
        """
        logging.info("Getting session cookie")

        data = requests.get('https://www.vinted.co.uk', impersonate='chrome', proxies=self.proxy_manager.get_proxy())
        data.raise_for_status()

        return data.cookies.get_dict()

    @retry(stop_max_attempt_number=3)
    def get_catalog_items(self, amount=1):
        """
        Retrieve the newest items from the Vinted catalog.

        Args:
            amount (int): The number of items to retrieve.

        Returns:
            list: A list of items from the catalog.
        """
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
            proxies=self.proxy_manager.get_proxy(),
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
        """
        Retrieve details for a specific item.

        Args:
            item_id (int): The ID of the item to retrieve details for.

        Returns:
            dict: A dictionary containing the item details.
        """
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
            proxies=self.proxy_manager.get_proxy(),
            timeout=self.request_timeout,
            impersonate='chrome'
        )

        self.get_item_details_request_count += 1
        elapsed_time = time.time() - self.get_item_details_start_time
        if elapsed_time > 0:
            rps = self.get_item_details_request_count / elapsed_time
        else:
            rps = 0

        # logging.info(f"item_id: {item_id}\tstatus_code: {data.status_code}\toffset: {int(item_id) - int(self.last_id)}\trate_limit_errors: {self.rate_limit_errors}\tworkers: {self.workers}")
        logging.info(f"item_id: {item_id}\tstatus_code: {data.status_code}\toffset: {int(item_id) - int(self.last_id)}\trate_limit_errors: {self.rate_limit_errors}\tworkers: {self.workers}\trequests_per_second: {rps:.2f}")
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

    def append_to_csv(self, item, embed_fields):
        """
        Append item details to a CSV file.

        Args:
            item (dict): The item details.
            embed_fields (list): A list of embedded fields to include in the CSV.
        """
        csv_file_path = 'sent_items.csv'
        csv_headers = ["Item ID", "Price", "Size", "Brand", "User Rating", "Condition", "Country", "Discovery Time",
                       "Current Epoch", "Item Epoch", "Lowest Offset", "Highest Offset", "Current Offset"]

        # Check if CSV exists, if not, create it and write headers
        if not os.path.exists(csv_file_path):
            with open(csv_file_path, mode='w', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(csv_headers)

        # Extract data from embed_fields
        data_row = [
            item['id'],
            next((field['value'] for field in embed_fields if field['name'] == "💰 Price"), None),
            next((field['value'] for field in embed_fields if field['name'] == "📏 Size"), None),
            next((field['value'] for field in embed_fields if field['name'] == "🏷️ Brand"), None),
            next((field['value'] for field in embed_fields if field['name'] == "⭐️ User Rating"), None),
            next((field['value'] for field in embed_fields if field['name'] == "📦 Condition"), None),
            item['user']['country_code'],
            next((field['value'] for field in embed_fields if field['name'] == 'Discovery time'), None),
            next((field['value'] for field in embed_fields if field['name'] == 'Current epoch'), None),
            next((field['value'] for field in embed_fields if field['name'] == 'Item epoch'), None),
            next((field['value'] for field in embed_fields if field['name'] == "Lowest Offset"), None),
            next((field['value'] for field in embed_fields if field['name'] == "Highest Offset"), None),
            next((field['value'] for field in embed_fields if field['name'] == "Current Offset"), None),
        ]

        with open(csv_file_path, mode='a', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(data_row)

        return True

    def send_discord_message(self, item):
        """
        Send a message to Discord with item details.

        Args:
            item (dict): The item details.
        """
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
        current_time_epoch = int(time.time())
        time_difference = current_time_epoch - epoch_time

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
            {"name": 'Discovery time', "value": f'{time_difference} seconds', "inline": True},
            {"name": 'Current epoch', "value": current_time_epoch, "inline": True},
            {"name": 'Item epoch', "value": epoch_time, "inline": True},
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

        # FIXME: Remove this in 'production', this is added to generate statistics and generate timelines for analysis
        self.append_to_csv(item, embed_fields)

        for webhook_url in self._webhook_urls:
            response = requests.post(webhook_url, json=data)
            response.raise_for_status()

        logging.info(f"Discord message(s) sent for item {item['id']}")

    def process_possible_item_id(self, item_id):
        """
        Process a possible item ID by checking its details and sending a Discord message if it meets criteria.

        Args:
            item_id (int): The ID of the item to process.

        Returns:
            bool: True if the item was processed and sent, False otherwise.
        """
        if int(item_id) in self.checked_item_ids:
            return False

        if int(item_id) in self.sent_item_ids:
            return False

        try:
            item_details = self.get_item_details(item_id)
        except Exception as e:
            logging.error(f"Exception occurred: {e}")
            return False

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
        """
        Adjust the number of workers based on the rate limit errors.
        """
        with self.lock:
            if self.rate_limit_errors > self.catalog_items * 0.10:
                self.workers = max(self.min_workers, self.workers // 2)
                self.rate_limit_errors = 0
            elif self.rate_limit_errors < self.catalog_items * 0.01:
                self.workers = min(self.max_workers, self.workers * 2)
                self.rate_limit_errors = 0

    def monitor_catalog(self):
        """
        Monitor the Vinted catalog for new items and process them.
        """
        while True:
            self.adjust_workers_based_on_rate_limit()
            self.rate_limit_errors = 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
                catalog_items = self.get_catalog_items()
                if not catalog_items:
                    continue

                catalog_item = catalog_items[0]
                if int(catalog_item['id']) >= int(self.last_id):
                    self.last_id = catalog_item['id']

                    id_list = list(range(self.last_id + 0, self.last_id + self.catalog_items))
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
                elif int(catalog_item['id']) < int(self.last_id):
                    logging.error("Detected a lower item ID than the last ID, retrieving new cookies.")
                    self.cookies = self.get_session_cookie()


if __name__ == '__main__':
    vinted = Vinted()
    vinted.monitor_catalog()

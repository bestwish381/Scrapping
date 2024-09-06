import aiohttp
import asyncio
import logging
import requests
import time
from datetime import datetime, timezone
from proxy_manager import ProxyManager

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] - %(message)s', datefmt='%d-%m-%y %H:%M:%S')


class NotFoundError(Exception):
    """Exception raised for errors in the input when an item is not found."""
    def __init__(self, message="Item not found"):
        self.message = message
        super().__init__(self.message)


class Vinted:
    def __init__(self):
        self.get_item_details_start_time = time.time()
        self.get_item_details_request_count = 0

        self.catalog_items = 5000

        self.last_id = 0
        self.request_timeout = 30  # Seconds
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
        self.proxy_manager = ProxyManager()
        asyncio.run(self.initialize())

    async def initialize(self):
        async with aiohttp.ClientSession() as session:
            self.cookies = await self.get_session_cookie(session)

    async def fetch(self, session, url, **kwargs):
        try:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                kwargs['proxy'] = proxy
            async with session.get(url, **kwargs) as response:
                if response.status == 401:
                    self.cookies = await self.get_session_cookie(session)
                    return await self.fetch(session, url, **kwargs)
                elif response.status == 429:
                    await asyncio.sleep(0.1)
                    return await self.fetch(session, url, **kwargs)
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            # logging.error(f"Request failed: {e}")
            return None

    async def get_session_cookie(self, session):
        logging.info("Getting session cookie")
        try:
            async with session.get('https://www.vinted.co.uk') as response:
                response.raise_for_status()
                logging.info(f"Cookies: {response.cookies}")
                return response.cookies
        except Exception as e:
            logging.error(f"Failed to get session cookie: {e}")
            raise

    async def get_catalog_items(self, session, amount=1):
        logging.info(f"Getting {amount} newest items from Vinted catalog")
        url = f'https://www.vinted.co.uk/api/v2/catalog/items?per_page={amount}&order=newest_first'
        response = await self.fetch(
            session,
            url,
            headers={
                'Cache-Control': 'no-cache',
                'Referer': 'https://vinted.co.uk/',
                'Origin': 'https://www.vinted.co.uk/catalog',
                'Platform': 'Windows',
                'Accept-Language': 'en-GB',
                'Content-Type': "application/json",
            },
            cookies=self.cookies
        )
        return response.get('items', []) if response else []

    async def get_item_details(self, session, item_id):
        url = f'https://www.vinted.co.uk/api/v2/items/{item_id}'
        data = await self.fetch(
            session,
            url,
            headers={
                'Cache-Control': 'no-cache',
                'Referer': 'https://vinted.co.uk/',
                'Origin': 'https://www.vinted.co.uk/catalog',
                'Platform': 'Windows',
                'Accept-Language': 'en-GB',
                'Content-Type': "application/json"
            },
            cookies=self.cookies,
            timeout=self.request_timeout
        )

        if data is None:
            return None

        if data.get('code') != 0:
            return None

        return data

    async def send_discord_message(self, item):
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
            {"name": "🛒 Buy Now", "value": f"[Buy Now](https://www.vinted.co.uk/items/{item_id})", "inline": False}
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

    async def process_possible_item_id(self, item_id):
        if int(item_id) in self.checked_item_ids:
            # logging.debug(f"Item {item_id} already checked")
            return None

        if int(item_id) in self.sent_item_ids:
            return False

        logging.info(f"Checking item {item_id}")

        async with aiohttp.ClientSession() as session:
            try:
                item_data = await self.get_item_details(session, item_id)
            except NotFoundError:
                return None

            if not item_data:
                logging.warning(f"No details found for item {item_id}")
                self.checked_item_ids.add(int(item_id))
                return None

            if int(item_id) in self.sent_item_ids:
                logging.debug(f"Item {item_id} already sent")
                return None

            item = item_data.get('item')

            if item['country_id'] not in self.country_ids:
                return False

            if item['size_id'] not in self.size_ids:
                return False

            if item['brand_id'] not in self.brand_ids:
                return False

            await self.send_discord_message(item)
            self.sent_item_ids.add(int(item_id))

            return item_data

    async def monitor_catalog(self):
        async with aiohttp.ClientSession() as session:
            while True:
                catalog_items = await self.get_catalog_items(session)
                if not catalog_items:
                    continue

                catalog_item = catalog_items[0]
                if int(catalog_item['id']) >= int(self.last_id):
                    self.last_id = catalog_item['id']

                    id_list = list(range(self.last_id + 0, self.last_id + self.catalog_items))
                    tasks = [self.process_possible_item_id(item_id) for item_id in id_list]
                    results = await asyncio.gather(*tasks)
                    logging.info(f'Processed {len(results)} items')


if __name__ == '__main__':
    vinted = Vinted()
    asyncio.run(vinted.monitor_catalog())

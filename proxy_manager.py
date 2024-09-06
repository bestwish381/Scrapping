from curl_cffi import requests


class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.current_index = 0

        self.load_proxies()

    def load_proxies(self):
        proxy_source = [
            'https://actproxy.com/proxy-api/bf3d7cf7ecb8b579789d2dbe50f11ffb_17557-46024?format=json&userpass=true',
            'https://actproxy.com/proxy-api/5d8138fef1c0e2455ca2257686593809_17557-46034?format=json&userpass=true'
        ]

        for source in proxy_source:
            response = requests.get(source, impersonate='chrome')
            if response.status_code == 200:
                response_json = response.json()
                for proxy_response in response_json:
                    ip_port, username, password = proxy_response.split(';')

                    self.proxies.append({
                        'http': f'http://{username}:{password}@{ip_port}',
                        'https': f'http://{username}:{password}@{ip_port}'
                    })

                    # self.proxies.append(f'http://{username}:{password}@{ip_port}')
            else:
                print(f"Failed to load proxies from {source}")

    def get_proxy(self):
        if not self.proxies:
            raise ValueError("Proxy list is empty.")

        current_proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)

        return current_proxy

    def disable_proxy(self, proxy):
        if proxy in self.proxies:
            self.proxies.remove(proxy)

            if self.current_index >= len(self.proxies):
                self.current_index = 0


def parse_proxy(proxy_string):
    if not proxy_string:
        return {}
    
    proxy_parts = proxy_string.split(':')
    proxy_config = {}
    
    if len(proxy_parts) >= 4:
        host, port, username, password = proxy_parts
        server_url = f"http://{host}:{port}"
        proxy_config = {
            "server": server_url,
            "username": username,
            "password": password
        }
    elif len(proxy_parts) == 2:
        host, port = proxy_parts
        server_url = f"http://{host}:{port}"
        proxy_config = {
            "server": server_url
        }
    
    return proxy_config
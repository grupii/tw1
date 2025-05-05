import asyncio
from playwright.async_api import async_playwright
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from utils.proxyparser import parse_proxy
from db.connection import get_accounts_collection


class TwitterLogin:
    def __init__(self, username, password, proxy=None):
        self.username = username
        self.password = password
        self.proxy = proxy
        
        self.is_logged_in = False
        self.browser = None
        self.context = None
        self.page = None
        self.LOGIN_URL = "https://x.com/i/flow/login"

        self.login_scenarios = {

            "suspicious_login": {
                "selector": "//*[contains(text(), 'Suspicious login prevented')]",
                "action": "click",
                "action_selector": "//*[contains(text(), 'Got it')]"
            },
            "authentication_code": {
                "selector": "//*[contains(text(), 'Enter code')]",
                "action": "input",
                "prompt_message": "Enter 2FA code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "email_verification": {
                "selector": "//*[contains(text(), 'Confirmation code')]",
                "action": "input",
                "prompt_message": "Enter email verification code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone-email": {
                "selector": "//*[contains(text(), 'Phone or email')]",
                "action": "input",
                "prompt_message": "Enter email or phone number:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone_verification": {
                "selector": "//*[contains(text(), 'Verify your phone')]",
                "action": "input",
                "prompt_message": "Enter phone verification code:",
                "next_button": "//*[contains(text(), 'Next')]"
            },
            "phone_verify_identity": {
                "selector": "//*[contains(text(), 'Phone number')]",
                "action": "input",
                "prompt_message": "Enter the phone number",
                "next_button": "//*[contains(text(), 'Next')]"
            },
        }

    async def check_scenarios(self):
        """
        Check for and handle various login scenarios
        Returns a tuple of (scenario_detected, needs_input, scenario_info)
        """
        for name, scenario in self.login_scenarios.items():
            try:
                print(f"[DEBUG] Checking for {name}...")
                element = await self.page.wait_for_selector(scenario["selector"], state="visible", timeout=1000)
                print(f"Detected {name}")

                if scenario["action"] == "click":
                    action_element = await self.page.wait_for_selector(
                        scenario["action_selector"], state="visible", timeout=1000
                    )
                    await action_element.click()
                    print(f"Clicked {scenario['action_selector']}")
                    return True, False, None

                elif scenario["action"] == "input":
                    input_element = element
                    if "input_selector" in scenario:
                        input_element = await self.page.wait_for_selector(
                            scenario["input_selector"], state="visible", timeout=1000
                        )
                        print(f"Found input element using selector: {scenario['input_selector']}")

                    scenario_info = {
                        "name": name,
                        "element": input_element,
                        "prompt_message": scenario["prompt_message"],
                        "next_button": scenario.get("next_button"),
                        "input_selector": scenario.get("input_selector")
                    }
                    
                    return True, True, scenario_info

            except Exception:
                continue

        return False, False, None
    
    async def handle_verification_steps(self, input_callback):
        """Handle verification steps that require user input."""
        scenario_detected, needs_input, scenario_info = await self.check_scenarios()
        
        while scenario_detected and needs_input and input_callback:

            user_input = await input_callback(scenario_info["prompt_message"])

            print(f"[DEBUG] - Login received input: {user_input[:3]}***")
            
            await scenario_info["element"].focus()
            await asyncio.sleep(0.5)
            await scenario_info["element"].fill(user_input)

            print(f"[DEBUG] Entered input for {scenario_info['name']}")
            
            if "next_button" in scenario_info:
                next_btn = await self.page.wait_for_selector(
                    scenario_info["next_button"],
                    state="visible",
                    timeout=10000
                )
                await next_btn.click()
                
            await asyncio.sleep(3)
            await self.page.wait_for_load_state("networkidle")
            
            scenario_detected, needs_input, scenario_info = await self.check_scenarios()
        
        return scenario_detected, needs_input, scenario_info
            
    async def save_auth(self):
        """Extract auth tokens needed for API requests."""
        cookies = await self.context.cookies()

        tokens = {
            "x-csrf-token": None,
            "authorization": "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "user-agent": None,
            "content-type": "application/json"
        }

        for cookie in cookies:
            if cookie.get("name") == "ct0":
                tokens["x-csrf-token"] = cookie.get("value")
                break
        
        tokens["user-agent"] = await self.page.evaluate("() => navigator.userAgent")

        return tokens, cookies

    async def save_auth_to_db(self, tokens, cookies):
        
        accounts_collection = get_accounts_collection()
        
        result = await accounts_collection.update_one(
            {"username": self.username},
            {
                "$set": {
                    "auth_tokens": tokens,
                    "cookies": cookies,
                    "is_active": True
                }
        },
            upsert=True
        )
        print(f"[*] Updated auth data in database for {self.username}")
        return result

    async def initialize_browser(self, extra_options=None):
        playwright = await async_playwright().start()

        launch_options = {
            "headless": False
        }

        if extra_options and isinstance(extra_options, dict):
            launch_options.update(extra_options)

        self.browser = await playwright.chromium.launch(**launch_options)

        context_options = {}

        if self.proxy:
            proxy_config = parse_proxy(self.proxy)
            if proxy_config:
                context_options["proxy"] = proxy_config


        self.context = await self.browser.new_context(**context_options)
        self.page = await self.context.new_page()
        return self

    async def login(self, username, password, input_callback=None):
        """
        Spin up a browser session and login to Twitter, supports suspicious login attempts.

        Args:
            username (str): Your Twitter Username
            password (str): Your Twitter Password
            input_callback (callable, optional): Handles verifications codes for suspicious logins. Defaults to None.

        Raises:
            Exception: _description_
        """
        
        if not hasattr(self, 'page') or not self.page:
            print("[*] Browser not initialized, creating it now.")
            await self.initialize_browser()

        if not hasattr(self, 'page') or not self.page:
            print("[*] Failed to create browser.")
            raise Exception("[*] Failed to create browser.")
        

        await self.page.goto(self.LOGIN_URL)
        await self.page.wait_for_load_state("networkidle")
        
        current_url = self.page.url
        if current_url in ["https://x.com/login", "https://x.com/i/flow/login"]:
            try:
                print("[*] Starting login process")
                
                username_input = await self.page.wait_for_selector(
                    "//*[contains(text(), 'Phone, email, or username')]",
                    state="visible",
                    timeout=15000
                )

                print("[DEBUG] Found username input")
                await username_input.fill(self.username)
                
                next_button = await self.page.wait_for_selector(
                    "//*[contains(text(), 'Next')]",
                    state="visible",
                    timeout=15000
                )
                await next_button.click()
                print("[DEBUG] Entered username and clicked next")
                
                await self.handle_verification_steps(input_callback)
                
                password_input = await self.page.wait_for_selector(
                        "//*[contains(text(), 'Password')]",
                        state="visible",
                        timeout=10000
                    )
                await password_input.fill(password)
                print("[DEBUG] Entered password")
                
                login_button = await self.page.wait_for_selector(
                        "//button[@data-testid='LoginForm_Login_Button']",
                        state="visible",
                        timeout=10000
                    )
                await login_button.click()
                print("[DEBUG] Clicked login button")
                
                await self.page.wait_for_load_state("networkidle", timeout=15000)
                
                current_url = self.page.url
                if current_url == "https://x.com/home":
                    print("[*] Successfully logged in.")
                else:
                    print("[DEBUG] Checking for any suspicious login prevention")
                    await self.handle_verification_steps(input_callback)
                    
                    current_url = self.page.url
                    if current_url == "https://x.com/home":
                        print("[*] Successfully logged in.")
            
            except Exception as e:
                print(f"[DEBUG] Error during password entry or post-login: {e}")
            
            
            try:
                await self.page.goto("https://x.com/settings/privacy_and_safety")
                await self.page.wait_for_load_state("networkidle", timeout=5000)
                
                if self.page.url == "https://x.com/settings/privacy_and_safety":
                    print("[*] Successfully logged in - verified by settings page access")
                    self.is_logged_in = True
                    tokens, cookies = await self.save_auth()
                    
                    await self.save_auth_to_db(tokens, cookies)
                    
                    return True, tokens
                
                elif self.page.url in ["https://x.com/login", "https://x.com/i/flow/login"]:
                    print("[*] You didn't get to join mile high club. Failed to login")
                    return False
                
                else:
                    print(f"[*] Unexpected URL after login: {self.page.url}")
                    return False

            except Exception as e:
                print(f"[*] Error during final login verificaiton: {e}")
                return False
            
        else:
            print(f"[DEBUG] Not sure where we're redirected, checking login status. {self.page.url}")    
            try:
                await self.page.goto("https://x.com/settings/privacy_and_safety")
                await self.page.wait_for_load_state("networkidle", timeout=5000)
                
                if self.page.url == "https://x.com/settings/privacy_and_safety":
                    print("[*] Successfully logged in - verified by settings page access")
                    self.is_logged_in = True
                    tokens = await self.save_auth()
                    return True, tokens
                
                else:
                    print("[DEBUG] Not logged in despite being on a non-login page")
                    return False
                
            except Exception as e:
                print(f"[DEBUG] Error checking login status: {e}")
                return False


if __name__ == "__main__":
    import asyncio
    import getpass
    import argparse
    
    parser = argparse.ArgumentParser(description="Twitter Login Tool")
    parser.add_argument("-u", "--username", help="Twitter username")
    parser.add_argument("-p", "--password", help="Twitter password (not recommended, use prompt instead)")
    parser.add_argument("--proxy", help="Proxy in format protocol://user:pass@host:port")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    
    args = parser.parse_args()
    
    async def input_callback(prompt):
        return input(prompt)
    
    async def main():
        username = args.username or input("Enter Twitter username: ")
        password = args.password or getpass.getpass("Enter Twitter password: ")
        
        browser_options = {}
        if args.headless:
            browser_options["headless"] = True
        
        twitter_login = TwitterLogin(
            username=username,
            password=password,
            proxy=args.proxy
        )
        
        try:
            await twitter_login.initialize_browser(browser_options)
            
            print(f"[*] Attempting to log in as {username}...")
            login_success, tokens = await twitter_login.login(username, password, input_callback)
            
            if login_success:
                print("[*] Login successful!")
                print("[*] Auth tokens and cookies saved to database")
            else:
                print("[*] Login failed!")
                
        finally:
            if twitter_login.browser:
                print("[*] Closing browser...")
                await twitter_login.browser.close()
    
    asyncio.run(main())
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Optional, Set
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from db.connection import get_accounts_collection


class TwitterScraper:
    """
    A Twitter scraper that navigates to Twitter's messages page and extracts group chats
    and participant information using browser automation and network request interception.
    
    This class captures API responses from Twitter's messaging endpoints, processes the 
    data to extract structured information about group chats and users, and returns this
    information for further processing or storage.
    """
    
    def __init__(self, page, context, account_id: Optional[str] = None, username: Optional[str] = None):
        """
        Initialize the Twitter scraper with browser context and account information.
        
        Args:
            page: The Playwright page object used for navigation and interaction
            context: The Playwright browser context for managing cookies and sessions
            account_id: MongoDB ID of the account being scraped (optional)
            username: Twitter username being scraped (optional)
        """
        self.page = page
        self.context = context
        self.account_id = account_id
        self.username = username
        
    async def scrape_messages(self) -> Dict[str, Any]:
        """
        Navigate to Twitter's messages page and capture specific network requests for group chats.
        
        This method:
        1. Retrieves authentication tokens from the database if available
        2. Sets up request and response interception to capture API data
        3. Navigates to Twitter's messages page
        4. Scrolls through conversations to trigger additional data loading
        5. Processes and returns the captured data
        
        Returns:
            Dict containing captured requests and authentication tokens
        """
        captured_data = {
            "requests": [],
            "tokens": {
                "x-csrf-token": None,
                "authorization": None,
                "user-agent": None,
                "content-type": None
            }
        }
        
        target_urls = [
            "api/1.1/dm/inbox_initial_state.json",
            "api/1.1/dm/user_updates.json"
        ]
        
        try:
            accounts_collection = get_accounts_collection()
            account_data = await accounts_collection.find_one({"username": self.username})
            
            if not account_data:
                print(f"[*] No account found for username: {self.username}")
            elif "auth_tokens" not in account_data:
                print(f"[*] Account found but no auth tokens available for: {self.username}")
            else:
                captured_data["tokens"] = account_data["auth_tokens"]
                print(f"[*] Found auth tokens for {self.username}")
                print(captured_data["tokens"])
        
        except Exception as e:
            print(f"[*] Error retrieving account data: {e}")

        async def capture_request(request):
            url = request.url
            
            if any(target_url in url for target_url in target_urls):
                request_data = {
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                captured_data["requests"].append(request_data)
                
        async def capture_response(response):
            url = response.url
            
            if any(target_url in url for target_url in target_urls):
                try:
                    body = await response.text()

                    for req in captured_data["requests"]:
                        if req["url"] == url:
                            req["response_body"] = body
                            req["response_status"] = response.status
                            break
                except Exception as e:
                    print(f"[ERROR] Error capturing response: {e}")

        self.page.on("request", capture_request)
        self.page.on("response", capture_response)
        
        await self.page.goto("https://x.com/messages")
        await self.page.wait_for_load_state("networkidle", timeout=10000)
        
        print("[*] Messages page loaded. Starting to scroll...")
        
        section_nav = await self.page.query_selector('section[aria-label="Section navigation"]')
        
        if not section_nav:
            print("[ERROR] Could not find section navigation element")
            await self._basic_scroll_and_click()
        else:
            print("[DEBUG] Found section navigation element")

            viewportview_div = await section_nav.query_selector('div[data-viewportview="true"]')
            scrollable_div = viewportview_div or section_nav

            scroll_divs = await section_nav.query_selector_all('div:has-text("scroll")')
            if scroll_divs and len(scroll_divs) > 0:
                print(f"[DEBUG] Found {len(scroll_divs)} potential scroll containers")
                scrollable_div = scroll_divs[0]

            print("[DEBUG] Using found scrollable container for scrolling attempts")
            
            for i in range(5):
                await asyncio.sleep(5)
                print(f"[*] Scroll attempt {i + 1}/5")

                box = await scrollable_div.bounding_box()
                if box:
                    center_x = box['x'] + box['width'] / 2
                    center_y = box['y'] + box['height'] / 2
                    await self.page.mouse.move(center_x, center_y)
                    await self.page.mouse.down()
                    await self.page.wait_for_timeout(100)
                    await self.page.mouse.wheel(0, 500)
                    await self.page.mouse.up()

                try:
                    await self.page.evaluate("""
                        (element) => {
                            if (element && typeof element.scrollBy === 'function') {
                                element.scrollBy(0, 500);
                                return true;
                            } else if (element && typeof element.scrollTop !== 'undefined') {
                                element.scrollTop += 500;
                                return true;
                            }
                            return false;
                        }
                    """, scrollable_div)
                except Exception as e:
                    print(f"[ERROR] Scroll error: {e}")
        
        self.page.remove_listener("request", capture_request)
        self.page.remove_listener("response", capture_response)
        
        return captured_data
    
    async def _basic_scroll_and_click(self) -> None:
        """
        Fallback scrolling method if the standard navigation elements aren't found.
        
        This method performs basic page scrolling and attempts to click on conversations
        to trigger additional data loading.
        """
        for i in range(3):
            await self.page.evaluate("window.scrollBy(0, 500)")
            print(f"[DEBUG] Basic scroll attempt {i + 1}/3")
            await asyncio.sleep(3)

            await self._click_conversation(i)
    
    async def _click_conversation(self, index: int) -> None:
        """
        Attempt to click on a conversation at the specified index.
        
        This helps load additional conversation data and trigger network requests.
        
        Args:
            index: The index of the conversation to click (0-based)
        """
        try:
            conversations = await self.page.query_selector_all('div[data-testid="conversation"]')

            if conversations and index < len(conversations):
                await conversations[index].click()
                print(f"[DEBUG] Clicked on conversation {index + 1}")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"[DEBUG] Error clicking conversation: {e}")
    
    def _extract_group_chats_from_initial_state(self, response_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract group chat information from Twitter's inbox_initial_state.json API response.
        
        This method parses the nested JSON structure to identify group chats and their
        participants, handling multiple possible data formats.
        
        Args:
            response_json: The parsed JSON response from the API
            
        Returns:
            List of structured group chat objects with participant information
        """
        group_chats = []

        if "inbox_initial_state" not in response_json:
            return group_chats

        initial_state = response_json["inbox_initial_state"]

        if "conversations" in initial_state:
            conversations = initial_state["conversations"]

            for conv_id, conv_data in conversations.items():
                if "type" in conv_data and conv_data["type"] == "GROUP_DM":
                    group_chat = {
                        "account_id": self.account_id,
                        "twitter_username": self.username,
                        "conversation_id": conv_id,
                        "name": conv_data.get("name", "Unnamed Group"),
                        "create_time": conv_data.get("create_time"),
                        "created_by_user_id": conv_data.get("created_by_user_id"),
                        "trusted": conv_data.get("trusted", False),
                        "participants": [],
                        "scraped_at": datetime.now(timezone.utc),
                        "source": "inbox_initial_state"
                    }

                    if "participants" in conv_data:
                        participants = []
                        participants_data = conv_data["participants"]

                        if isinstance(participants_data, dict):
                            for range_key, range_participants in participants_data.items():
                                if isinstance(range_participants, dict):
                                    for idx, participant in range_participants.items():
                                        if isinstance(participant, dict):
                                            participant_info = {
                                                "user_id": participant.get("user_id"),
                                                "join_time": participant.get("join_time"),
                                                "is_admin": participant.get("is_admin", False),
                                                "join_conversation_event_id": participant.get(
                                                    "join_conversation_event_id"),
                                                "last_read_event_id": participant.get("last_read_event_id")
                                            }
                                            participants.append(participant_info)

                        elif isinstance(participants_data, list):
                            for participant in participants_data:
                                if isinstance(participant, dict) and "user_id" in participant:
                                    participant_info = {
                                        "user_id": participant.get("user_id"),
                                        "join_time": participant.get("join_time"),
                                        "is_admin": participant.get("is_admin", False),
                                        "join_conversation_event_id": participant.get("join_conversation_event_id"),
                                        "last_read_event_id": participant.get("last_read_event_id")
                                    }
                                    participants.append(participant_info)

                        group_chat["participants"] = participants
                        group_chat["participant_count"] = len(participants)
                        print(f"[*] Extracted {len(participants)} participants for group {conv_id} from initial_state")

                    group_chats.append(group_chat)

        return group_chats
    
    def _extract_group_chats_from_user_updates(self, response_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract group chat information from Twitter's user_updates.json API response.
        
        This method handles a different API response format than the initial state,
        but produces the same standardized output format. It also delegates to
        _extract_group_chats_from_initial_state if the response contains that structure.
        
        Args:
            response_json: The parsed JSON response from the API
            
        Returns:
            List of structured group chat objects with participant information
        """
        group_chats = []

        if "inbox_initial_state" in response_json:
            return self._extract_group_chats_from_initial_state(response_json)

        if "user_events" in response_json:
            user_events = response_json["user_events"]

            if "conversations" in user_events:
                conversations = user_events["conversations"]

                for conv_id, conv_data in conversations.items():
                    if isinstance(conv_data, dict) and "type" in conv_data and conv_data["type"] == "GROUP_DM":
                        group_chat = {
                            "account_id": self.account_id,
                            "twitter_username": self.username,
                            "conversation_id": conv_id,
                            "name": conv_data.get("name", "Unnamed Group"),
                            "create_time": conv_data.get("create_time"),
                            "created_by_user_id": conv_data.get("created_by_user_id"),
                            "trusted": conv_data.get("trusted", False),
                            "participants": [],
                            "scraped_at": datetime.now(timezone.utc),
                            "source": "user_events"
                        }

                        if "participants" in conv_data:
                            participants = []
                            participants_data = conv_data["participants"]

                            if isinstance(participants_data, list):
                                for participant in participants_data:
                                    if isinstance(participant, dict) and "user_id" in participant:
                                        participant_info = {
                                            "user_id": participant.get("user_id"),
                                            "join_time": participant.get("join_time"),
                                            "is_admin": participant.get("is_admin", False),
                                            "join_conversation_event_id": participant.get("join_conversation_event_id"),
                                            "last_read_event_id": participant.get("last_read_event_id")
                                        }
                                        participants.append(participant_info)
                                print(f"[*] Extracted {len(participants)} participants (list format) for group {conv_id}")

                            elif isinstance(participants_data, dict):
                                for range_key, range_participants in participants_data.items():
                                    if isinstance(range_participants, dict):
                                        for idx, participant in range_participants.items():
                                            if isinstance(participant, dict) and "user_id" in participant:
                                                participant_info = {
                                                    "user_id": participant.get("user_id"),
                                                    "join_time": participant.get("join_time"),
                                                    "is_admin": participant.get("is_admin", False),
                                                    "join_conversation_event_id": participant.get(
                                                        "join_conversation_event_id"),
                                                    "last_read_event_id": participant.get("last_read_event_id")
                                                }
                                                participants.append(participant_info)
                                print(f"[*] Extracted {len(participants)} participants (nested format) for group {conv_id}")

                            group_chat["participants"] = participants
                            group_chat["participant_count"] = len(participants)

                        print(f"[*] Extracted {len(group_chat['participants'])} participants for group {conv_id} from user_updates")
                        group_chats.append(group_chat)

        return group_chats
    
    def extract_data(self, data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract structured data from captured API responses.
        
        This method processes the raw captured requests and responses to extract:
        1. Raw API data with metadata
        2. Group chat information
        3. User profile information
        
        It also enriches group chat participants with user data when available.
        
        Args:
            data: The captured request/response data from scrape_messages
            
        Returns:
            Tuple of (raw_data, group_chats, twitter_users)
        """
        raw_data = []
        group_chats = []
        twitter_users = []

        seen_user_ids: Set[str] = set()
        user_id_to_data: Dict[str, Dict[str, Any]] = {}

        for req in data["requests"]:
            if "response_body" not in req or not req["response_body"]:
                continue

            try:
                response_json = json.loads(req["response_body"])

                raw_json = {
                    "account_id": self.account_id,
                    "twitter_username": self.username,
                    "url": req["url"],
                    "timestamp": datetime.now(timezone.utc),
                    "data": response_json
                }
                raw_data.append(raw_json)

                extracted_users = []

                if "inbox_initial_state" in response_json and "users" in response_json["inbox_initial_state"]:
                    users = response_json["inbox_initial_state"]["users"]
                    print(f"[*] Found users in inbox_initial_state with {len(users)} users")

                    for user_id, user_data in users.items():
                        if user_id not in seen_user_ids and isinstance(user_data, dict):
                            user_info = self._extract_user_info(user_id, user_data)
                            extracted_users.append(user_info)
                            seen_user_ids.add(user_id)
                            user_id_to_data[user_id] = user_info

                if "user_events" in response_json and "users" in response_json["user_events"]:
                    users = response_json["user_events"]["users"]
                    print(f"[*] Found users in user_events with {len(users)} users")

                    for user_id, user_data in users.items():
                        if user_id not in seen_user_ids and isinstance(user_data, dict):
                            user_info = self._extract_user_info(user_id, user_data)
                            extracted_users.append(user_info)
                            seen_user_ids.add(user_id)
                            user_id_to_data[user_id] = user_info

                if "users" in response_json:
                    users = response_json["users"]
                    print(f"[*] Found users in root with {len(users)} users")

                    for user_id, user_data in users.items():
                        if user_id not in seen_user_ids and isinstance(user_data, dict):
                            user_info = self._extract_user_info(user_id, user_data)
                            extracted_users.append(user_info)
                            seen_user_ids.add(user_id)
                            user_id_to_data[user_id] = user_info

                print(f"[*] Extracted {len(extracted_users)} users from this response")
                twitter_users.extend(extracted_users)

                request_group_chats = []

                if "inbox_initial_state.json" in req["url"]:
                    request_group_chats = self._extract_group_chats_from_initial_state(response_json)
                elif "user_updates.json" in req["url"]:
                    request_group_chats = self._extract_group_chats_from_user_updates(response_json)

                for group_chat in request_group_chats:
                    for participant in group_chat["participants"]:
                        user_id = participant["user_id"]
                        if user_id in user_id_to_data:
                            participant["user_data"] = {
                                "name": user_id_to_data[user_id].get("name"),
                                "screen_name": user_id_to_data[user_id].get("screen_name"),
                                "followers_count": user_id_to_data[user_id].get("followers_count"),
                                "profile_image_url": user_id_to_data[user_id].get("profile_image_url")
                            }

                group_chats.extend(request_group_chats)

            except Exception as e:
                print(f"[ERROR] Error processing response: {e}")
                import traceback
                traceback.print_exc()

        print(f"[*] Total extracted: {len(raw_data)} raw data, {len(group_chats)} group chats, {len(twitter_users)} users")
        return raw_data, group_chats, twitter_users
    
    def _extract_user_info(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract standardized user profile information from Twitter API data.
        
        This helper method takes raw user data from Twitter's API and transforms
        it into a consistent, structured format for storage or analysis.
        
        Args:
            user_id: The Twitter user ID
            user_data: The raw user data from Twitter's API
            
        Returns:
            Structured user profile information
        """
        return {
            "account_id": self.account_id,
            "twitter_username": self.username,
            "user_id": user_id,
            "id_str": user_data.get("id_str"),
            "name": user_data.get("name"),
            "screen_name": user_data.get("screen_name"),
            "description": user_data.get("description"),
            "followers_count": user_data.get("followers_count"),
            "friends_count": user_data.get("friends_count"),
            "statuses_count": user_data.get("statuses_count"),
            "profile_image_url": user_data.get("profile_image_url_https"),
            "profile_banner_url": user_data.get("profile_banner_url"),
            "created_at": user_data.get("created_at"),
            "protected": user_data.get("protected"),
            "verified": user_data.get("verified"),
            "location": user_data.get("location"),
            "url": user_data.get("url"),
            "blocked_by": user_data.get("blocked_by"),
            "blocking": user_data.get("blocking"),
            "followed_by": user_data.get("followed_by"),
            "following": user_data.get("following"),
            "can_dm": user_data.get("can_dm"),
            "favourites_count": user_data.get("favourites_count"),
            "geo_enabled": user_data.get("geo_enabled"),
            "time_zone": user_data.get("time_zone"),
            "translator_type": user_data.get("translator_type"),
            "scraped_at": datetime.now(timezone.utc)
        }
        
        
if __name__ == "__main__":
    import asyncio
    import argparse
    from playwright.async_api import async_playwright
    from db.connection import get_accounts_collection, get_group_chats_collection
    
    parser = argparse.ArgumentParser(description="Twitter Group Chat Scraper")
    parser.add_argument("-u", "--username", required=True, help="Twitter username to scrape")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    
    args = parser.parse_args()
    
    async def main():
        accounts_collection = get_accounts_collection()
        group_chats_collection = get_group_chats_collection()
        
        account = await accounts_collection.find_one({"username": args.username})
        
        if not account:
            print(f"[ERROR] No account found for username: {args.username}")
            print("[*] Please run login.py first to save account credentials")
            return
            
        if "cookies" not in account:
            print(f"[ERROR] No cookies found for account: {args.username}")
            print("[*] Please run login.py first to save cookies")
            return
        
        async with async_playwright() as playwright:
            browser_options = {
                "headless": args.headless
            }
            
            browser = await playwright.chromium.launch(**browser_options)
            context = await browser.new_context()
            
            if "cookies" in account:
                print(f"[*] Loading cookies for {args.username}")
                await context.add_cookies(account["cookies"])
            
            page = await context.new_page()
            
            scraper = TwitterScraper(
                page=page,
                context=context,
                account_id=str(account["_id"]),
                username=args.username
            )
            
            try:
                print(f"[*] Starting scraping for {args.username}")
                captured_data = await scraper.scrape_messages()
                
                raw_data, group_chats, users = scraper.extract_data(captured_data)
                print(f"[*] Extracted: {len(raw_data)} raw responses, {len(group_chats)} group chats, {len(users)} users")
                
                if group_chats:
                    inserted_count = 0
                    updated_count = 0
                    
                    for group_chat in group_chats:
                        try:
                            result = await group_chats_collection.update_one(
                                {
                                    "twitter_username": args.username,
                                    "conversation_id": group_chat["conversation_id"]
                                },
                                {"$set": group_chat},
                                upsert=True
                            )
                            
                            if result.upserted_id:
                                inserted_count += 1
                            elif result.modified_count > 0:
                                updated_count += 1
                                
                        except Exception as e:
                            print(f"[ERROR] Failed to save group chat {group_chat.get('name', group_chat['conversation_id'])}: {e}")
                    
                    print(f"[*] Database updated: {inserted_count} new group chats, {updated_count} updated")
                else:
                    print("[*] No group chats found to save")
                
                print(f"[*] Scraping completed for {args.username}")
                
            finally:
                await browser.close()
                print("[*] Browser closed")
    
    asyncio.run(main())
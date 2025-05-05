import asyncio
import random
import json
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from db.connection import get_accounts_collection, get_group_chats_collection
from playwright.async_api import async_playwright

DEFAULT_MESSAGE_TEMPLATES = [
    "hit pinned please and add me to gif groups",
    "please don't skip, hit my pinned and recent please i check"
]

class TwitterMessenger:
    """
    Send messages to Twitter group chats using credentials from the database.
    """
    
    def __init__(self, template_file: Optional[str] = None):
        """
        Initialize the Twitter messenger.
        
        Args:
            template_file: Path to a JSON file containing message templates
        """
        self.accounts_collection = get_accounts_collection()
        self.group_chats_collection = get_group_chats_collection()
        
        self.message_templates = DEFAULT_MESSAGE_TEMPLATES
        if template_file and os.path.exists(template_file):
            try:
                with open(template_file, 'r') as f:
                    templates = json.load(f)
                if isinstance(templates, list) and templates:
                    self.message_templates = templates
                    print(f"[*] Loaded {len(templates)} message templates from {template_file}")
            except Exception as e:
                print(f"[ERROR] Failed to load message templates from {template_file}: {e}")
    
    async def send_message_to_groups(self, username: str, group_ids: Optional[List[str]] = None) -> bool:
        """
        Send a message to specific groups or all trusted groups for an account.
        
        Args:
            username: Twitter username to use for sending messages
            group_ids: Optional list of specific group conversation IDs to message
                       If None, will message all trusted groups for the account
        
        Returns:
            True if successful, False otherwise
        """
        browser = None
        context = None
        page = None
        
        try:
            account = await self.accounts_collection.find_one({"username": username})
            if not account:
                print(f"[ERROR] Account not found for username: {username}")
                return False
            
            if "cookies" not in account or not account["cookies"]:
                print(f"[ERROR] No cookies found for account: {username}")
                print("[*] Please run the login script first to save cookies")
                return False
                
            query = {"twitter_username": username, "trusted": True}
            
            if group_ids:
                query["conversation_id"] = {"$in": group_ids}
            
            cursor = self.group_chats_collection.find(query)
            group_chats = await cursor.to_list(length=None)
            
            if not group_chats:
                print(f"[*] No message-eligible groups found for {username}")
                return True
            
            print(f"[*] Found {len(group_chats)} groups to message for {username}")
            
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=False)
                context = await browser.new_context()
                
                await context.add_cookies(account["cookies"])
                
                page = await context.new_page()
                
                await page.goto("https://x.com/messages")
                await page.wait_for_load_state("networkidle", timeout=10000)
                
                if not page.url.startswith("https://x.com/messages"):
                    print(f"[ERROR] Cookie login failed for {username}, please run login script again")
                    return False
                
                messages_sent = 0
                
                for group in group_chats:
                    try:
                        conversation_url = f"https://x.com/messages/{group['conversation_id']}"
                        await page.goto(conversation_url)
                        await asyncio.sleep(2)
                        
                        if page.url.startswith(conversation_url):
                            group_templates = group.get("custom_messages", [])
                            message_pool = group_templates or self.message_templates
                            message = random.choice(message_pool)
                            
                            input_selector = '[data-testid="dmComposerTextInput"]'
                            try:
                                await page.wait_for_selector(input_selector, timeout=5000)
                                await page.fill(input_selector, message)
                                await asyncio.sleep(1)
                                
                                send_button_selector = '[data-testid="dmComposerSendButton"]'
                                await page.wait_for_selector(send_button_selector, timeout=5000)
                                await page.click(send_button_selector)
                                await asyncio.sleep(2)
                                
                                print(f"[*] Sent message to group {group.get('name', group['conversation_id'])}")
                                messages_sent += 1
                                
                                delay = random.randint(5, 15)
                                print(f"[*] Waiting {delay} seconds before next message...")
                                await asyncio.sleep(delay)
                            except Exception as e:
                                print(f"[ERROR] Error sending message to conversation {group['conversation_id']}: {e}")
                        else:
                            print(f"[ERROR] Failed to navigate to conversation {group['conversation_id']}")
                    except Exception as e:
                        print(f"[ERROR] Error messaging group {group.get('name', group['conversation_id'])}: {e}")
                
                print(f"[*] Successfully sent {messages_sent} messages for account {username}")
                return True
            
        except Exception as e:
            print(f"[ERROR] Error in messaging process for {username}: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            print("[*] Browser resources cleaned up")


async def send_messages(username: str, group_ids: Optional[List[str]] = None, template_file: Optional[str] = None):
    """
    Utility function to send messages to Twitter group chats.
    
    Args:
        username: Twitter username to use for sending messages
        group_ids: Optional list of specific group conversation IDs to message
        template_file: Optional path to a JSON file with message templates
    """
    messenger = TwitterMessenger(template_file)
    success = await messenger.send_message_to_groups(username, group_ids)
    if success:
        print(f"[*] Messaging completed successfully for {username}")
    else:
        print(f"[*] Messaging failed for {username}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Send messages to Twitter group chats")
    parser.add_argument("-u", "--username", required=True, help="Twitter username to use")
    parser.add_argument("-g", "--groups", nargs="*", help="Specific group IDs to message (optional)")
    parser.add_argument("-t", "--templates", help="Path to JSON file with message templates (optional)")
    
    args = parser.parse_args()
    
    asyncio.run(send_messages(args.username, args.groups, args.templates))
# Twitter Engagement Group Automation

A Python-based tool for automating Twitter login and scraping group chat data using Playwright.

## Overview

This project provides a set of utilities for Twitter automation, including:
- Automated login with support for various authentication scenarios
- Group chat data extraction
- User profile information collection
- MongoDB integration for data storage

## Features

- **Headless Browser Automation**: Uses Playwright for reliable browser automation
- **Authentication Handling**: Manages login, 2FA, and verification challenges
- **API Response Capture**: Intercepts network requests to extract group chat data
- **Data Persistence**: Stores authentication tokens, cookies, and scraped data in MongoDB
- **Participant Tracking**: Maps users to group chats with rich profile information

## Requirements

- Python 3.7+
- MongoDB
- Playwright
- AsyncIO

## Installation

1. Clone the repository
```bash
git clone https://github.com/yourusername/tw1.git
cd tw1
```

2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

3. Make sure your .env file is in the repo and contains the MONGO_URI pointed to your MongoDB cluster (local or cloud)

```bash
MONGO_URI="mongodb://127.0.0.1:27017/"
```

## Component Scripts

### Login Tool (`login.py`)

The login tool authenticates with Twitter and saves credentials for future use. (run this first to save cookies & auth)

```bash
python login.py -u your_username
```

**Parameters:**
- `-u, --username`: Twitter username
- `-p, --password`: Twitter password (optional, will prompt if not provided)
- `--proxy`: Proxy in format protocol://user:pass@host:port
- `--headless`: Run browser in headless mode (not recommended)

### Group Chat Scraper (`scraper.py`)

Extracts group chat data and user information from Twitter's messaging endpoints.
You'll need to run this multiple times, since the Twitter API provides only so much of the groupchats, and it also will contain groupchats which you've been invited to but haven't accepted. (it doesn't send a message to the "untrusted" groups, they need to be "trusted" first)

```bash
python scraper.py -u your_username
```

**Parameters:**
- `-u, --username`: Twitter username to use for scraping
- `--headless`: Run browser in headless mode (not recommended)

### Message Sender (`messaging.py`)

Automatically sends messages to trusted Twitter group chats.

```bash
python messaging.py -u your_username -t templates.json
```

Either setup a template or update the list in line 13.

**Parameters:**
- `-u, --username`: Twitter username to use for sending messages
- `-g, --groups`: Specific group IDs to message (optional)
- `-t, --templates`: Path to JSON file with message templates

## Data Structure

### Group Chat Data
- Conversation ID
- Group name
- Creation time and creator
- Trust status
- Participant information
- Timestamps for data collection

### User Profile Data
- User ID and screen name
- Profile information (name, description, image URLs)
- Account statistics (followers, following, tweet count)
- Platform engagement data

## Project Structure

```
tw1/
├── login.py             # Twitter authentication 
├── scraper.py           # Group chat extraction
├── messaging.py         # Automated messaging
├── db/
│   └── connection.py    # MongoDB connection utilities
├── utils/
│   └── proxyparser.py   # Proxy configuration parser
└── templates/
    └── messages.json    # Sample message templates
```

## Usage Examples

### Complete Workflow

1. First-time login with credentials:
```bash
python login.py -u your_username
```

2. Scrape group chats:
```bash
python scraper.py -u your_username
```

3. Send messages to all trusted groups:
```bash
python messaging.py -u your_username
```

### Custom Message Templates

Create a JSON file with message templates:
```json
[
  "hit pinned please and add me to gif groups",
  "please don't skip, hit my pinned and recent please i check",
  "check out my latest content and hit pinned/recent"
]
```

Then use it with the messaging tool:
```bash
python messaging.py -u your_username -t your_templates.json
```

## License

MIT License

## Disclaimer

This tool is for educational purposes only. Use responsibly and in accordance with Twitter's Terms of Service.

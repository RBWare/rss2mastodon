import os
import json
import feedparser
import requests
from io import BytesIO
from mastodon import Mastodon
import hashlib
import time
import re

def strip_html(html):
    """Remove HTML tags from a string."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html)

def get_entry_id(entry):
    raw = entry.get("id") or entry.get("guid") or entry.get("link") or (entry.title + entry.link)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

# === CONFIG FILE & ID STORAGE ===
CONFIG_FILE = "feeds_config.json"
ID_STORE_DIR = "posted_ids"
os.makedirs(ID_STORE_DIR, exist_ok=True)

# === LOAD FEED/ACCOUNT CONFIGURATION ===
with open(CONFIG_FILE, "r") as f:
    feed_configs = json.load(f)

# === PROCESS EACH FEED/ACCOUNT PAIR ===
for config in feed_configs:
    name = config["name"]
    feed_url = config["feed_url"]
    instance = config["mastodon_instance"]
    token = config["access_token"]

    # === ID TRACKING FILE ===
    id_store_path = os.path.join(ID_STORE_DIR, f"{name}.json")
    first_run = not os.path.exists(id_store_path)

    if not first_run:
        with open(id_store_path, "r") as f:
            posted_ids = set(json.load(f))
    else:
        posted_ids = set()

    # === PARSE RSS FEED ===
    try:
        print(f"🌐 Fetching feed: {feed_url}")
        response = requests.get(feed_url, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        entries = feed.entries
    except Exception as e:
        print(f"⚠️ Failed to fetch or parse feed {name}: {e}")
        continue  # skip to next feed

    print(f"\n📡 Processing: {name} ({len(entries)} entries)")

    if not entries:
        continue

    # === FIRST RUN: ONLY POST LATEST ITEM ===
    if first_run:
        print("🆕 First run: posting only the most recent entry.")
        entries = [entries[0]]

    new_ids = set()
    
    # === INIT MASTODON CLIENT ===
    mastodon = Mastodon(
        access_token=token,
        api_base_url=instance,
        ratelimit_method='wait'
    )
    print("Starting to process...")

    for entry in entries:
        entry_id = get_entry_id(entry)
        if not entry_id or entry_id in posted_ids:
            continue

        MAX_CHARS = 500

        
        title = strip_html(entry.get("title", "").strip())
        summary = entry.get("summary") or entry.get("description")
        summary = strip_html(summary.strip()) if summary else ""
        link = entry.get("link", "").strip()

        # Reserve room for title and link
        static_part = f"{title}\n\n"
        link_part = f"\n{link}"
        available_chars = MAX_CHARS - len(static_part) - len(link_part)

        # Truncate summary if needed
        if summary:
            if len(summary) > available_chars:
                summary = summary[:available_chars].rsplit(" ", 1)[0] + "…"
            text = f"{static_part}{summary}{link_part}"
        else:
            text = f"{title}{link_part}"

        status = text.strip()
        media_ids = []

        # === TRY TO EXTRACT MEDIA ===
        media_url = None
        if 'media_content' in entry and entry.media_content:
            media_url = entry.media_content[0].get('url')
        elif 'enclosures' in entry and entry.enclosures:
            media_url = entry.enclosures[0].get('href')

        # === UPLOAD MEDIA ===
        if media_url:
            try:
                response = requests.get(media_url, timeout=10)
                response.raise_for_status()
                mime_type = response.headers.get("Content-Type", "image/jpeg")
                media = BytesIO(response.content)
                media_response = mastodon.media_post(media, mime_type=mime_type)
                media_ids.append(media_response['id'])
                print(f"🖼️  Attached image: {media_url}")
            except Exception as e:
                print(f"⚠️ Media upload failed: {e}")

        # === POST TO MASTODON ===
        try:
            remaining = mastodon.ratelimit_remaining
            if remaining is not None and remaining < 5:
                reset_time = mastodon.ratelimit_reset
                print(f"⛔ Rate limit near exhaustion ({remaining} remaining). Skipping post.")
                print(f"⏳ Limit resets at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reset_time))}")
                continue

            print("Posting to Mastodon...")
            mastodon.status_post(status, media_ids=media_ids)
            print(f"✅ Posted: {entry.title}")

            posted_ids.add(entry_id)  # ✅ Immediately mark as posted

            # ✅ Save updated ID list after this post
            with open(id_store_path, "w") as f:
                json.dump(list(posted_ids), f)
                print(f"💾 Saved ID for: {entry.title}")
            time.sleep(15)
        except Exception as e:
            print(f"❌ Failed to post '{entry.title}': {e}")

    # # === SAVE UPDATED ID LIST ===
    # all_ids = posted_ids.union(new_ids)
    # print(f"📝 New IDs to save: {len(new_ids)}")
    # print(f"🧮 Total known IDs: {len(all_ids)}")
    
    # print(f"💾 Saving IDs to: {id_store_path}")
    # try:
    #     with open(id_store_path, "w") as f:
    #         json.dump(list(all_ids), f)
    #     print("✅ ID list saved successfully.")
    # except Exception as e:
    #     print(f"❌ Failed to save ID list: {e}")


import os
import time
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from models import get_db
from telethon_config import api_id, api_hash, session_name, channel

def get_media_files(folder_path):
    if not os.path.exists(folder_path):
        return []
    files = []
    for fname in sorted(os.listdir(folder_path)):
        path = os.path.join(folder_path, fname)
        if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            files.append(('photo', path))
        elif fname.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv')):
            files.append(('video', path))
        # Можно добавить другие типы
    return files

async def send_post(client, post):
    media_files = get_media_files(post['folder_path'])
    text = post['text']
    if media_files:
        media_to_send = [path for mtype, path in media_files[:10]]
        await client.send_file(
            entity=int(channel) if isinstance(channel, int) or channel.lstrip('-').isdigit() else channel,
            file=media_to_send,
            caption=text,
            parse_mode='html'
        )
    else:
        await client.send_message(
            entity=int(channel) if isinstance(channel, int) or channel.lstrip('-').isdigit() else channel,
            message=text,
            parse_mode='html'
        )

def main_loop():
    client = TelegramClient(session_name, api_id, api_hash)
    client.start()
    print('Telethon client started. Waiting for scheduled posts...')
    while True:
        now = datetime.now()
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM posts WHERE status='pending' AND scheduled_at IS NOT NULL AND scheduled_at<=? ORDER BY scheduled_at ASC",
            (now.strftime("%Y-%m-%d %H:%M:%S"),)
        )
        posts = c.fetchall()
        for post in posts:
            try:
                print(f"Sending post id={post['id']} scheduled_at={post['scheduled_at']}")
                client.loop.run_until_complete(send_post(client, post))
                c.execute("UPDATE posts SET status='sent', sent_at=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), post['id']))
                conn.commit()
            except FloodWaitError as e:
                print(f"FloodWaitError: sleeping for {e.seconds} seconds")
                time.sleep(e.seconds)
            except Exception as e:
                print(f"Error sending post id={post['id']}: {e}")
        conn.close()
        time.sleep(60)

if __name__ == '__main__':
    main_loop()

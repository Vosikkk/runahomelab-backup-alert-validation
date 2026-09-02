import os, httpx
from dotenv import load_dotenv

load_dotenv(override=True)

bot = os.environ['TELEGRAM_BOT_TOKEN']; base = os.environ['PUBLIC_BASE_URL'].rstrip('/'); secret = os.environ['TELEGRAM_WEBHOOK_SECRET']
r = httpx.post(f'https://api.telegram.org/bot{bot}/setWebhook', json={'url':f'{base}/telegram/webhook','secret_token':secret,'drop_pending_updates':True}, timeout=15)
r.raise_for_status(); print(r.json())



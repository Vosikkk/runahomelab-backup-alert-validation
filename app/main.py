import os, secrets, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv('DB_PATH', BASE_DIR / 'data.sqlite3'))
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '')
WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')

app = FastAPI(title='runahomelab backup alert validation')
app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')

def now_iso(): return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        yield conn; conn.commit()
    finally: conn.close()

def init_db():
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS validation_sessions (
            token TEXT PRIMARY KEY,
            telegram_chat_id TEXT,
            created_at TEXT NOT NULL,
            connected_at TEXT,
            test_completed_at TEXT
        )''')

@app.on_event('startup')
def startup(): init_db()

class SessionResponse(BaseModel):
    token: str
    telegram_url: str

@app.get('/', response_class=HTMLResponse)
def index():
    return (BASE_DIR / 'static' / 'index.html').read_text(encoding='utf-8')

@app.post('/api/session', response_model=SessionResponse)
def create_session():
    if not BOT_USERNAME: raise HTTPException(503, 'TELEGRAM_BOT_USERNAME is not configured')
    token = secrets.token_urlsafe(18)
    with db() as conn:
        conn.execute('INSERT INTO validation_sessions(token,created_at) VALUES (?,?)',(token,now_iso()))
    return SessionResponse(token=token, telegram_url=f'https://t.me/{BOT_USERNAME}?start={quote(token)}')

@app.get('/api/session/{token}')
def session_status(token: str):
    with db() as conn:
        row = conn.execute('SELECT connected_at,test_completed_at FROM validation_sessions WHERE token=?',(token,)).fetchone()
    if not row: raise HTTPException(404,'Unknown session')
    return {'connected': row['connected_at'] is not None, 'test_completed': row['test_completed_at'] is not None}

async def send_telegram(chat_id: str, text: str):
    if not BOT_TOKEN: raise RuntimeError('TELEGRAM_BOT_TOKEN is not configured')
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', json={'chat_id':chat_id,'text':text,'disable_web_page_preview':True})
        r.raise_for_status()

@app.post('/telegram/webhook')
async def telegram_webhook(request: Request):
    received_secret = request.headers.get(
        'X-Telegram-Bot-Api-Secret-Token'
    )

    if WEBHOOK_SECRET and received_secret != WEBHOOK_SECRET:
        raise HTTPException(403, 'Invalid webhook secret')

    update = await request.json()

    message = update.get('message') or {}
    text = (message.get('text') or '').strip()
    chat_id = (message.get('chat') or {}).get('id')

    if not chat_id or not text.startswith('/start'):
        return {'ok': True}

    parts = text.split(maxsplit=1)

    if len(parts) != 2:
        await send_telegram(
            str(chat_id),
            'Open the Connect Telegram button on runahomelab.com first.'
        )
        return {'ok': True}

    token = parts[1].strip()

    with db() as conn:
        row = conn.execute(
            '''
            SELECT token
            FROM validation_sessions
            WHERE token=?
            ''',
            (token,)
        ).fetchone()

        if not row:
            await send_telegram(
                str(chat_id),
                'This test link is invalid or expired. Start again on runahomelab.com.'
            )
            return {'ok': True}

        ts = now_iso()

        conn.execute(
            '''
            UPDATE validation_sessions
            SET telegram_chat_id=?,
                connected_at=?
            WHERE token=?
            ''',
            (str(chat_id), ts, token)
        )

    await send_telegram(
        str(chat_id),
        '✅ Backup alerts connected\n\n'
        'This is what a runahomelab alert would look like:\n\n'
        '❌ PBS backup FAILED · node pve1 · 02:14\n\n'
        'No dashboard. Just tell you when the backup breaks.'
    )

    with db() as conn:
        conn.execute(
            '''
            UPDATE validation_sessions
            SET test_completed_at=?
            WHERE token=?
            ''',
            (now_iso(), token)
        )

    return {'ok': True}


class ProxmoxWebhookPayload(BaseModel):
    title: str | None = None
    message: str | None = None
    severity: str | None = None
    type: str | None = None
    hostname: str | None = None


@app.post('/i/{token}')
async def proxmox_receiver(
    token: str,
    payload: ProxmoxWebhookPayload = Body(...)
):
    with db() as conn:
        row = conn.execute(
            '''
            SELECT telegram_chat_id
            FROM validation_sessions
            WHERE token=?
            ''',
            (token,)
        ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail='Unknown receiver'
        )

    chat_id = row['telegram_chat_id']

    if not chat_id:
        raise HTTPException(
            status_code=409,
            detail='Telegram is not connected'
        )

    severity = (payload.severity or '').lower()
    event_type = (payload.type or '').lower()
    title = (payload.title or '').lower()
    message = (payload.message or '').lower()

    is_backup = (
        'backup' in event_type
        or 'vzdump' in event_type
        or 'backup' in title
        or 'backup' in message
    )

    is_failure = (
        severity in {'error', 'critical'}
        or 'fail' in title
        or 'fail' in message
    )

    if not is_backup or not is_failure:
        return {
            'ok': True,
            'ignored': True
        }

    node = payload.hostname or 'unknown'

    await send_telegram(
        str(chat_id),
        (
            '❌ PBS backup FAILED\n'
            f'node {node}\n'
            f'{payload.message or payload.title or "Backup failed"}'
        )
    )

    return {
        'ok': True,
        'sent': True
    }



@app.get('/health')
def health(): return {'ok':True}

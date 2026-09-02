import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data.sqlite3"))

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def send_message(
    client: httpx.AsyncClient,
    chat_id: str,
    text: str,
):
    response = await client.post(
        f"{API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )

    response.raise_for_status()


async def handle_update(
    client: httpx.AsyncClient,
    update: dict,
):
    message = update.get("message") or {}

    text = (message.get("text") or "").strip()

    chat_id = (
        message.get("chat") or {}
    ).get("id")

    print("UPDATE:", update)
    print("TEXT:", repr(text))
    print("CHAT:", chat_id)

    if not chat_id:
        return

    if not text.startswith("/start"):
        return

    parts = text.split(maxsplit=1)

    if len(parts) != 2:
        await send_message(
            client,
            str(chat_id),
            "Open the Connect Telegram button on runahomelab.com first.",
        )
        return

    token = parts[1].strip()

    print("TOKEN:", token)

    conn = connect_db()

    try:
        row = conn.execute(
            """
            SELECT token
            FROM validation_sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

        if not row:
            await send_message(
                client,
                str(chat_id),
                "This test link is invalid or expired. "
                "Start again on runahomelab.com.",
            )
            return

        timestamp = now_iso()

        conn.execute(
            """
            UPDATE validation_sessions
            SET telegram_chat_id = ?,
                connected_at = ?,
                test_completed_at = ?
            WHERE token = ?
            """,
            (
                str(chat_id),
                timestamp,
                timestamp,
                token,
            ),
        )

        conn.commit()

    finally:
        conn.close()

    await send_message(
        client,
        str(chat_id),
        (
            "✅ Backup alerts connected\n\n"
            "This is what a runahomelab alert would look like:\n\n"
            "❌ PBS backup FAILED · node pve1 · 02:14\n\n"
            "No dashboard. Just tell you when the backup breaks."
        ),
    )

    print("✅ TEST ALERT SENT")


async def main():
    offset = 0

    print("🤖 Telegram polling started")

    async with httpx.AsyncClient(timeout=35) as client:

        # Webhook and getUpdates cannot be used simultaneously.
        response = await client.post(
            f"{API}/deleteWebhook",
            json={
                "drop_pending_updates": True,
            },
        )

        response.raise_for_status()

        print("✅ Webhook disabled for local polling")

        while True:
            try:
                response = await client.get(
                    f"{API}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                )

                response.raise_for_status()

                updates = response.json()["result"]

                for update in updates:
                    offset = update["update_id"] + 1

                    await handle_update(
                        client,
                        update,
                    )

            except Exception as error:
                print("❌ Polling error:", error)

                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
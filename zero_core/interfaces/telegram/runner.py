"""Live Telegram Bot Long-Polling Daemon for ZERO (Priority 3).

Connects to the official Telegram Bot API via standard HTTPS requests without
requiring external third-party bot libraries.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from zero_core.config import load_env

load_env()

from zero_core.interfaces.telegram.bot import TelegramBotHandler


from zero_core.scheduler import DEFAULT_BRIEFING_SCHEDULER, BriefingScheduler


class TelegramBotRunner:
    """Long-polling daemon dispatching Telegram events to TelegramBotHandler."""

    def __init__(
        self,
        token: Optional[str] = None,
        allowed_user_ids: Optional[List[str]] = None,
        handler: Optional[TelegramBotHandler] = None,
        scheduler: Optional[BriefingScheduler] = None,
    ):
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.handler = handler or TelegramBotHandler()
        self.scheduler = scheduler or DEFAULT_BRIEFING_SCHEDULER

        raw_ids = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        self.allowed_user_ids = allowed_user_ids or ([i.strip() for i in raw_ids.split(",") if i.strip()] if raw_ids else [])
        self.known_chat_ids: set[int | str] = set()

        # Seed known chat IDs from environment if configured
        target_chat = os.environ.get("TELEGRAM_BRIEFING_CHAT_ID", "")
        if target_chat.strip():
            self.known_chat_ids.add(target_chat.strip())

        self.last_update_id = 0
        self._running = False

    def is_configured(self) -> bool:
        return bool(self.token.strip())

    def _api_call(self, method: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None

        url = f"https://api.telegram.org/bot{self.token}/{method}"
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def send_message(self, chat_id: int | str, text: str) -> bool:
        """Sends a text message back to a chat, with automatic markdown parse fallback."""
        res = self._api_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
        )
        if res and res.get("ok"):
            return True

        # Fallback to plain text if Markdown parsing fails due to unescaped symbols
        res = self._api_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
            },
        )
        return bool(res and res.get("ok"))

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Acknowledges a button callback in Telegram."""
        res = self._api_call(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text,
            },
        )
        return bool(res and res.get("ok"))

    def check_scheduled_broadcasts(self):
        """Checks scheduler and delivers automated morning/evening briefings to known users."""
        due_jobs = self.scheduler.check_and_run_due_jobs()
        for job_name, content in due_jobs:
            recipients = list(self.known_chat_ids) or self.allowed_user_ids
            for recipient in recipients:
                header = "🌅 *Automated Morning Briefing Push*\n\n" if "morning" in job_name else "🌇 *Automated Evening Briefing Push*\n\n"
                self.send_message(recipient, f"{header}{content}")

    def poll_once(self, timeout: int = 10) -> int:
        """Polls for new updates and dispatches them. Returns count of updates processed."""
        # Check scheduled cron jobs
        self.check_scheduled_broadcasts()

        res = self._api_call(
            "getUpdates",
            {
                "offset": self.last_update_id + 1,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
        )

        if not res or not res.get("ok"):
            return 0

        updates = res.get("result", [])
        for upd in updates:
            upd_id = upd.get("update_id", 0)
            if upd_id > self.last_update_id:
                self.last_update_id = upd_id

            # Process Message
            if "message" in upd:
                msg = upd["message"]
                chat_id = msg.get("chat", {}).get("id")
                from_id = str(msg.get("from", {}).get("id", ""))
                text = msg.get("text", "")

                if chat_id:
                    self.known_chat_ids.add(chat_id)

                if self.allowed_user_ids and from_id not in self.allowed_user_ids:
                    self.send_message(chat_id, "⛔ *Unauthorized*: Your Telegram User ID is not on the ZERO access whitelist.")
                    continue

                if text:
                    reply = self.handler.handle_message(text=text, user_id=from_id)
                    self.send_message(chat_id, reply)

            # Process Callback Query (Buttons)
            elif "callback_query" in upd:
                cb = upd["callback_query"]
                cb_id = cb.get("id")
                from_id = str(cb.get("from", {}).get("id", ""))
                chat_id = cb.get("message", {}).get("chat", {}).get("id")
                data = cb.get("data", "")

                if chat_id:
                    self.known_chat_ids.add(chat_id)

                if self.allowed_user_ids and from_id not in self.allowed_user_ids:
                    self.answer_callback_query(cb_id, "Unauthorized")
                    continue

                res_text = self.handler.handle_callback(callback_data=data, approver=from_id)
                self.answer_callback_query(cb_id, res_text)
                if chat_id:
                    self.send_message(chat_id, res_text)

        return len(updates)

    def run_forever(self):
        """Runs the long-polling loop indefinitely."""
        if not self.is_configured():
            print("[!] TelegramBotRunner: TELEGRAM_BOT_TOKEN is not set. Set it in .env to start the bot.")
            return

        print("[*] Starting ZERO Telegram Bot Runner daemon (with Automated Briefing Scheduler)...")
        self._running = True
        while self._running:
            try:
                self.poll_once(timeout=15)
            except KeyboardInterrupt:
                print("\n[!] Stopping Telegram Bot Runner.")
                break
            except Exception as e:
                time.sleep(2)


# Global singleton instance
DEFAULT_TELEGRAM_RUNNER = TelegramBotRunner()


if __name__ == "__main__":
    DEFAULT_TELEGRAM_RUNNER.run_forever()

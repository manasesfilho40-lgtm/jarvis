import asyncio
import email
import imaplib
import logging
import smtplib
import time
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_email")


class EmailPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="email",
                version="1.0.0",
                description="Email integration - read/send via IMAP/SMTP",
            )
        super().__init__(manifest)
        self._imap_server: str = ""
        self._imap_port: int = 993
        self._smtp_server: str = ""
        self._smtp_port: int = 587
        self._email: str = ""
        self._password: str = ""
        self._check_interval: int = 300
        self._last_check: float = 0

    async def on_load(self):
        self._email = self.config.get("email_address", "")
        self._password = self.config.get("email_password", "")
        self._imap_server = self.config.get("imap_server", "imap.gmail.com")
        self._imap_port = int(self.config.get("imap_port", 993))
        self._smtp_server = self.config.get("smtp_server", "smtp.gmail.com")
        self._smtp_port = int(self.config.get("smtp_port", 587))
        self._check_interval = int(self.config.get("email_check_interval", 300))
        if self._email and self._password:
            logger.info(f"Email plugin loaded - {self._email}")
        else:
            logger.warning("Email plugin loaded - no credentials configured")

    async def on_unload(self):
        logger.info("Email plugin unloaded")

    def _connect_imap(self):
        if not self._email or not self._password:
            return None
        try:
            mail = imaplib.IMAP4_SSL(self._imap_server, self._imap_port)
            mail.login(self._email, self._password)
            return mail
        except Exception as e:
            logger.error(f"Failed to connect IMAP: {e}")
            return None

    def _decode_mime_header(self, header_value: str) -> str:
        if not header_value:
            return ""
        decoded_parts = decode_header(header_value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(str(part))
        return " ".join(result)

    def _get_email_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            return payload.decode("utf-8", errors="replace")
                    except Exception:
                        continue
            return "[No text body]"
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
            except Exception:
                pass
            return "[No body]"

    async def read_inbox(self, limit: int = 10, folder: str = "INBOX") -> list[dict]:
        mail = self._connect_imap()
        if not mail:
            return []
        try:
            mail.select(folder)
            status, message_ids = mail.search(None, "ALL")
            if status != "OK":
                return []
            ids = message_ids[0].split() if message_ids[0] else []
            ids = ids[-limit:]
            messages = []
            for mid in reversed(ids):
                status, data = mail.fetch(mid, "(RFC822)")
                if status != "OK":
                    continue
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        messages.append({
                            "id": mid.decode(),
                            "from": self._decode_mime_header(msg.get("From", "")),
                            "subject": self._decode_mime_header(msg.get("Subject", "")),
                            "date": str(msg.get("Date", "")),
                            "body_preview": self._get_email_body(msg)[:200],
                        })
            return messages
        except Exception as e:
            logger.error(f"Failed to read inbox: {e}")
            return []
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self._email or not self._password:
            return False
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self._email
            msg["To"] = to

            with smtplib.SMTP(self._smtp_server, self._smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self._email, self._password)
                server.send_message(msg)
            logger.info(f"Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def search_emails(self, query: str, limit: int = 10) -> list[dict]:
        mail = self._connect_imap()
        if not mail:
            return []
        try:
            mail.select("INBOX")
            status, message_ids = mail.search(None, f'BODY "{query}"')
            if status != "OK":
                status, message_ids = mail.search(None, f'SUBJECT "{query}"')
                if status != "OK":
                    return []
            ids = message_ids[0].split() if message_ids[0] else []
            ids = ids[-limit:]
            messages = []
            for mid in reversed(ids):
                status, data = mail.fetch(mid, "(RFC822)")
                if status != "OK":
                    continue
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        messages.append({
                            "id": mid.decode(),
                            "from": self._decode_mime_header(msg.get("From", "")),
                            "subject": self._decode_mime_header(msg.get("Subject", "")),
                            "date": str(msg.get("Date", "")),
                            "body_preview": self._get_email_body(msg)[:200],
                        })
            return messages
        except Exception as e:
            logger.error(f"Failed to search emails: {e}")
            return []
        finally:
            try:
                mail.logout()
            except Exception:
                pass


manifest = PluginManifest(
    name="email",
    version="1.0.0",
    description="Email integration - read/send via IMAP/SMTP",
)

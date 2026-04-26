"""
core/bot_registry.py — Bot Token Kayıt & Otomatik Kurulum Sistemi

Her bot için:
  1. Token DB'ye şifreli kaydedilir
  2. Telegram getMe() ile bot bilgileri çekilir
  3. Komut menüleri dile göre kurulur
  4. Webhook ayarlanır (HTTPS URL varsa)
  5. Mini App butonu eklenir (WEB_APP_URL varsa)
  6. Bağlı gruplar Telegram API'den listelenir

Token güvenliği:
  - Fernet simetrik şifreleme (AES-128-CBC + HMAC)
  - Şifreleme anahtarı .env'deki TOKEN_ENCRYPTION_KEY
  - DB'de şifreli saklanır, hiçbir zaman plain-text log'a yazılmaz
"""
from __future__ import annotations
import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")


# ═══════════════════════════════════════════
# Token Şifreleme
# ═══════════════════════════════════════════
class TokenCipher:
    def __init__(self, key: str = ""):
        if key:
            try:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
                self._enabled = True
            except Exception:
                log.warning("Geçersiz TOKEN_ENCRYPTION_KEY — şifreleme devre dışı")
                self._fernet = None
                self._enabled = False
        else:
            self._fernet = None
            self._enabled = False

    def encrypt(self, token: str) -> str:
        if not self._enabled or not self._fernet:
            return token  # Şifreleme kapalıysa düz sakla
        return self._fernet.encrypt(token.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        if not self._enabled or not self._fernet:
            return encrypted
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken:
            log.error("Token çözümlenemedi — anahtar değişmiş olabilir")
            return ""

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()


# ═══════════════════════════════════════════
# Bot Bilgi Nesnesi
# ═══════════════════════════════════════════
@dataclass
class BotInfo:
    bot_id: int
    username: str
    first_name: str
    can_join_groups: bool
    can_read_all_group_messages: bool
    supports_inline_queries: bool
    token_env_key: str       # groups.yaml'daki env değişkeni adı
    group_id: str            # groups.yaml'daki grup ID'si
    status: str              # "online" | "offline" | "error" | "unconfigured"
    error_msg: str = ""
    webhook_url: str = ""
    last_checked: str = ""


# ═══════════════════════════════════════════
# Telegram API İstemcisi
# ═══════════════════════════════════════════
class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self._base = f"https://api.telegram.org/bot{token}"

    async def call(self, method: str, **params) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{self._base}/{method}", json=params)
            return r.json()

    async def get_me(self) -> dict | None:
        r = await self.call("getMe")
        return r.get("result") if r.get("ok") else None

    async def get_updates(self, limit: int = 1) -> list[dict]:
        """Son güncellemeleri al — bot'un üye olduğu grupları bulmak için."""
        r = await self.call("getUpdates", limit=limit, timeout=1)
        return r.get("result", []) if r.get("ok") else []

    async def set_webhook(self, url: str, secret: str = "") -> bool:
        params = {"url": url, "max_connections": 100, "drop_pending_updates": False}
        if secret:
            params["secret_token"] = secret
        r = await self.call("setWebhook", **params)
        return r.get("ok", False)

    async def delete_webhook(self) -> bool:
        r = await self.call("deleteWebhook")
        return r.get("ok", False)

    async def get_webhook_info(self) -> dict:
        r = await self.call("getWebhookInfo")
        return r.get("result", {})

    async def set_my_commands(self, commands: list[dict], lang_code: str = "") -> bool:
        params = {"commands": commands}
        if lang_code:
            params["language_code"] = lang_code
        r = await self.call("setMyCommands", **params)
        return r.get("ok", False)

    async def set_my_description(self, description: str, lang_code: str = "") -> bool:
        params = {"description": description[:512]}
        if lang_code:
            params["language_code"] = lang_code
        r = await self.call("setMyDescription", **params)
        return r.get("ok", False)

    async def set_my_short_description(self, desc: str, lang_code: str = "") -> bool:
        params = {"short_description": desc[:120]}
        if lang_code:
            params["language_code"] = lang_code
        r = await self.call("setMyShortDescription", **params)
        return r.get("ok", False)

    async def set_chat_menu_button(self, chat_id: int | None, url: str, text: str) -> bool:
        params = {
            "menu_button": {
                "type": "web_app",
                "text": text,
                "web_app": {"url": url}
            }
        }
        if chat_id:
            params["chat_id"] = chat_id
        r = await self.call("setChatMenuButton", **params)
        return r.get("ok", False)

    async def set_default_menu_button(self) -> bool:
        r = await self.call("setChatMenuButton",
                            menu_button={"type": "default"})
        return r.get("ok", False)

    async def get_chat(self, chat_id: int) -> dict | None:
        r = await self.call("getChat", chat_id=chat_id)
        return r.get("result") if r.get("ok") else None

    async def get_chat_member(self, chat_id: int, user_id: int) -> dict | None:
        r = await self.call("getChatMember", chat_id=chat_id, user_id=user_id)
        return r.get("result") if r.get("ok") else None


# ═══════════════════════════════════════════
# Bot Kayıt Sistemi
# ═══════════════════════════════════════════
class BotRegistry:
    """
    Tüm botların token'larını, durumlarını ve
    Telegram kurulum adımlarını yönetir.
    """

    def __init__(self):
        self.cipher = TokenCipher(ENCRYPTION_KEY)
        # In-memory cache: {group_id: BotInfo}
        self._cache: dict[str, BotInfo] = {}

    # ── Token CRUD ────────────────────────────
    async def register_bot(
        self,
        group_id: str,
        token_env_key: str,
        raw_token: str,
    ) -> BotInfo:
        """
        Yeni bot kaydeder veya günceller.
        1. Token doğrulanır (getMe)
        2. DB'ye şifreli yazılır
        3. .env güncellenir
        4. BotInfo döner
        """
        import core.db as db

        # Token doğrula
        client = TelegramClient(raw_token)
        me = await client.get_me()
        if not me:
            info = BotInfo(
                bot_id=0, username="", first_name="",
                can_join_groups=False, can_read_all_group_messages=False,
                supports_inline_queries=False,
                token_env_key=token_env_key, group_id=group_id,
                status="error", error_msg="Geçersiz token veya Telegram'a ulaşılamıyor."
            )
            return info

        # Token şifrele
        encrypted = self.cipher.encrypt(raw_token)

        # DB'ye kaydet
        await db.bot_token_kaydet(group_id, token_env_key, encrypted, me["id"])

        # .env'i güncelle (yedek)
        self._update_env_file(token_env_key, raw_token)

        info = BotInfo(
            bot_id=me["id"],
            username=me.get("username", ""),
            first_name=me.get("first_name", ""),
            can_join_groups=me.get("can_join_groups", True),
            can_read_all_group_messages=me.get("can_read_all_group_messages", False),
            supports_inline_queries=me.get("supports_inline_queries", False),
            token_env_key=token_env_key,
            group_id=group_id,
            status="online",
            last_checked=datetime.now(timezone.utc).isoformat(),
        )
        self._cache[group_id] = info
        log.info(f"Bot kaydedildi: @{me.get('username')} → {group_id}")
        return info

    async def get_token(self, group_id: str) -> str | None:
        """DB'den şifreli token'ı çöz."""
        import core.db as db
        row = await db.bot_token_getir(group_id)
        if not row:
            # DB'de yoksa env'den al
            from core.config_loader import load_config
            cfg = load_config()
            g = cfg.groups.get_group(group_id)
            return g.bot_token if g else None
        return self.cipher.decrypt(row["encrypted_token"])

    def _update_env_file(self, key: str, value: str):
        """`.env` dosyasını güvenli günceller."""
        env_path = ".env"
        try:
            if os.path.exists(env_path):
                lines = open(env_path).readlines()
                new_lines = []
                found = False
                for line in lines:
                    if line.startswith(f"{key}="):
                        new_lines.append(f"{key}={value}\n")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"{key}={value}\n")
                open(env_path, "w").writelines(new_lines)
            else:
                open(env_path, "a").write(f"{key}={value}\n")
            log.info(f".env güncellendi: {key}")
        except Exception as e:
            log.warning(f".env güncellenemedi: {e}")

    # ── Bot durumu ────────────────────────────
    async def check_status(self, group_id: str) -> BotInfo | None:
        """Bot'un Telegram'a bağlı olup olmadığını kontrol eder."""
        token = await self.get_token(group_id)
        if not token:
            return None
        client = TelegramClient(token)
        try:
            me = await asyncio.wait_for(client.get_me(), timeout=8.0)
            webhook = await client.get_webhook_info()
            if me:
                info = BotInfo(
                    bot_id=me["id"],
                    username=me.get("username", ""),
                    first_name=me.get("first_name", ""),
                    can_join_groups=me.get("can_join_groups", True),
                    can_read_all_group_messages=me.get("can_read_all_group_messages", False),
                    supports_inline_queries=me.get("supports_inline_queries", False),
                    token_env_key="",
                    group_id=group_id,
                    status="online",
                    webhook_url=webhook.get("url", ""),
                    last_checked=datetime.now(timezone.utc).isoformat(),
                )
                self._cache[group_id] = info
                return info
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log.warning(f"Bot durumu kontrol hatası ({group_id}): {e}")
        info = BotInfo(
            bot_id=0, username="", first_name="",
            can_join_groups=False, can_read_all_group_messages=False,
            supports_inline_queries=False,
            token_env_key="", group_id=group_id,
            status="offline",
            last_checked=datetime.now(timezone.utc).isoformat(),
        )
        self._cache[group_id] = info
        return info

    async def check_all_statuses(self, group_ids: list[str]) -> dict[str, BotInfo]:
        tasks = [self.check_status(gid) for gid in group_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = {}
        for gid, r in zip(group_ids, results):
            if isinstance(r, BotInfo):
                out[gid] = r
        return out

    # ── Otomatik kurulum ──────────────────────
    async def setup_bot(
        self,
        group_id: str,
        langs: list[str] | None = None,
        webhook_url: str = "",
        web_app_url: str = "",
        bot_description_tr: str = "",
        bot_description_en: str = "",
    ) -> dict[str, bool | str]:
        """
        Tek adımda tam kurulum:
          1. Komut menüsü (her dil için)
          2. Bot açıklaması
          3. Webhook
          4. Mini App butonu
        Döner: {adım: başarı_durumu}
        """
        from core.bot_i18n import i18n

        token = await self.get_token(group_id)
        if not token:
            return {"error": "Token bulunamadı"}

        client = TelegramClient(token)
        results = {}

        # 1. Komut menüsü
        langs = langs or ["tr", "en"]
        for lang in langs:
            t = i18n.t(lang)
            cmds = [
                {"command": "start",       "description": t.commands().get("start", "Start")},
                {"command": "register",    "description": t.commands().get("register", "Register")},
                {"command": "tasks",       "description": t.commands().get("tasks", "Tasks")},
                {"command": "complete",    "description": t.commands().get("complete", "Complete")},
                {"command": "events",      "description": t.commands().get("events", "Events")},
                {"command": "score",       "description": t.commands().get("score", "Score")},
                {"command": "profile",     "description": t.commands().get("profile", "Profile")},
                {"command": "duel",        "description": t.commands().get("duel", "Duel")},
                {"command": "language",    "description": t.commands().get("language", "Language")},
                {"command": "help",        "description": t.commands().get("help", "Help")},
            ]
            ok = await client.set_my_commands(cmds, lang_code=lang)
            results[f"commands_{lang}"] = ok

        # 2. Bot açıklaması
        if bot_description_tr:
            results["description_tr"] = await client.set_my_description(
                bot_description_tr, "tr")
        if bot_description_en:
            results["description_en"] = await client.set_my_description(
                bot_description_en, "en")

        # 3. Webhook (HTTPS varsa)
        if webhook_url and webhook_url.startswith("https://"):
            full_webhook = f"{webhook_url}/webhook/{group_id}"
            results["webhook"] = await client.set_webhook(full_webhook)
            results["webhook_url"] = full_webhook
        else:
            results["webhook"] = "skipped (no HTTPS URL)"

        # 4. Mini App butonu
        if web_app_url and web_app_url.startswith("https://"):
            results["mini_app"] = await client.set_chat_menu_button(
                chat_id=None,
                url=web_app_url,
                text="🔥 ALEV Panel"
            )
        else:
            results["mini_app"] = "skipped (no WEB_APP_URL)"

        return results

    # ── Grup listeleme ────────────────────────
    async def get_bot_groups(
        self, group_id: str, known_chat_ids: list[int]
    ) -> list[dict]:
        """
        Bilinen chat_id listesini Telegram API ile doğrular.
        Bot'un admin olduğu grupları döner.
        """
        token = await self.get_token(group_id)
        if not token:
            return []
        client = TelegramClient(token)
        me = await client.get_me()
        if not me:
            return []
        bot_id = me["id"]
        groups = []
        for chat_id in known_chat_ids:
            if not chat_id:
                continue
            chat = await client.get_chat(chat_id)
            if not chat:
                continue
            member = await client.get_chat_member(chat_id, bot_id)
            status = member.get("status", "unknown") if member else "not_member"
            groups.append({
                "chat_id": chat_id,
                "title": chat.get("title", ""),
                "type": chat.get("type", ""),
                "bot_status": status,
                "is_admin": status in ("administrator", "creator"),
            })
        return groups


# Singleton
registry = BotRegistry()

"""
core/bot_i18n.py — Bot Çeviri Motoru

Kullanım:
    i18n = BotI18n()

    # Kullanıcı dilini al (DB'den veya varsayılan)
    t = i18n.t("en")

    # Şablonu render et
    msg = t("approval.approved", title="Task A", xp=350, bonus="", level=5)

    # Dil listesi
    langs = i18n.available()  # [{"code":"tr",...}, {"code":"en",...}]

Şablonlar {key} formatını kullanır — str.format_map() ile render edilir.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent.parent / "bot_locales"
SUPPORTED   = {"tr", "en"}
DEFAULT     = "tr"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = LOCALES_DIR / f"{DEFAULT}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_nested(data: dict, key: str) -> str:
    """'approval.approved' → data['approval']['approved']"""
    parts = key.split(".")
    node = data
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return f"[missing: {key}]"
    return str(node)


class BotTranslator:
    """Belirli bir dil için çeviri nesnesi."""

    def __init__(self, lang: str):
        self.lang = lang if lang in SUPPORTED else DEFAULT
        self._data = _load(self.lang)

    def __call__(self, key: str, **kwargs) -> str:
        """
        t("approval.approved", title="Task A", xp=350)
        → "🎉 *Task A approved!* +*350 XP*..."
        """
        template = _get_nested(self._data, key)
        if not kwargs:
            return template
        try:
            return template.format_map(kwargs)
        except (KeyError, ValueError):
            return template

    def get(self, key: str, default: str = "") -> str:
        """Hata vermeden al."""
        result = _get_nested(self._data, key)
        return result if not result.startswith("[missing:") else default

    def commands(self) -> dict[str, str]:
        """Telegram komut menüsü için {komut: açıklama} sözlüğü."""
        return self._data.get("commands", {})

    @property
    def flag(self) -> str:
        return self._data.get("lang_flag", "")

    @property
    def name(self) -> str:
        return self._data.get("lang_name", self.lang)


class BotI18n:
    """Merkezi bot çeviri yöneticisi."""

    def t(self, lang: str) -> BotTranslator:
        """Verilen dil için çevirici döndürür."""
        return BotTranslator(lang if lang in SUPPORTED else DEFAULT)

    def available(self) -> list[dict]:
        return [
            {"code": lang, "name": BotTranslator(lang).name, "flag": BotTranslator(lang).flag}
            for lang in sorted(SUPPORTED)
        ]

    def is_supported(self, lang: str) -> bool:
        return lang in SUPPORTED

    def default(self) -> str:
        return DEFAULT


# Singleton — bot.py'de `from core.bot_i18n import i18n` ile kullanılır
i18n = BotI18n()

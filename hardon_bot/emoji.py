from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import MessageEntity


# Message text uses custom emoji entities; button icons use icon_custom_emoji_id.
CUSTOM_EMOJI = {
    "xrocket": "5316571734604790521",
    "cryptobot": "5406612507034948020",
    "payhot_sbp": "5265074015868822600",
    "payhot_card": "5927169041595634481",
    "payhot_crypto": "5210814920924357232",
}

# Premium custom emoji used as Telegram inline keyboard button icons.
BUTTON_CUSTOM_EMOJI: dict[str, str] = {
    "stars": "5339326389734620043",
    "premium": "5204330443725347173",
    "ton": "5265151230790884988",
    "balance": "5769403330761593044",
    "profile": "5879770735999717115",
    "info": "6028435952299413210",
    "privacy": "6028435952299413210",
    "projects": "6028171274939797252",
    "support": "5213256712911363107",
    "instructions": "5992157823838984339",
    "rules": "6008090211181923982",
    "agreement": "5960551395730919906",
    "payments": "5927169041595634481",
    "advertising": "5938539885907415367",
    "custom_amount": "6039779802741739617",
    "accept": "5825794181183836432",
    "pay": "6039451237743595514",
    "link": "6039451237743595514",
    "check": "5244758760429213978",
    "back": "5307655777635286834",
}


RichTextPart = tuple[str, str | None] | tuple[str, str | None, str]


def rich_text(parts: Iterable[RichTextPart]) -> tuple[str, list[MessageEntity]]:
    text = ""
    entities: list[MessageEntity] = []
    for part in parts:
        value, custom_emoji_id = part[0], part[1]
        formatting = part[2] if len(part) == 3 else None
        offset = len(text.encode("utf-16-le")) // 2
        length = len(value.encode("utf-16-le")) // 2
        if custom_emoji_id:
            text += value
            entities.append(
                MessageEntity(
                    type="custom_emoji",
                    offset=offset,
                    length=length,
                    custom_emoji_id=custom_emoji_id,
                )
            )
        else:
            text += value
        if formatting:
            entities.append(
                MessageEntity(type=formatting, offset=offset, length=length)
            )
    return text, entities

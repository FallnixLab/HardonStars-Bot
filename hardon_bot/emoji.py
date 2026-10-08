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

# Button icons are supplied by the owner. Keys can be filled as IDs arrive.
BUTTON_CUSTOM_EMOJI: dict[str, str] = {}


def rich_text(parts: Iterable[tuple[str, str | None]]) -> tuple[str, list[MessageEntity]]:
    text = ""
    entities: list[MessageEntity] = []
    for value, custom_emoji_id in parts:
        if custom_emoji_id:
            offset = len(text.encode("utf-16-le")) // 2
            text += value
            length = len(value.encode("utf-16-le")) // 2
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
    return text, entities

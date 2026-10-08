from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import MessageEntity


# Bot API custom emoji entities work in message text. Inline keyboard button labels
# are plain strings and cannot carry custom_emoji entities.
CUSTOM_EMOJI = {
    "xrocket": "5316571734604790521",
    "cryptobot": "5406612507034948020",
    "payhot_sbp": "5265074015868822600",
    "payhot_card": "5927169041595634481",
    "payhot_crypto": "5210814920924357232",
}


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

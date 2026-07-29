"""Arabic-aware number normalization for speech generation."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Match

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def _num2words(value: int | float | Decimal, lang: str = "ar") -> str:
    try:
        from num2words import num2words
        return str(num2words(value, lang=lang))
    except Exception:
        return str(value)


def digits_individually(value: str) -> str:
    names = {
        "0": "صفر", "1": "واحد", "2": "اثنان", "3": "ثلاثة", "4": "أربعة",
        "5": "خمسة", "6": "ستة", "7": "سبعة", "8": "ثمانية", "9": "تسعة",
        "+": "زائد", "-": "ناقص", ".": "نقطة", ":": "نقطتان",
    }
    return " ".join(names.get(char, char) for char in value)


def normalize_number_token(token: str, mode: str = "context") -> str:
    token = token.translate(_ARABIC_DIGITS).strip()
    if mode in {"digits", "phone", "serial"}:
        return digits_individually(token)
    if token.endswith("%"):
        return f"{normalize_number_token(token[:-1], 'cardinal')} بالمائة"
    if re.fullmatch(r"\d{1,2}:\d{2}", token):
        hour, minute = token.split(":")
        return f"الساعة {_num2words(int(hour))} و{_num2words(int(minute))} دقيقة"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", token):
        day, month, year = map(int, token.split("/"))
        try:
            date = datetime(year, month, day)
            months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
            return f"{_num2words(date.day, 'ar')} من {months[date.month - 1]} عام {_num2words(date.year, 'ar')}"
        except ValueError:
            return digits_individually(token)
    if re.fullmatch(r"\+?\d[\d\s-]{6,}", token) and mode == "context":
        return digits_individually(re.sub(r"[\s-]", "", token))
    try:
        normalized = token.replace(",", "")
        if "." in normalized:
            whole, fraction = normalized.split(".", 1)
            return f"{_num2words(int(whole))} فاصلة {digits_individually(fraction)}"
        return _num2words(int(normalized))
    except (ValueError, InvalidOperation):
        return token


def normalize_numbers_in_text(text: str, mode: str = "context") -> str:
    text = text.translate(_ARABIC_DIGITS)
    pattern = re.compile(r"(?<!\w)(?:\+?\d[\d\s-]{6,}|\d{1,2}:\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d+(?:[.,]\d+)?%?)(?!\w)")

    def replace(match: Match[str]) -> str:
        return normalize_number_token(match.group(0), mode=mode)

    return pattern.sub(replace, text)

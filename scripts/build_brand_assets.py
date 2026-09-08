#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Готовит фирменные файлы из исходников художника.

Делает три вещи, которые иначе пришлось бы делать руками и каждый раз
по-разному:

  * обрезает прозрачные поля — внутри файла они только уменьшают знак,
    потому что отступы задаёт разметка;
  * приводит квадратный знак к настоящему квадрату — у скруглённого
    квадрата с тенью низ шире верха, и в круглой обрезке домашнего экрана
    несимметричный знак съезжает;
  * раскладывает значок вкладки по нужным размерам, включая вариант для
    iOS на сплошной подложке.

Запуск:  python scripts/build_brand_assets.py <папка-с-исходниками>

Ожидаемые имена: Aurum-Ex-dark.png, Aurum-Ex-marble.png,
A-Ex-icon-dark.png, A-Ex-icon-marble.png. Результат кладётся в
frontend/public/brand. Подробности — docs/brand.md.
"""
import os
import sys

from PIL import Image

DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "frontend", "public", "brand")

PLATES = (("Aurum-Ex-dark.png", "plate-dark.png"),
          ("Aurum-Ex-marble.png", "plate-marble.png"))
ICONS = (("A-Ex-icon-dark.png", "icon-dark.png"),
         ("A-Ex-icon-marble.png", "icon-marble.png"))
FAVICON_SIZES = (32, 192, 512)
APPLE_SIZE = 180
# Поля вокруг знака на подложке для iOS: система накладывает собственное
# скругление, и знак впритык к краю оно срежет.
APPLE_PADDING = 0.12
# Цвет подложки для iOS. Совпадает с --surface-0 тёмного «золотого»
# оформления: значок кладут на домашний экран один раз, и он должен
# выглядеть как само приложение.
APPLE_BACKGROUND = (13, 13, 13, 255)


def trimmed(path):
    """Картинка без прозрачных полей. Тень остаётся: её пиксели не вполне
    прозрачны и в рамку попадают."""
    img = Image.open(path).convert("RGBA")
    box = img.split()[-1].getbbox()
    return img.crop(box) if box else img


def save(img, name):
    path = os.path.join(DST, name)
    img.save(path, optimize=True)
    print("%-22s %4d x %4d  %d КБ" % (name, img.width, img.height, os.path.getsize(path) // 1024))


def squared(img):
    side = max(img.width, img.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def main(src):
    if not os.path.isdir(src):
        raise SystemExit("нет такой папки: " + src)
    os.makedirs(DST, exist_ok=True)

    for name, out in PLATES:
        save(trimmed(os.path.join(src, name)), out)

    icons = {}
    for name, out in ICONS:
        icon = squared(trimmed(os.path.join(src, name)))
        icons[out] = icon
        save(icon, out)

    dark = icons["icon-dark.png"]
    for size in FAVICON_SIZES:
        save(dark.resize((size, size), Image.LANCZOS), "favicon-%d.png" % size)

    pad = int(APPLE_SIZE * APPLE_PADDING)
    canvas = Image.new("RGBA", (APPLE_SIZE, APPLE_SIZE), APPLE_BACKGROUND)
    inner = dark.resize((APPLE_SIZE - pad * 2, APPLE_SIZE - pad * 2), Image.LANCZOS)
    canvas.paste(inner, (pad, pad), inner)
    save(canvas, "apple-touch-icon.png")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

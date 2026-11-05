"""Free, deterministic artwork and encrypted recipient helpers for LINE promotions."""

import base64
import hashlib
import hmac
import io
import os
import random

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw


def _recipient_key(secret: str, customer_key: str) -> bytes:
    if not secret:
        raise ValueError("Promotion encryption is not configured")
    context = ("wm-line-promo-recipient-v1:" + customer_key).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), context, hashlib.sha256).digest()


def encrypt_recipient_id(user_id: str, secret: str, customer_key: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_recipient_key(secret, customer_key)).encrypt(
        nonce, user_id.encode("utf-8"), customer_key.encode("utf-8")
    )
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
    return "v1:" + encoded


def decrypt_recipient_id(encrypted_id: str, secret: str, customer_key: str) -> str:
    version, encoded = encrypted_id.split(":", 1)
    if version != "v1":
        raise ValueError("Unsupported encrypted recipient format")
    encoded += "=" * (-len(encoded) % 4)
    raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    plaintext = AESGCM(_recipient_key(secret, customer_key)).decrypt(
        raw[:12], raw[12:], customer_key.encode("utf-8")
    )
    return plaintext.decode("utf-8")


def build_monthly_artwork_png(month_key: str) -> bytes:
    """Generate fresh monthly artwork without an external image API or embedded copy."""
    seed = int.from_bytes(hashlib.sha256(month_key.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    palettes = [
        ((246, 241, 232), (39, 63, 61), (202, 158, 87), (231, 216, 193)),
        ((239, 243, 239), (42, 74, 83), (197, 145, 77), (213, 228, 221)),
        ((248, 239, 236), (83, 57, 62), (194, 139, 95), (232, 210, 201)),
        ((239, 237, 246), (58, 58, 82), (190, 157, 98), (218, 213, 234)),
    ]
    background, dark, accent, light = palettes[seed % len(palettes)]
    size = 1024
    image = Image.new("RGB", (size, size), background)
    draw = ImageDraw.Draw(image)

    # A soft, deterministic gradient changes with each campaign month.
    for y in range(size):
        mix = y / (size * 1.7)
        color = tuple(int(background[i] * (1 - mix) + light[i] * mix) for i in range(3))
        draw.line((0, y, size, y), fill=color)

    # Repeating arcs and dots create a new composition for each month.
    for index in range(10):
        x = rng.randint(-220, size + 120)
        y = rng.randint(-180, size + 180)
        diameter = rng.randint(90, 340)
        color = accent if index % 3 == 0 else light
        draw.ellipse((x, y, x + diameter, y + diameter), outline=color, width=rng.randint(3, 12))

    # Sign panel with a paper stack and a stamp-like seal, using the brand palette.
    panel = (155, 165, 870, 735)
    draw.rounded_rectangle(panel, radius=46, fill=(255, 253, 249), outline=dark, width=12)
    draw.rounded_rectangle((215, 225, 810, 670), radius=30, fill=background, outline=accent, width=8)
    draw.rounded_rectangle((310, 770, 755, 910), radius=26, fill=dark)
    for offset in range(5):
        x = 365 + offset * 52
        draw.rounded_rectangle((x, 805, x + 34, 875), radius=7, fill=accent if offset == 2 else light)
    seal_x, seal_y = rng.randint(210, 800), rng.randint(210, 690)
    draw.ellipse((seal_x - 54, seal_y - 54, seal_x + 54, seal_y + 54), fill=accent, outline=dark, width=7)
    draw.ellipse((seal_x - 29, seal_y - 29, seal_x + 29, seal_y + 29), outline=(255, 253, 249), width=5)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()

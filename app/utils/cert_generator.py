import json
from typing import Dict, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import qrcode


def _load_coordinates(path: str) -> Dict:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def _get_font(font_path: Optional[str], font_size: int) -> ImageFont.FreeTypeFont:
	"""Load a TrueType font honoring font_size. Fallback to DejaVuSans bundled with PIL when font_path is None.
	Using ImageFont.load_default() ignores font_size, so avoid it for dynamic rendering.
	"""
	tried = []
	try:
		if font_path and os.path.exists(font_path):
			return ImageFont.truetype(font_path, font_size)
		tried.append(str(font_path))
	except Exception:
		pass
	# Try common bundled fonts
	candidates = [
		"DejaVuSans.ttf",
		os.path.join(os.path.dirname(ImageFont.__file__), "../fonts/DejaVuSans.ttf"),
		os.path.join(os.path.dirname(ImageFont.__file__), "fonts", "DejaVuSans.ttf"),
	]
	for c in candidates:
		try:
			if c and os.path.exists(c):
				return ImageFont.truetype(c, font_size)
			# Some environments resolve by name only
			return ImageFont.truetype("DejaVuSans.ttf", font_size)
		except Exception:
			tried.append(c)
			continue
	# Final fallback: default bitmap font (may not match size precisely)
	return ImageFont.load_default()


def _draw_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font_path: Optional[str], font_size: int, color: str, anchor: str = "mm") -> None:
	font = _get_font(font_path, font_size)
	draw.text((x, y), text, fill=color, font=font, anchor=anchor)


def _paste_qr(image: Image.Image, value: str, x: int, y: int, size: int) -> None:
	qr = qrcode.QRCode(border=1, box_size=10)
	qr.add_data(value)
	qr.make(fit=True)
	qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
	qr_img = qr_img.resize((size, size))
	image.paste(qr_img, (x, y))


def generate_certificate_png(template_path: str, coordinates_path: str, fields: Dict[str, str], qr_value: Optional[str], output_path: str) -> str:
	base = Image.open(template_path).convert("RGB")
	draw = ImageDraw.Draw(base)
	coords = _load_coordinates(coordinates_path)

	# Draw dynamic fields
	for key, meta in coords.get("fields", {}).items():
		val = fields.get(key, "")
		if not val:
			continue
		x, y = int(meta.get("x", 0)), int(meta.get("y", 0))
		font_path = meta.get("font_path")
		font_size = int(meta.get("font_size", 36))
		color = meta.get("color", "#000000")
		anchor = meta.get("anchor", "mm")
		_draw_text(draw, val, x, y, font_path, font_size, color, anchor)

	# QR code
	qr_meta = coords.get("qr")
	if qr_meta and qr_value:
		x, y = int(qr_meta.get("x", 0)), int(qr_meta.get("y", 0))
		size = int(qr_meta.get("size", 180))
		_paste_qr(base, qr_value, x, y, size)

	base.save(output_path, format="PNG")
	return output_path

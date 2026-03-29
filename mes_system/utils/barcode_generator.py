"""Generazione barcode Code128 e QR code per etichette."""

import io
import json
from datetime import date

import barcode
from barcode.writer import ImageWriter
import qrcode


def generate_code128(data: str) -> bytes:
    """Genera barcode Code128 come immagine PNG."""
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    bc = code128(data, writer=writer)

    buffer = io.BytesIO()
    bc.write(buffer, options={
        "module_width": 0.3,
        "module_height": 10,
        "font_size": 8,
        "text_distance": 3,
    })
    buffer.seek(0)
    return buffer.read()


def generate_qr(data: dict | str) -> bytes:
    """Genera QR code come immagine PNG.

    Se data è un dict, viene serializzato come JSON.
    """
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def generate_reel_label_data(
    barcode_id: str,
    mpn: str,
    description: str,
    quantity: int,
    supplier: str,
    lot_number: str | None = None,
    weight_g: float | None = None,
    operator: str | None = None,
) -> dict:
    """Genera i dati per un'etichetta reel completa.

    Restituisce un dict con tutti i dati per stampare l'etichetta,
    inclusi Code128 e QR code come bytes base64.
    """
    qr_data = {
        "id": barcode_id,
        "mpn": mpn,
        "desc": description,
        "qty": quantity,
        "supplier": supplier,
        "lot": lot_number,
        "weight": weight_g,
        "date": str(date.today()),
        "op": operator,
    }

    return {
        "barcode_id": barcode_id,
        "mpn": mpn,
        "description": description,
        "quantity": quantity,
        "supplier": supplier,
        "lot_number": lot_number,
        "weight_g": weight_g,
        "date": str(date.today()),
        "operator": operator,
        "code128_bytes": generate_code128(barcode_id),
        "qr_bytes": generate_qr(qr_data),
    }

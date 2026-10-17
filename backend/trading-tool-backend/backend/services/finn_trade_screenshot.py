"""Strict, bounded PNG ingestion for private trade-review screenshots."""

import hashlib
import struct
import zlib

from fastapi import HTTPException


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 3 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 4_000_000


def validate_png(data: bytes) -> tuple[bytes, int, int, str]:
    if len(data) > MAX_BYTES or not data.startswith(PNG_SIGNATURE):
        raise HTTPException(422, "Alleen PNG tot 3 MB wordt ondersteund")
    cursor = len(PNG_SIGNATURE)
    chunks = []
    image_data = bytearray()
    width = height = channels = 0
    phase = 0
    while cursor + 12 <= len(data):
        length = struct.unpack_from(">I", data, cursor)[0]
        end = cursor + 12 + length
        if end > len(data) or length > MAX_BYTES:
            raise HTTPException(422, "Ongeldige PNG")
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        crc = struct.unpack_from(">I", data, cursor + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise HTTPException(422, "Ongeldige PNG checksum")
        if kind == b"IHDR" and phase == 0 and length == 13:
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            channels = {2: 3, 6: 4}.get(color, 0)
            if (not channels or depth != 8 or compression or filtering or interlace
                    or not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION
                    or width * height > MAX_PIXELS):
                raise HTTPException(422, "PNG-afmetingen of kleurtype niet ondersteund")
            chunks.append(data[cursor:end])
            phase = 1
        elif kind == b"IDAT" and phase in {1, 2}:
            image_data.extend(payload)
            chunks.append(data[cursor:end])
            phase = 2
        elif kind == b"IEND" and phase in {2, 4} and length == 0 and end == len(data):
            chunks.append(data[cursor:end])
            phase = 3
            break
        elif phase in {1, 2, 4} and len(kind) == 4 and 97 <= kind[0] <= 122:
            # Ancillary chunks may contain EXIF/text or color-profile metadata.
            # Accept common screenshots, but strip all metadata before storing.
            if phase == 2:
                phase = 4
        else:
            raise HTTPException(422, "PNG bevat niet-ondersteunde inhoud")
        cursor = end
    if phase != 3:
        raise HTTPException(422, "PNG is onvolledig")
    expected = height * (1 + width * channels)
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(bytes(image_data), expected + 1)
    except zlib.error:
        raise HTTPException(422, "PNG-pixels zijn ongeldig") from None
    if len(raw) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise HTTPException(422, "PNG-pixels zijn ongeldig")
    stride = 1 + width * channels
    if any(raw[row * stride] > 4 for row in range(height)):
        raise HTTPException(422, "PNG-filter is ongeldig")
    normalized = b"".join([PNG_SIGNATURE, *chunks])
    return normalized, width, height, hashlib.sha256(normalized).hexdigest()

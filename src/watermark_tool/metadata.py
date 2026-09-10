"""Rebuild safe output metadata; never copy stale geometry, thumbnails or MakerNotes."""

from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from PIL import Image, IptcImagePlugin, PngImagePlugin

from .drawing import HEIC_SUFFIXES, register_heif_opener
from .utils import warn

# Deliberately exclude device serials, MakerNotes and embedded thumbnails.
ROOT_TAGS = {271, 272, 306, 315, 33432}
EXIF_TAGS = {
    33434,
    33437,
    34855,
    34864,
    34865,
    34866,
    34867,
    36867,
    36868,
    36880,
    36881,
    36882,
    37377,
    37378,
    37379,
    37380,
    37381,
    37382,
    37383,
    37384,
    37385,
    37386,
    37520,
    37521,
    37522,
    41986,
    41987,
    41988,
    41989,
    41990,
    41991,
    41992,
    41993,
    41994,
    42034,
    42035,
    42036,
}
NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
XMP_FIELDS = {
    f"{{{NS['dc']}}}{name}" for name in ("creator", "rights", "title", "description", "subject")
}
XMP_FIELDS.add(f"{{{NS['xmp']}}}Rating")


def safe_xmp(raw, iptc):
    root = ET.Element(f"{{{NS['x']}}}xmpmeta")
    rdf = ET.SubElement(root, f"{{{NS['rdf']}}}RDF")
    desc = ET.SubElement(rdf, f"{{{NS['rdf']}}}Description")
    values = {}
    if raw:
        try:
            source = ET.fromstring(raw)
            for node in source.iter():
                if node.tag in XMP_FIELDS:
                    values[node.tag] = [text for text in node.itertext() if text.strip()]
                for key, value in node.attrib.items():
                    if key in XMP_FIELDS:
                        values[key] = [value]
        except (ET.ParseError, ValueError):
            warn("XMP 无法解析，跳过损坏的信息。")
    for tag, field in (
        ((2, 80), "creator"),
        ((2, 116), "rights"),
        ((2, 120), "description"),
        ((2, 25), "subject"),
    ):
        value = iptc.get(tag)
        key = f"{{{NS['dc']}}}{field}"
        if value and key not in values:
            entries = value if isinstance(value, list) else [value]
            values[key] = [
                v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
                for v in entries
            ]
    for key, texts in values.items():
        if not texts:
            continue
        field = ET.SubElement(desc, key)
        if key.endswith("Rating"):
            field.text = texts[0]
        else:
            kind = "Seq" if key.endswith("creator") else "Bag" if key.endswith("subject") else "Alt"
            array = ET.SubElement(field, f"{{{NS['rdf']}}}{kind}")
            for text in texts:
                item = ET.SubElement(array, f"{{{NS['rdf']}}}li")
                if kind == "Alt":
                    item.set("{http://www.w3.org/XML/1998/namespace}lang", "x-default")
                item.text = text
    return ET.tostring(root, encoding="utf-8") if len(desc) else None


def png_metadata(path):
    """Read metadata even after IDAT, seeking past pixels without decompressing them."""
    with open(path, "rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("PNG 文件签名无效")
        parser = PngImagePlugin.PngStream(stream)
        while True:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("PNG 文件不完整")
            length, tag = struct.unpack(">I4s", header)
            if tag == b"IEND":
                break
            if tag in {b"eXIf", b"iTXt", b"tEXt", b"zTXt"}:
                if length > PngImagePlugin.MAX_TEXT_MEMORY:
                    raise ValueError("PNG 元数据过大")
                data = parser.call(tag, stream.tell(), length)
                parser.crc(tag, data)
            else:
                stream.seek(length + 4, 1)
        return parser.im_info


def _read_exif_ifd(exif, tag, path):
    if tag not in exif:
        return {}
    try:
        return dict(exif.get_ifd(tag))
    except (OSError, ValueError, TypeError, SyntaxError) as exc:
        warn(f"无法展开 EXIF IFD {tag}：{path}，原因：{exc}")
        return {}


def read_source_metadata(path, image=None):
    """Snapshot metadata once per input, without requesting a pixel decode."""
    if image is None:
        if Path(path).suffix.lower() in HEIC_SUFFIXES:
            register_heif_opener()
        with Image.open(path) as opened:
            return read_source_metadata(path, opened)
    try:
        if image.format == "PNG":
            image.info.update(png_metadata(path))
            # The PNG override loads pixels if this key is missing, even for metadata-only reads.
            image.info.setdefault("exif", b"")
        exif = image.getexif()
        nested = _read_exif_ifd(exif, 34665, path)
        gps = _read_exif_ifd(exif, 34853, path)
        return (
            dict(exif), nested, gps, image.info.copy(), IptcImagePlugin.getiptcinfo(image) or {},
        )
    except (OSError, ValueError, TypeError, SyntaxError) as exc:
        warn(f"无法读取元数据：{path}，原因：{exc}")
        return ({}, {}, {}, image.info.copy(), {})


def collect_metadata(paths, size, policy="safe", preserve_gps=False, *, sources=None):
    if policy == "none":
        return {}
    if sources is None:
        sources = [read_source_metadata(path) for path in paths]
    output = Image.Exif()
    extra = {}
    if len(sources) == 1:
        root, nested, gps, metadata, iptc = sources[0]
        for tag in ROOT_TAGS:
            if tag in root:
                output[tag] = root[tag]
        details = {tag: value for tag, value in nested.items() if tag in EXIF_TAGS}
        # The profile, rather than a stale EXIF sRGB/AdobeRGB assertion, describes color.
        details.update({40962: size[0], 40963: size[1], 40961: 65535})
        output[34665] = details
        if preserve_gps and gps:
            output[34853] = gps
        dpi = metadata.get("dpi")
        if (
            dpi
            and len(dpi) == 2
            and all(isinstance(v, (int, float)) and 0 < v < 100000 for v in dpi)
        ):
            extra["dpi"] = dpi
        xmp = safe_xmp(metadata.get("xmp") or metadata.get("XML:com.adobe.xmp"), iptc)
        if xmp:
            extra["xmp"] = xmp
    else:
        # A collage has no single camera, capture date or location. Keep only common ownership.
        for tag in (315, 33432):
            values = [source[0].get(tag) for source in sources]
            if values[0] and all(value == values[0] for value in values):
                output[tag] = values[0]
        xmps = [
            safe_xmp(source[3].get("xmp") or source[3].get("XML:com.adobe.xmp"), source[4])
            for source in sources
        ]
        if xmps[0] and all(value == xmps[0] for value in xmps):
            extra["xmp"] = xmps[0]
    output[274] = 1
    output[305] = "watermark-tool"
    extra["exif"] = output.tobytes()
    return extra

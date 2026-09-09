from datetime import datetime
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

from .config import (
    GPS_LOCATION_LANGUAGE,
    GPS_LOCATION_TIMEOUT,
    INCLUDE_GPS_LOCATION,
    PhotoMetadata,
)
from .drawing import HEIC_SUFFIXES, register_heif_opener
from .utils import warn


TAG_MAKE = 271
TAG_MODEL = 272
TAG_EXIF_OFFSET = 34665
TAG_GPS_INFO = 34853
TAG_EXPOSURE_TIME = 33434
TAG_F_NUMBER = 33437
TAG_ISO = 34855
TAG_DATETIME_ORIGINAL = 36867
TAG_FOCAL_LENGTH = 37386
TAG_FOCAL_LENGTH_35MM = 41989

GPS_LATITUDE_REF = 1
GPS_LATITUDE = 2
GPS_LONGITUDE_REF = 3
GPS_LONGITUDE = 4

LOCATION_LOOKUP_URL = "https://nominatim.openstreetmap.org/reverse"
LOCATION_LOOKUP_USER_AGENT = "watermark-tool-layout.py/1.0"
LOCATION_CACHE = {}
LAST_LOCATION_LOOKUP_TIME = 0

LOCATION_SUFFIX_PATTERN = re.compile(
    r"\s+("
    r"district|county|city|town|village|municipality|suburb|borough|"
    r"province|state|region|prefecture|ward|county-level city"
    r")$",
    re.IGNORECASE,
)


def clean_exif_value(value):
    """清理 EXIF 值，避免 bytes 等类型影响后续格式化。"""
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip("\x00 ")

    return value


def read_exif_all(image_path):
    """读取照片 EXIF 信息，并展开 ExifOffset 和 GPSInfo 子 IFD。"""
    result = {}
    image_path = str(image_path)

    try:
        if str(image_path).lower().endswith(tuple(HEIC_SUFFIXES)):
            register_heif_opener()

        with Image.open(image_path) as img:
            exif = img.getexif()

            if not exif:
                return result

            for tag_id, value in exif.items():
                result[tag_id] = value

            try:
                exif_ifd = exif.get_ifd(TAG_EXIF_OFFSET)

                for tag_id, value in exif_ifd.items():
                    result[tag_id] = value
            except Exception as exc:
                warn(f"无法展开 ExifOffset：{image_path}，原因：{exc}")

            try:
                gps_ifd = exif.get_ifd(TAG_GPS_INFO)

                if gps_ifd:
                    result[TAG_GPS_INFO] = dict(gps_ifd)
            except Exception as exc:
                if TAG_GPS_INFO in exif:
                    warn(f"无法展开 GPSInfo：{image_path}，原因：{exc}")

    except Exception as exc:
        warn(f"读取 EXIF 失败：{image_path}，原因：{exc}")

    return result


def rational_to_float(value):
    """将 EXIF 里的分数值转换成 float。"""
    value = clean_exif_value(value)

    if value is None:
        return None

    try:
        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value

            if denominator == 0:
                return None

            return numerator / denominator

        return float(value)
    except Exception:
        return None


def format_number(value, decimals=1):
    if value is None:
        return ""

    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def format_exposure_time(value):
    """保留曝光时长；倒数表示的相对误差不超过 0.1% 时才使用 1/N。"""
    v = rational_to_float(value)

    if v is None or not math.isfinite(v) or v <= 0:
        return ""

    if v < 1 and math.isfinite(1 / v):
        denominator = round(1 / v)
        if abs(1 / denominator - v) <= v * 0.001:
            return f"1/{denominator}s"

    return f"{v:.12g}s"


def format_aperture(value):
    v = rational_to_float(value)

    if v is None or not math.isfinite(v) or v <= 0:
        return ""

    return f"f/{format_number(v, 1)}"


def format_iso(value):
    value = clean_exif_value(value)

    if value is None or value == "":
        return ""

    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
    v = rational_to_float(value)
    if v is None or not math.isfinite(v) or v <= 0 or not v.is_integer():
        return ""
    return f"ISO{int(v)}"


def format_focal_length(value):
    v = rational_to_float(value)

    if v is None or not math.isfinite(v) or v <= 0:
        return ""

    return f"{format_number(v, 1)}mm"


def format_photo_date(value, offset=None, subsecond=None):
    """Display the camera's capture time to whole seconds, without timezone conversion."""
    value = clean_exif_value(value)
    if not value:
        return ""
    try:
        dt_obj = datetime.strptime(str(value).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except (TypeError, ValueError):
        warn(f"EXIF 日期格式异常：{value}；忽略该日期。")
        return ""
    return dt_obj.strftime("%a, %d %b %Y %H:%M:%S")


def photo_date_from_exif(exif_data):
    # Digitization/modification dates do not establish when the photo was taken.
    return format_photo_date(exif_data.get(TAG_DATETIME_ORIGINAL))


def format_camera_settings(exif_data):
    items = [
        # 优先使用有效的 35mm 等效焦距，无效时回退到实际焦距。
        format_focal_length(exif_data.get(TAG_FOCAL_LENGTH_35MM))
        or format_focal_length(exif_data.get(TAG_FOCAL_LENGTH)),
        format_aperture(exif_data.get(TAG_F_NUMBER)),
        format_exposure_time(exif_data.get(TAG_EXPOSURE_TIME)),
        format_iso(exif_data.get(TAG_ISO)),
    ]

    return " ".join(item for item in items if item)


def get_gps_value(gps_data, tag_id, tag_name):
    if not isinstance(gps_data, dict):
        return None

    return gps_data.get(tag_id, gps_data.get(tag_name))


def format_gps_ref(value):
    value = clean_exif_value(value)

    if value is None:
        return ""

    return str(value).strip().upper()


def gps_coord_to_decimal(values, ref):
    if not isinstance(values, (tuple, list)) or len(values) != 3:
        return None

    degrees = rational_to_float(values[0])
    minutes = rational_to_float(values[1])
    seconds = rational_to_float(values[2])

    if any(v is None or not math.isfinite(v) or v < 0 for v in (degrees, minutes, seconds)):
        return None
    if minutes >= 60 or seconds >= 60:
        return None

    result = degrees + minutes / 60 + seconds / 3600

    if format_gps_ref(ref) in {"S", "W"}:
        result = -result

    return result


def read_gps_coordinates(exif_data):
    gps_data = exif_data.get(TAG_GPS_INFO)

    if not isinstance(gps_data, dict):
        return None

    lat_values = get_gps_value(gps_data, GPS_LATITUDE, "GPSLatitude")
    lat_ref = get_gps_value(gps_data, GPS_LATITUDE_REF, "GPSLatitudeRef")
    lon_values = get_gps_value(gps_data, GPS_LONGITUDE, "GPSLongitude")
    lon_ref = get_gps_value(gps_data, GPS_LONGITUDE_REF, "GPSLongitudeRef")

    if format_gps_ref(lat_ref) not in {"N", "S"} or format_gps_ref(lon_ref) not in {"E", "W"}:
        return None

    lat = gps_coord_to_decimal(lat_values, lat_ref)
    lon = gps_coord_to_decimal(lon_values, lon_ref)

    if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
        return None

    return lat, lon


def first_address_value(address, keys):
    for key in keys:
        value = address.get(key)

        if value:
            return str(value).strip()

    return ""


def infer_place_from_display_parts(display_parts, address):
    if not display_parts:
        return ""

    country = address.get("country")

    for part in display_parts:
        text = str(part).strip()

        if not text or text.isdigit() or text == country:
            continue

        return text

    return ""


def infer_parent_from_display_parts(display_parts, place, address):
    if not display_parts:
        return ""

    country = address.get("country")

    for part in display_parts:
        text = str(part).strip()

        if not text or text.isdigit() or text == place or text == country:
            continue

        return text

    return ""


def strip_location_suffix(value):
    """去掉照片上不想显示的行政区划后缀。"""
    text = str(value).strip()

    while True:
        stripped = LOCATION_SUFFIX_PATTERN.sub("", text).strip()

        if stripped == text:
            return stripped

        text = stripped


def join_location_parts(place, province):
    parts = []

    for value in (place, province):
        if not value:
            continue

        text = strip_location_suffix(value)

        if not text:
            continue

        if text.lower() in {part.lower() for part in parts}:
            continue

        parts.append(text)

    if parts:
        return ", ".join(parts)

    return ""


def format_location_from_address(address, display_name):
    if not isinstance(address, dict):
        address = {}

    if display_name:
        display_parts = [part.strip() for part in str(display_name).split(",")]
    else:
        display_parts = []

    location_pairs = [
        (
            first_address_value(address, ("town", "village", "municipality", "suburb")),
            first_address_value(
                address,
                ("county", "city_district", "district", "borough", "city"),
            ),
        ),
        (
            first_address_value(address, ("city_district", "district", "borough", "county")),
            first_address_value(address, ("city", "state", "province", "region")),
        ),
        (
            first_address_value(address, ("city",)),
            first_address_value(address, ("state", "province", "region")),
        ),
    ]

    for place, parent in location_pairs:
        if place and parent:
            result = join_location_parts(place, parent)

            if result:
                return result

    fallback_place = infer_place_from_display_parts(display_parts, address)
    fallback_parent = infer_parent_from_display_parts(display_parts, fallback_place, address)

    return join_location_parts(fallback_place, fallback_parent)


def should_prefer_ascii_location(language):
    """英文地点模式下优先返回 Courier New 能稳定显示的 ASCII 文字。"""
    return str(language).lower().startswith("en")


def is_ascii_location(text):
    return bool(text) and str(text).isascii()


def fetch_reverse_geocode_data(lat, lon, language, timeout, zoom):
    deadline = time.monotonic() + timeout
    params = urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "lat": f"{lat:.8f}",
            "lon": f"{lon:.8f}",
            "zoom": zoom,
            "addressdetails": 1,
            "accept-language": language,
        }
    )
    url = f"{LOCATION_LOOKUP_URL}?{params}"

    global LAST_LOCATION_LOOKUP_TIME

    now = time.monotonic()
    elapsed = now - LAST_LOCATION_LOOKUP_TIME

    if elapsed < 1:
        if 1 - elapsed >= timeout:
            raise TimeoutError("地点查询总时间预算已用完")
        time.sleep(1 - elapsed)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": LOCATION_LOOKUP_USER_AGENT,
            "Accept-Language": language,
        },
    )

    LAST_LOCATION_LOOKUP_TIME = time.monotonic()
    remaining = deadline - LAST_LOCATION_LOOKUP_TIME
    if remaining <= 0:
        raise TimeoutError("地点查询总时间预算已用完")
    with urllib.request.urlopen(request, timeout=remaining) as response:
        return json.loads(response.read().decode("utf-8"))


def reverse_geocode_location(lat, lon, language, timeout):
    cache_key = (round(lat, 5), round(lon, 5), language)

    if cache_key in LOCATION_CACHE:
        return LOCATION_CACHE[cache_key]

    location = ""
    deadline = time.monotonic() + timeout
    try:
        zooms = (10, 16, 14, 12, 8) if should_prefer_ascii_location(language) else (10,)

        for zoom in zooms:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            data = fetch_reverse_geocode_data(lat, lon, language, remaining, zoom)
            candidate = format_location_from_address(
                data.get("address"),
                data.get("display_name"),
            )

            if not candidate:
                continue

            if not location:
                location = candidate

            if not should_prefer_ascii_location(language) or is_ascii_location(candidate):
                location = candidate
                break
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            warn(
                "GPS 地点反查被 Nominatim 限流（HTTP 429）。"
                "已停止继续查询，保留已查到的地点（如有）；可稍后重试。"
            )
        else:
            warn(
                f"GPS 地点反查失败：{lat:.6f}, {lon:.6f}，"
                f"HTTP {exc.code} {exc.reason}"
            )
    except Exception as exc:
        warn(f"GPS 地点反查失败：{lat:.6f}, {lon:.6f}，原因：{exc}")

    LOCATION_CACHE[cache_key] = location
    return location


def format_gps_location(exif_data, language=GPS_LOCATION_LANGUAGE, timeout=GPS_LOCATION_TIMEOUT):
    coordinates = read_gps_coordinates(exif_data)

    if coordinates is None:
        return ""

    lat, lon = coordinates
    return reverse_geocode_location(lat, lon, language, timeout)


def read_photo_metadata(
    image_path,
    include_gps_location=INCLUDE_GPS_LOCATION,
    gps_location_language=GPS_LOCATION_LANGUAGE,
    gps_location_timeout=GPS_LOCATION_TIMEOUT,
    *, source=None,
):
    if source is None:
        exif_data = read_exif_all(image_path)
    else:
        root, nested, gps, _, _ = source
        exif_data = {**root, **nested}
        if gps:
            exif_data[TAG_GPS_INFO] = gps
    make = clean_exif_value(exif_data.get(TAG_MAKE, ""))
    model = clean_exif_value(exif_data.get(TAG_MODEL, ""))
    location = ""

    if include_gps_location:
        location = format_gps_location(
            exif_data,
            language=gps_location_language,
            timeout=gps_location_timeout,
        )

    return PhotoMetadata(
        date=photo_date_from_exif(exif_data),
        make=str(make).strip(),
        model=str(model).strip(),
        settings=format_camera_settings(exif_data),
        location=location,
    )

"""Match camera metadata to brand assets and build per-photo logo plans."""

import json
import os
from pathlib import Path
import re

from .config import BRAND_RULES_FILE
from .utils import info, warn

LOGO_FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".svg")
WORD_CHAR_PATTERN = re.compile(r"[a-z0-9]")


def get_brand_rules_path(base_dir):
    """返回品牌匹配规则文件路径，允许用环境变量覆盖。"""
    override = os.environ.get("WATERMARK_BRANDS_FILE")

    if override:
        return Path(override).expanduser()

    return Path(base_dir) / BRAND_RULES_FILE


def load_brand_rules(base_dir):
    """读取外部品牌 logo 匹配规则。"""
    rules_path = get_brand_rules_path(base_dir)

    if not rules_path.exists():
        warn(f"找不到品牌规则文件：{rules_path}。将不添加品牌 logo，只放签名。")
        return []

    try:
        with rules_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"品牌规则文件不是合法 JSON：{rules_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError(f"品牌规则文件顶层必须是对象：{rules_path}")

    brands = data.get("brands")

    if not isinstance(brands, list):
        raise ValueError(f"品牌规则文件缺少 brands 列表：{rules_path}")

    normalized_rules = []

    for idx, brand in enumerate(brands, start=1):
        if not isinstance(brand, dict):
            raise ValueError(f"品牌规则第 {idx} 项必须是对象：{rules_path}")

        logo_file = brand.get("logo")
        keywords = brand.get("keywords", [])
        display_name = brand.get("display_name") or brand.get("name") or logo_file

        if not isinstance(logo_file, str) or not logo_file.strip():
            raise ValueError(f"品牌规则第 {idx} 项缺少 logo 文件名：{rules_path}")

        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"品牌规则第 {idx} 项缺少 keywords 列表：{rules_path}")

        normalized_keywords = []

        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError(f"品牌规则第 {idx} 项包含无效 keyword：{rules_path}")

            normalized_keywords.append(keyword.strip().lower())

        normalized_rules.append(
            {
                "display_name": str(display_name),
                "logo": logo_file,
                "keywords": normalized_keywords,
            }
        )

    return normalized_rules


def resolve_logo_path(base_dir, logo_file):
    """根据规则里的文件名寻找 logo，兼容旧的 *_400.jpg 命名。"""
    base_dir = Path(base_dir)
    logo_file = Path(logo_file)
    exact_path = base_dir / logo_file

    if exact_path.exists():
        return exact_path

    candidates = []
    stem = logo_file.stem

    if stem.endswith("_400"):
        candidates.extend(
            base_dir / f"{stem[:-4]}{suffix}"
            for suffix in LOGO_FILE_SUFFIXES
        )

    candidates.extend(
        base_dir / f"{stem}{suffix}"
        for suffix in LOGO_FILE_SUFFIXES
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def normalize_brand_match_text(value):
    """归一化相机厂商 / 型号文本，用于更稳定的品牌匹配。"""
    return " ".join(str(value or "").lower().split())


def keyword_matches_text(keyword, text):
    """判断关键词是否命中，短字母数字关键词必须满足词边界。"""
    keyword = normalize_brand_match_text(keyword)
    text = normalize_brand_match_text(text)

    if not keyword or not text:
        return False

    if not WORD_CHAR_PATTERN.search(keyword):
        return keyword in text

    if keyword.isalnum():
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None

    return keyword in text


def keyword_specificity(keyword):
    return len(re.sub(r"[^a-z0-9]", "", normalize_brand_match_text(keyword)))


def is_generic_brand_keyword(rule, keyword):
    """品牌名关键词在 model 中出现时不应压过更具体的机型关键词。"""
    keyword = normalize_brand_match_text(keyword)
    display_name = normalize_brand_match_text(rule.get("display_name", ""))
    logo_stem = normalize_brand_match_text(Path(rule.get("logo", "")).stem)
    generic_text = f"{display_name} {logo_stem}"
    generic_tokens = set(re.findall(r"[a-z0-9]+", generic_text))

    return keyword in generic_tokens or keyword == display_name or keyword == logo_stem


def is_specific_model_keyword(rule, keyword):
    """带型号前缀、系列短语的关键词比单纯品牌名更适合覆盖 EXIF Make。"""
    keyword = normalize_brand_match_text(keyword)

    if is_generic_brand_keyword(rule, keyword):
        return False

    return "-" in keyword or " " in keyword


def score_brand_rule_for_camera(rule, make, model):
    """给品牌规则打分，优先选择明确品牌或更具体的机型规则。"""
    best_score = 0

    for keyword in rule["keywords"]:
        specificity = keyword_specificity(keyword)

        if keyword_matches_text(keyword, make):
            best_score = max(best_score, 600 + specificity)

        if keyword_matches_text(keyword, model):
            if is_specific_model_keyword(rule, keyword):
                score = 700 + specificity
            elif is_generic_brand_keyword(rule, keyword):
                score = 250 + specificity
            else:
                score = 300 + specificity

            best_score = max(best_score, score)

    return best_score


def find_brand_rule_by_camera(make, model, base_dir, rules=None):
    """根据 EXIF 里的 Make / Model 选择最可信的品牌规则。"""
    best_rule = None
    best_score = 0

    for rule in load_brand_rules(base_dir) if rules is None else rules:
        score = score_brand_rule_for_camera(rule, make, model)

        if score > best_score:
            best_rule = rule
            best_score = score

    return best_rule


def find_logo_path_by_camera(make, model, base_dir, rules=None):
    """根据外部品牌规则选择 logo，不输出未知品牌警告。"""
    rule = find_brand_rule_by_camera(make, model, base_dir, rules=rules)

    if rule is None:
        return None

    return resolve_logo_path(base_dir, rule["logo"])


def choose_logo_by_camera(make, model, base_dir, warn_unknown=True, rules=None):
    """根据 EXIF 里的相机品牌 Make 和型号 Model 选择 logo。"""
    logo_path = find_logo_path_by_camera(make, model, base_dir, rules=rules)

    if logo_path is not None:
        return logo_path

    if not warn_unknown:
        return None

    warn(
        f"无法找到可用品牌 logo：Make={make or '空'}，Model={model or '空'}。"
        "将不添加 logo，只放签名。"
    )
    return None


def normalize_camera_device_key(make, model):
    """把 EXIF Make / Model 归一成用于判断同一拍摄设备的 key。"""
    make = " ".join((make or "").lower().split())
    model = " ".join((model or "").lower().split())

    if not make and not model:
        return ""

    return f"{make}|{model}"


def select_logo_paths_for_items(items, base_dir):
    """
    为每张照片生成品牌 logo 和签名计划。

    - 单张照片：在该照片右下侧放品牌 logo，并在其上方放签名。
    - 多张照片设备完全一致：只在最右侧照片右下侧放品牌 logo 和签名。
    - 多张照片设备不一致：每张可识别照片都放自己的品牌 logo，只有最右侧有签名。
    """
    if not items:
        return []

    rules = load_brand_rules(base_dir)
    logo_paths = []
    camera_labels = []
    device_keys = []
    unknown_logo_count = 0

    for item in items:
        metadata = item.metadata
        make = metadata.make or ""
        model = metadata.model or ""
        logo_path = choose_logo_by_camera(
            make, model, base_dir, warn_unknown=False, rules=rules,
        )

        camera_labels.append(f"{make or '未识别'} {model or ''}".strip())
        device_keys.append(normalize_camera_device_key(make, model))
        logo_paths.append(logo_path)

        if logo_path is None:
            unknown_logo_count += 1

    info(f"检测到相机：{'；'.join(camera_labels)}")

    rightmost_idx = len(items) - 1
    all_same_device = all(device_keys) and len(set(device_keys)) == 1

    if len(items) == 1 or all_same_device:
        marks = [(None, False) for _ in items]
        marks[rightmost_idx] = (logo_paths[rightmost_idx], True)

        if logo_paths[rightmost_idx] is None:
            warn("无法从所选照片找到可用品牌 logo。将不添加品牌 logo，只放签名。")
        elif len(items) > 1:
            info("所选照片拍摄设备一致：只在最右侧照片添加品牌 logo 和签名。")

        return marks

    marks = [
        (logo_path, idx == rightmost_idx)
        for idx, logo_path in enumerate(logo_paths)
    ]

    if unknown_logo_count:
        warn(
            f"有 {unknown_logo_count} 张照片无法找到可用品牌 logo。"
            "这些照片将不添加品牌 logo。"
        )

    info("所选照片拍摄设备不一致：分别添加可识别的品牌 logo，签名只添加在最右侧照片。")
    return marks

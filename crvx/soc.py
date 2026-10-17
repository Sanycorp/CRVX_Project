"""SoC / GPU knowledge base -> performance tiering & honest engine FPS ceiling.

Data current per October 2026 (Bedrock 26.52 release / 26.70 preview).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import VENDOR_ALIASES, Device, Vendor

# tier: 5 = flagship 2025/2026, 4 = flagship lama / upper-mid,
#       3 = midrange, 2 = entry, 1 = sangat lemah
TIER_NAMES = {5: "FLAGSHIP", 4: "UPPER", 3: "MID", 2: "ENTRY", 1: "LOW"}


@dataclass
class SocInfo:
    name: str
    tier: int
    gpu: str = ""
    vendor: str = ""
    year: int = 2024
    engine_cap: int = 60          # cap FPS Bedrock Android yang realistis
    notes: str = ""


# --------------------------------------------------------------------------- #
# Database SoC (dicocokkan dari ro.soc.model / ro.board.platform / hardware)
# --------------------------------------------------------------------------- #
SOC_DB: Dict[str, SocInfo] = {
    # ---- Qualcomm 2025-2026 ------------------------------------------------
    "sm8850": SocInfo("Snapdragon 8 Elite Gen 5", 5, "Adreno 840", "Qualcomm", 2025, 120),
    "snapdragon 8 elite gen 5": SocInfo("Snapdragon 8 Elite Gen 5", 5, "Adreno 840", "Qualcomm", 2025, 120),
    "sm8750": SocInfo("Snapdragon 8 Elite", 5, "Adreno 830", "Qualcomm", 2024, 120),
    "snapdragon 8 elite": SocInfo("Snapdragon 8 Elite", 5, "Adreno 830", "Qualcomm", 2024, 120),
    "sun": SocInfo("Snapdragon 8 Elite", 5, "Adreno 830", "Qualcomm", 2024, 120),
    "sm8650": SocInfo("Snapdragon 8 Gen 3", 5, "Adreno 750", "Qualcomm", 2023, 120),
    "snapdragon 8 gen 3": SocInfo("Snapdragon 8 Gen 3", 5, "Adreno 750", "Qualcomm", 2023, 120),
    "pineapple": SocInfo("Snapdragon 8 Gen 3", 5, "Adreno 750", "Qualcomm", 2023, 120),
    "sm8635": SocInfo("Snapdragon 8s Gen 3", 4, "Adreno 735", "Qualcomm", 2024, 120),
    "snapdragon 8s gen 3": SocInfo("Snapdragon 8s Gen 3", 4, "Adreno 735", "Qualcomm", 2024, 120),
    "sm8550": SocInfo("Snapdragon 8 Gen 2", 4, "Adreno 740", "Qualcomm", 2022, 120),
    "kalama": SocInfo("Snapdragon 8 Gen 2", 4, "Adreno 740", "Qualcomm", 2022, 120),
    "sm8475": SocInfo("Snapdragon 8+ Gen 1", 4, "Adreno 730", "Qualcomm", 2022, 120),
    "sm8450": SocInfo("Snapdragon 8 Gen 1", 4, "Adreno 730", "Qualcomm", 2021, 90),
    "waipio": SocInfo("Snapdragon 8 Gen 1", 4, "Adreno 730", "Qualcomm", 2021, 90),
    "taro": SocInfo("Snapdragon 8 Gen 1", 4, "Adreno 730", "Qualcomm", 2021, 90),
    "lahaina": SocInfo("Snapdragon 888", 4, "Adreno 660", "Qualcomm", 2020, 90),
    "sm8350": SocInfo("Snapdragon 888", 4, "Adreno 660", "Qualcomm", 2020, 90),
    "sm7675": SocInfo("Snapdragon 7+ Gen 3", 4, "Adreno 732", "Qualcomm", 2024, 120),
    "snapdragon 7+ gen 3": SocInfo("Snapdragon 7+ Gen 3", 4, "Adreno 732", "Qualcomm", 2024, 120),
    "sm7550": SocInfo("Snapdragon 7 Gen 3", 4, "Adreno 720", "Qualcomm", 2023, 120),
    "sm7450": SocInfo("Snapdragon 7 Gen 1", 3, "Adreno 644", "Qualcomm", 2022, 90),
    "sm7325": SocInfo("Snapdragon 778G", 3, "Adreno 642L", "Qualcomm", 2021, 90),
    "lahaina ": SocInfo("Snapdragon 888", 4, "Adreno 660", "Qualcomm", 2020, 90),
    "sm6375": SocInfo("Snapdragon 695", 3, "Adreno 619", "Qualcomm", 2021, 90),
    "holi": SocInfo("Snapdragon 695", 3, "Adreno 619", "Qualcomm", 2021, 90),
    "sm6450": SocInfo("Snapdragon 6 Gen 1", 3, "Adreno 710", "Qualcomm", 2022, 90),
    "sm6115": SocInfo("Snapdragon 662", 2, "Adreno 610", "Qualcomm", 2020, 60),
    "bengal": SocInfo("Snapdragon 662/460", 2, "Adreno 610", "Qualcomm", 2020, 60),
    "sm4250": SocInfo("Snapdragon 480", 2, "Adreno 619", "Qualcomm", 2021, 60),
    "sm4350": SocInfo("Snapdragon 4 Gen 1", 2, "Adreno 619", "Qualcomm", 2022, 60),
    "sm6225": SocInfo("Snapdragon 680", 2, "Adreno 610", "Qualcomm", 2021, 60),
    "sdm665": SocInfo("Snapdragon 665", 2, "Adreno 610", "Qualcomm", 2019, 60),
    "sdm845": SocInfo("Snapdragon 845", 3, "Adreno 630", "Qualcomm", 2018, 90),
    "msm8998": SocInfo("Snapdragon 835", 3, "Adreno 540", "Qualcomm", 2017, 60),

    # ---- MediaTek ---------------------------------------------------------
    "mt6991": SocInfo("Dimensity 9400", 5, "Immortalis-G925", "MediaTek", 2024, 120),
    "dimensity 9400": SocInfo("Dimensity 9400", 5, "Immortalis-G925", "MediaTek", 2024, 120),
    "mt6989": SocInfo("Dimensity 9300", 5, "Immortalis-G720", "MediaTek", 2023, 120),
    "dimensity 9300": SocInfo("Dimensity 9300", 5, "Immortalis-G720", "MediaTek", 2023, 120),
    "mt6985": SocInfo("Dimensity 9200", 4, "Immortalis-G715", "MediaTek", 2022, 120),
    "dimensity 9200": SocInfo("Dimensity 9200", 4, "Immortalis-G715", "MediaTek", 2022, 120),
    "mt6983": SocInfo("Dimensity 9000", 4, "Immortalis-G710", "MediaTek", 2021, 90),
    "mt6897": SocInfo("Dimensity 8300", 4, "Mali-G615", "MediaTek", 2023, 120),
    "dimensity 8300": SocInfo("Dimensity 8300", 4, "Mali-G615", "MediaTek", 2023, 120),
    "dimensity 8300-ultra": SocInfo("Dimensity 8300 Ultra", 4, "Mali-G615", "MediaTek", 2023, 120),
    "mt6896": SocInfo("Dimensity 8200", 4, "Mali-G610", "MediaTek", 2022, 120),
    "mt6895": SocInfo("Dimensity 8100", 3, "Mali-G610", "MediaTek", 2022, 90),
    "dimensity 8100": SocInfo("Dimensity 8100", 3, "Mali-G610", "MediaTek", 2022, 90),
    "mt6893": SocInfo("Dimensity 1200", 3, "Mali-G77", "MediaTek", 2021, 90),
    "mt6891": SocInfo("Dimensity 1100", 3, "Mali-G77", "MediaTek", 2021, 90),
    "mt6889": SocInfo("Dimensity 1000", 3, "Mali-G77", "MediaTek", 2020, 90),
    "mt6878": SocInfo("Dimensity 7300", 3, "Mali-G615", "MediaTek", 2024, 120),
    "dimensity 7300": SocInfo("Dimensity 7300", 3, "Mali-G615", "MediaTek", 2024, 120),
    "mt6855": SocInfo("Dimensity 7200", 3, "Mali-G610", "MediaTek", 2023, 90),
    "mt6835": SocInfo("Dimensity 7025/930", 3, "IMG BXM-8-256", "MediaTek", 2022, 90),
    "mt6833": SocInfo("Dimensity 700", 2, "Mali-G57", "MediaTek", 2020, 60),
    "mt6789": SocInfo("Helio G99", 2, "Mali-G57 MC2", "MediaTek", 2022, 60),
    "helio g99": SocInfo("Helio G99", 2, "Mali-G57 MC2", "MediaTek", 2022, 60),
    "mt6781": SocInfo("Helio G96/G88", 2, "Mali-G57", "MediaTek", 2021, 60),
    "mt6785": SocInfo("Helio G95/G90T", 2, "Mali-G76", "MediaTek", 2019, 60),
    "mt6769": SocInfo("Helio G85/G80", 1, "Mali-G52", "MediaTek", 2020, 60),
    "mt6768": SocInfo("Helio G70/P65", 1, "Mali-G52", "MediaTek", 2019, 60),
    "mt6765": SocInfo("Helio P35/A25", 1, "PowerVR GE8320", "MediaTek", 2018, 30),
    "mt6762": SocInfo("Helio P22", 1, "PowerVR GE8320", "MediaTek", 2018, 30),
    "mt8781": SocInfo("Helio G99 (tablet)", 2, "Mali-G57", "MediaTek", 2022, 60),

    # ---- Samsung Exynos ---------------------------------------------------
    "exynos2500": SocInfo("Exynos 2500", 4, "Xclipse 950", "Samsung", 2025, 120),
    "exynos2400": SocInfo("Exynos 2400", 4, "Xclipse 940", "Samsung", 2024, 120),
    "s5e9945": SocInfo("Exynos 2400", 4, "Xclipse 940", "Samsung", 2024, 120),
    "exynos2200": SocInfo("Exynos 2200", 4, "Xclipse 920", "Samsung", 2022, 90),
    "s5e9925": SocInfo("Exynos 2200", 4, "Xclipse 920", "Samsung", 2022, 90),
    "exynos1480": SocInfo("Exynos 1480", 3, "Xclipse 530", "Samsung", 2024, 90),
    "s5e8845": SocInfo("Exynos 1480", 3, "Xclipse 530", "Samsung", 2024, 90),
    "exynos1380": SocInfo("Exynos 1380", 3, "Mali-G68", "Samsung", 2023, 90),
    "s5e8835": SocInfo("Exynos 1380", 3, "Mali-G68", "Samsung", 2023, 90),
    "exynos1330": SocInfo("Exynos 1330", 2, "Mali-G68", "Samsung", 2023, 60),
    "exynos1280": SocInfo("Exynos 1280", 2, "Mali-G68", "Samsung", 2022, 60),
    "exynos990": SocInfo("Exynos 990", 3, "Mali-G77", "Samsung", 2020, 90),
    "exynos9820": SocInfo("Exynos 9820", 3, "Mali-G76", "Samsung", 2019, 60),
    "exynos9810": SocInfo("Exynos 9810", 2, "Mali-G72", "Samsung", 2018, 60),
    "exynos850": SocInfo("Exynos 850", 1, "Mali-G52", "Samsung", 2020, 30),
    "universal990": SocInfo("Exynos 990", 3, "Mali-G77", "Samsung", 2020, 90),

    # ---- Google Tensor ----------------------------------------------------
    "gs201": SocInfo("Tensor G3", 3, "Immortalis-G715", "Google", 2023, 90),
    "tensor g3": SocInfo("Tensor G3", 3, "Immortalis-G715", "Google", 2023, 90),
    "gs101": SocInfo("Tensor G1/G2", 3, "Mali-G78", "Google", 2021, 90),
    "tensor g4": SocInfo("Tensor G4", 3, "Mali-G715", "Google", 2024, 90),
    "tensor g5": SocInfo("Tensor G5", 4, "PowerVR D-series", "Google", 2025, 120),
    "cheetah": SocInfo("Tensor G2", 3, "Mali-G710", "Google", 2022, 90),
    "oriole": SocInfo("Tensor G1", 3, "Mali-G78", "Google", 2021, 90),

    # ---- HiSilicon / Unisoc ----------------------------------------------
    "kirin9000s": SocInfo("Kirin 9000S", 4, "Maleoon 910", "HiSilicon", 2023, 60, "cap 60 (driver)"),
    "kirin990": SocInfo("Kirin 990", 3, "Mali-G76", "HiSilicon", 2019, 60),
    "kirin9000": SocInfo("Kirin 9000", 4, "Mali-G78", "HiSilicon", 2020, 60),
    "ums9230": SocInfo("Unisoc T616/T612", 1, "Mali-G57", "Unisoc", 2021, 60),
    "ums512": SocInfo("Unisoc T606/T610", 1, "Mali-G57", "Unisoc", 2021, 60),
    "ums501": SocInfo("Unisoc T310", 1, "PowerVR GE8300", "Unisoc", 2019, 30),
    "t7250": SocInfo("Unisoc T7250", 1, "Mali-G57", "Unisoc", 2023, 60),
    "udx710": SocInfo("Unisoc T740", 2, "Mali-G57", "Unisoc", 2021, 60),
}

# Chip gaming khusus (ROG / RedMagic) - engine cap tinggi
GAMING_CHIPS = {"sm8850", "sm8750", "sm8650", "sun", "pineapple", "kalama", "mt6991"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_soc(dev: Device) -> Optional[SocInfo]:
    """Cocokkan SoC perangkat dengan knowledge base."""
    candidates = [
        dev.soc_model, dev.board_platform, dev.codename,
        dev.extras.get("ro.hardware", ""), dev.extras.get("ro.soc.manufacturer", ""),
        dev.gpu_renderer,
    ]
    for raw in candidates:
        key = _norm(raw)
        if not key:
            continue
        if key in SOC_DB:
            return SOC_DB[key]
        for db_key, info in SOC_DB.items():
            if db_key and (db_key in key or key in db_key):
                return info
            if info.name and _norm(info.name) in key:
                return info
    return None


def guess_vendor(manufacturer: str, brand: str, model: str) -> Vendor:
    text = _norm(f"{manufacturer} {brand} {model}")
    for key, vendor in VENDOR_ALIASES.items():
        if key in text:
            return vendor
    return Vendor.GENERIC


def estimate_tier(dev: Device) -> Tuple[int, str]:
    """Tier performa 1-5 + alasan. Pakai DB, fallback ke heuristik."""
    info = classify_soc(dev)
    if info is not None:
        return info.tier, f"SoC terdeteksi: {info.name}"

    score = 0
    reasons: List[str] = []
    if dev.ram_mb >= 11000:
        score += 2
        reasons.append(f"RAM {dev.ram_mb // 1024} GB")
    elif dev.ram_mb >= 7500:
        score += 1
        reasons.append(f"RAM {dev.ram_mb // 1024} GB")
    if dev.cpu_cores >= 8 and dev.cpu_max_khz >= 2_800_000:
        score += 2
        reasons.append(f"{dev.cpu_cores} core @ {dev.cpu_max_khz // 1000} MHz")
    elif dev.cpu_max_khz >= 2_200_000:
        score += 1
        reasons.append(f"max {dev.cpu_max_khz // 1000} MHz")
    if "adreno 7" in _norm(dev.gpu_renderer) or "immortalis" in _norm(dev.gpu_renderer):
        score += 1
        reasons.append(dev.gpu_renderer)
    tier = max(1, min(5, 1 + score))
    return tier, "; ".join(reasons) or "heuristik umum"


def engine_ceiling(dev: Device) -> Tuple[int, str]:
    """Perkiraan jujur cap FPS engine Bedrock di perangkat ini.

    Fakta (Okt 2026): Bedrock Android sering dikunci 60 FPS oleh engine pada
    banyak perangkat meski layar 120 Hz. Cap nyata bergantung SoC + build game.
    """
    info = classify_soc(dev)
    panel = int(dev.panel_max_fps or 60)
    if info is not None:
        cap = min(info.engine_cap, panel)
        why = f"{info.name}: engine cap {info.engine_cap} FPS, layar {panel} Hz"
        if info.notes:
            why += f" ({info.notes})"
        return max(30, cap), why

    tier, _ = estimate_tier(dev)
    cap_by_tier = {5: 120, 4: 120, 3: 90, 2: 60, 1: 45}
    cap = min(cap_by_tier.get(tier, 60), panel)
    return max(30, cap), f"heuristik tier {TIER_NAMES.get(tier, 'MID')} + layar {panel} Hz"


def enrich(dev: Device) -> Device:
    """Isi vendor, tier, engine cap ke objek Device."""
    if dev.vendor == Vendor.GENERIC:
        dev.vendor = guess_vendor(dev.manufacturer, dev.brand, dev.model)
    tier, tier_reason = estimate_tier(dev)
    cap, cap_reason = engine_ceiling(dev)
    dev.engine_cap_fps = cap
    dev.engine_cap_reason = cap_reason
    info = classify_soc(dev)
    dev.extras.setdefault("tier", tier)
    dev.extras.setdefault("tier_name", TIER_NAMES.get(tier, "MID"))
    dev.extras.setdefault("tier_reason", tier_reason)
    dev.extras.setdefault("engine_cap_reason", cap_reason)
    if info is not None:
        dev.extras.setdefault("soc_name", info.name)
        dev.extras.setdefault("gpu_name", info.gpu)
        dev.extras.setdefault("soc_year", info.year)
    if not dev.panel_max_fps and dev.refresh_rates:
        dev.panel_max_fps = dev.refresh_rates[0]
    if not dev.panel_max_fps:
        dev.panel_max_fps = 60.0
    return dev

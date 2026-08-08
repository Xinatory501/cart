from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class RegionConfig:
    code: str          # BY, KZ, UZ
    name: str
    timezone: str
    languages: List[str]
    allowed_project_types: List[str]  # BUSINESS, BANK
    data_policy: str   # GDPR, LGPD, LOCAL
    status: str = 'active'  # active, suspended

REGION_CATALOG: Dict[str, RegionConfig] = {
    'BY': RegionConfig(
        code='BY', name='Беларусь', timezone='Europe/Minsk',
        languages=['ru', 'be'], allowed_project_types=['BUSINESS', 'BANK'],
        data_policy='GDPR', status='active',
    ),
    'KZ': RegionConfig(
        code='KZ', name='Казахстан', timezone='Asia/Almaty',
        languages=['kk', 'ru'], allowed_project_types=['BUSINESS', 'BANK'],
        data_policy='LOCAL', status='active',
    ),
    'UZ': RegionConfig(
        code='UZ', name='Узбекистан', timezone='Asia/Tashkent',
        languages=['uz', 'ru'], allowed_project_types=['BUSINESS'],
        data_policy='LOCAL', status='active',
    ),
}

def get_region(code: str) -> Optional[RegionConfig]:
    return REGION_CATALOG.get(code.upper())

def list_regions() -> List[RegionConfig]:
    return list(REGION_CATALOG.values())

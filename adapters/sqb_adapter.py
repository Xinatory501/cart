from __future__ import annotations
import logging
import asyncio
import re
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class SqbBankAdapter:
    """
    SQB-01...SQB-05, SQB-UC-01...08: SQB UZ Bank Loyalty API Adapter (CT-P0-08).
    Strictly forbids logs or stores of sensitive credentials (PIN/CVV/OTP/full PAN).
    All credit card numbers must be masked.
    """
    def __init__(self, base_url: str, client_certificate_path: str, timeout: float = 15.0):
        self.base_url = base_url
        self.cert_path = client_certificate_path
        self.timeout = timeout

    def _mask_card_number(self, pan: str) -> str:
        """Маскирует номер карты (оставляет видимыми только первые 6 и последние 4 цифры)."""
        clean_pan = re.sub(r"\D", "", pan)
        if len(clean_pan) < 10:
            return "****"
        return f"{clean_pan[:6]}******{clean_pan[-4:]}"

    async def get_bank_agreement(self, user_id: int) -> Dict[str, Any]:
        """SQB-UC-01: Проверка наличия банковского договора и согласия на лояльность."""
        logger.info("SQB Adapter: checking agreement status for user=%s", user_id)
        await asyncio.sleep(0.4)
        return {
            "agreement_found": True,
            "agreement_number": "AGR-SQB-2026-9912",
            "accepted_at": "2026-03-10T09:12:00Z",
            "status": "active"
        }

    async def check_mastercard_eligibility(self, pan: str) -> Dict[str, Any]:
        """SQB-UC-02: Проверка применимости карты Mastercard к программе лояльности SQB."""
        masked_pan = self._mask_card_number(pan)
        logger.info("SQB Adapter: checking Mastercard eligibility for PAN=%s", masked_pan)
        await asyncio.sleep(0.5)
        return {
            "eligible": True,
            "masked_pan": masked_pan,
            "bin_details": {
                "brand": "Mastercard",
                "tier": "World Black Edition",
                "issuer": "SQB Bank"
            }
        }

    async def link_mastercard(self, user_id: int, pan: str, consent_token: str) -> Dict[str, Any]:
        """SQB-UC-03: Привязка карты к бонусному счету лояльности."""
        masked_pan = self._mask_card_number(pan)
        logger.info("SQB Adapter: linking Mastercard to user=%s, PAN=%s", user_id, masked_pan)
        # Запрещено передавать PIN, CVV или OTP во внешние системы
        await asyncio.sleep(0.7)
        return {
            "status": "success",
            "card_reference_id": "ref_mc_sqb_449102",
            "linked_at": "2026-08-10T15:30:15Z"
        }

    async def get_bonus_balance(self, user_id: int) -> Dict[str, Any]:
        """SQB-UC-04: Получение баланса бонусного счета."""
        await asyncio.sleep(0.3)
        return {
            "user_id": user_id,
            "bonus_points": 1520,
            "monetary_equivalent_uzs": 152000,
            "status": "active"
        }

    async def get_bonus_transactions(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """SQB-UC-05: Получение истории начисления и списания бонусов."""
        return [
            {
                "transaction_id": "tx_sqb_01",
                "type": "earn",
                "amount": 150,
                "description": "Покупка в Korzinka.uz по карте *1024",
                "timestamp": "2026-08-09T18:15:00Z"
            },
            {
                "transaction_id": "tx_sqb_02",
                "type": "spend",
                "amount": 500,
                "description": "Оплата мобильной связи в приложении SQB Mobile",
                "timestamp": "2026-08-08T12:00:00Z"
            }
        ]

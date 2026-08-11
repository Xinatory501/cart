from __future__ import annotations
import logging
import asyncio
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class NiveaLoyaltyAdapter:
    """
    NIV-01...NIV-05, NIV-UC-01...09: NIVEA Brand Loyalty API Adapter (CT-P0-08).
    Handles lookup for participant status, points, campaign products, and receipt validations.
    """
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    async def check_participant_status(self, user_phone: str) -> Dict[str, Any]:
        """NIV-UC-01: Получение статуса участника и его согласий по телефону."""
        logger.info("NIVEA Adapter: checking status for phone mask=%s", user_phone[:5] + "***" + user_phone[-2:])
        await asyncio.sleep(0.5)  # Mock delay
        # Simulation
        return {
            "status": "active",
            "participant_id": "niv_parts_9921",
            "consents": ["personal_data", "marketing_sms"],
            "registered_at": "2026-01-15T12:00:00Z"
        }

    async def get_points_balance(self, participant_id: str) -> Dict[str, Any]:
        """NIV-UC-02: Запрос баланса баллов лояльности."""
        await asyncio.sleep(0.3)
        return {
            "participant_id": participant_id,
            "balance": 450,
            "pending_balance": 50,
            "spent_balance": 1200
        }

    async def get_campaign_products(self) -> List[Dict[str, Any]]:
        """NIV-UC-03: Получение товаров, участвующих в промо-акциях."""
        return [
            {"product_id": "nivea_01", "name": "NIVEA Cream 150ml", "points_value": 50},
            {"product_id": "nivea_02", "name": "NIVEA Soft 200ml", "points_value": 60},
            {"product_id": "nivea_03", "name": "NIVEA Deodorant Roll-on", "points_value": 30}
        ]

    async def register_receipt(self, participant_id: str, receipt_fn: str, fd: str, fp: str) -> Dict[str, Any]:
        """NIV-UC-04: Регистрация чека покупки для начисления баллов."""
        logger.info("NIVEA Adapter: registering receipt FN=%s FD=%s FP=%s", receipt_fn, fd, fp)
        await asyncio.sleep(0.8)
        return {
            "status": "pending_validation",
            "receipt_id": "rec_nivea_8871",
            "submitted_at": "2026-08-10T15:30:00Z",
            "estimated_points": 100
        }

    async def get_receipt_status(self, receipt_id: str) -> Dict[str, Any]:
        """NIV-UC-05: Запрос статуса проверки зарегистрированного чека."""
        return {
            "receipt_id": receipt_id,
            "status": "approved",
            "validated_at": "2026-08-10T16:00:00Z",
            "points_awarded": 100
        }

    async def claim_reward(self, participant_id: str, reward_id: str) -> Dict[str, Any]:
        """NIV-UC-09: Списание баллов и выдача награды (купона)."""
        logger.info("NIVEA Adapter: claiming reward %s for participant %s", reward_id, participant_id)
        return {
            "status": "success",
            "coupon_code": "NIV-PROMO-SUMMER-2026",
            "expiry_date": "2026-12-31T23:59:59Z"
        }

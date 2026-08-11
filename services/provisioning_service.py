from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session
from database.models import Region, ProjectProfile, BotInstance, ProvisioningEvent

logger = logging.getLogger(__name__)

async def bootstrap_provisioning_catalog() -> None:
    """Заполняет справочники регионов и шаблонов при первом старте (CT-P0-07)."""
    async with get_session() as session:
        # 1. Заполняем регионы
        result = await session.execute(select(Region.code))
        existing_regions = set(result.scalars().all())

        regions_to_add = [
            Region(
                code="BY",
                name="Беларусь",
                timezone="Europe/Minsk",
                languages="ru,be",
                allowed_project_types="BUSINESS,BANK",
                data_policy="GDPR"
            ),
            Region(
                code="KZ",
                name="Казахстан",
                timezone="Asia/Almaty",
                languages="kk,ru",
                allowed_project_types="BUSINESS,BANK",
                data_policy="LOCAL"
            ),
            Region(
                code="UZ",
                name="Узбекистан",
                timezone="Asia/Tashkent",
                languages="uz,ru",
                allowed_project_types="BUSINESS,BANK",  # SQB требует BANK (CT-P0-07)
                data_policy="LOCAL"
            )
        ]

        for r in regions_to_add:
            if r.code not in existing_regions:
                session.add(r)
                logger.info("Provisioning: Registered region %s", r.code)

        # 2. Заполняем шаблоны профилей проектов
        result = await session.execute(select(ProjectProfile.name))
        existing_profiles = set(result.scalars().all())

        profiles_to_add = [
            ProjectProfile(
                name="BUSINESS_DEFAULT",
                project_type="BUSINESS",
                required_modules="core,kb,loyalty_brand",
                config_defaults=json.dumps({
                    "working_hours_start": "09:00",
                    "working_hours_end": "18:00",
                    "working_days": "Mon-Fri",
                    "holiday_mode": "0"
                })
            ),
            ProjectProfile(
                name="BANK_DEFAULT",
                project_type="BANK",
                required_modules="core,kb,loyalty_bank,encryption_strict,pii_guard",
                config_defaults=json.dumps({
                    "working_hours_start": "00:00",
                    "working_hours_end": "23:59",
                    "working_days": "Mon-Sun",
                    "holiday_mode": "0"
                })
            )
        ]

        for p in profiles_to_add:
            if p.name not in existing_profiles:
                session.add(p)
                logger.info("Provisioning: Registered project profile template %s", p.name)

        await session.commit()


class ProvisioningService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_instance(
        self,
        instance_id: str,
        token: str,
        region_code: str,
        project_type: str,
        support_group_id: Optional[int] = None,
        actor_id: int = 0
    ) -> BotInstance:
        """Регистрация и подготовка нового инстанса бота (ready)."""
        # Валидация региона
        result = await self.session.execute(select(Region).where(Region.code == region_code.upper()))
        region = result.scalar_one_or_none()
        if not region:
            raise ValueError(f"Region {region_code} is not registered in catalog")

        if project_type.upper() not in region.allowed_project_types.split(","):
            raise ValueError(f"Project type {project_type} is not allowed for region {region_code}")

        # Проверка уникальности
        result = await self.session.execute(select(BotInstance).where(BotInstance.instance_id == instance_id))
        if result.scalar_one_or_none():
            raise ValueError(f"BotInstance {instance_id} already exists")

        instance = BotInstance(
            instance_id=instance_id,
            token=token,
            region_code=region_code.upper(),
            project_type=project_type.upper(),
            status="ready",
            support_group_id=support_group_id
        )
        self.session.add(instance)

        event = ProvisioningEvent(
            instance_id=instance_id,
            event_type="create",
            actor_id=actor_id,
            details=f"Created instance with project_type={project_type} in region={region_code}"
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(instance)
        
        logger.info("Provisioning: Created bot instance %s", instance_id)
        return instance

    async def activate_instance(self, instance_id: str, actor_id: int) -> None:
        """Активация инстанса бота (active)."""
        result = await self.session.execute(select(BotInstance).where(BotInstance.instance_id == instance_id))
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError(f"BotInstance {instance_id} not found")

        instance.status = "active"
        instance.updated_at = datetime.utcnow()

        event = ProvisioningEvent(
            instance_id=instance_id,
            event_type="activate",
            actor_id=actor_id,
            details="Activated bot instance"
        )
        self.session.add(event)
        await self.session.commit()
        logger.info("Provisioning: Activated bot instance %s", instance_id)

    async def suspend_instance(self, instance_id: str, actor_id: int) -> None:
        """Приостановка обслуживания инстанса (suspended)."""
        result = await self.session.execute(select(BotInstance).where(BotInstance.instance_id == instance_id))
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError(f"BotInstance {instance_id} not found")

        instance.status = "suspended"
        instance.updated_at = datetime.utcnow()

        event = ProvisioningEvent(
            instance_id=instance_id,
            event_type="suspend",
            actor_id=actor_id,
            details="Suspended bot instance"
        )
        self.session.add(event)
        await self.session.commit()
        logger.info("Provisioning: Suspended bot instance %s", instance_id)

from __future__ import annotations
import json
import logging
from aiohttp import web
from typing import Dict, Any

from config import settings
from database.database import get_session
from database.repository import ChatRepository
from utils.security_headers import get_cors_headers
from utils.rate_limiter import InMemoryRateLimiter

logger = logging.getLogger(__name__)

# Инициализируем рейт-лимитер (60 запросов в минуту)
rate_limiter = InMemoryRateLimiter(requests_per_minute=60)

def get_auth_token() -> str:
    """Get configured API token for WEB-06 auth."""
    token = getattr(settings, "WEB_API_TOKEN", "") or os.environ.get("WEB_API_TOKEN", "")
    if not token:
        # Fallback to a deterministic token if not configured
        token = f"cartame-{settings.INSTANCE_ID or 'dev'}"
    return token

def json_response(data: Any, status: int = 200, headers: Dict[str, str] = None) -> web.Response:
    """Helper to return JSON response with WEB-07 security headers."""
    cors_headers = get_cors_headers()
    if headers:
        cors_headers.update(headers)
    return web.json_response(
        data,
        status=status,
        headers=cors_headers
    )

# --- Middlewares ---

@web.middleware
async def auth_middleware(request: web.Request, handler) -> web.Response:
    """WEB-06: Bearer token validation middleware."""
    if request.path == "/api/v1/health":
        return await handler(request)
        
    auth_header = request.headers.get("Authorization", "")
    expected_token = get_auth_token()
    
    if not auth_header.startswith("Bearer ") or auth_header[7:] != expected_token:
        return json_response({"error": "Unauthorized"}, status=401)
        
    return await handler(request)

@web.middleware
async def rate_limit_middleware(request: web.Request, handler) -> web.Response:
    """WEB-09: Rate limiting middleware."""
    ip = request.remote or "unknown"
    allowed, retry_after = rate_limiter.is_allowed(ip)
    if not allowed:
        return json_response(
            {"error": "Too Many Requests", "retry_after": retry_after},
            status=429,
            headers={"Retry-After": str(retry_after)}
        )
    return await handler(request)


# --- Handlers ---

async def handle_health(request: web.Request) -> web.Response:
    """GET /api/v1/health"""
    return json_response({"status": "ok", "instance_id": settings.INSTANCE_ID})

async def handle_session(request: web.Request) -> web.Response:
    """GET /api/v1/session?user_id=123"""
    user_id_str = request.query.get("user_id")
    if not user_id_str:
        return json_response({"error": "Missing user_id parameter"}, status=400)
        
    try:
        user_id = int(user_id_str)
    except ValueError:
        return json_response({"error": "Invalid user_id parameter"}, status=400)
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        # Получаем активную сессию
        db_session = await chat_repo.get_active_session(user_id)
        if not db_session:
            return json_response({"error": "No active session found"}, status=404)
            
        return json_response({
            "id": db_session.id,
            "user_id": db_session.user_id,
            "ticket_code": db_session.ticket_code,
            "case_status": db_session.case_status,
            "started_at": db_session.started_at.isoformat() if db_session.started_at else None,
            "is_active": db_session.is_active
        })

async def handle_messages(request: web.Request) -> web.Response:
    """GET /api/v1/messages?session_id=123&limit=50"""
    session_id_str = request.query.get("session_id")
    limit_str = request.query.get("limit", "50")
    
    if not session_id_str:
        return json_response({"error": "Missing session_id parameter"}, status=400)
        
    try:
        session_id = int(session_id_str)
        limit = int(limit_str)
    except ValueError:
        return json_response({"error": "Invalid session_id or limit parameters"}, status=400)
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        history = await chat_repo.get_session_history(session_id, limit=limit)
        
        result = []
        for msg in history:
            result.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "media_type": msg.media_type,
                "file_id": msg.file_id,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            })
            
        return json_response({"session_id": session_id, "messages": result})

async def handle_feedback(request: web.Request) -> web.Response:
    """POST /api/v1/feedback (WEB-05)"""
    try:
        data = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)
        
    session_id = data.get("session_id")
    rating = data.get("rating")
    comment = data.get("comment", "")
    
    if not session_id or rating is None:
        return json_response({"error": "Missing session_id or rating"}, status=400)
        
    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError()
    except ValueError:
        return json_response({"error": "Rating must be an integer between 1 and 5"}, status=400)
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        
        # Проверяем существование сессии
        db_session = await chat_repo.get_session(session_id)
        if not db_session:
            return json_response({"error": "Session not found"}, status=404)
            
        # Сохраняем оценку CSAT в БД
        from database.models import CsatResponse
        from datetime import datetime
        
        # Удаляем старую оценку, если она была (обеспечивает idempotency)
        from sqlalchemy import delete
        await session.execute(delete(CsatResponse).where(CsatResponse.session_id == session_id))
        
        csat = CsatResponse(
            session_id=session_id,
            user_id=db_session.user_id,
            score=rating,
            feedback_text=comment,
            created_at=datetime.utcnow()
        )
        session.add(csat)
        await session.commit()
        
        logger.info("Saved CSAT feedback via Web API: session_id=%d, rating=%d", session_id, rating)
        return json_response({"status": "success", "message": "Feedback submitted successfully"})


# --- Server Lifecycle ---

class WebApiServer:
    """Background service runner for the Web API."""
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.runner = None
        
    async def start(self):
        """Starts the aiohttp web server in the background."""
        app = web.Application(middlewares=[rate_limit_middleware, auth_middleware])
        
        # Routes
        app.router.add_get("/api/v1/health", handle_health)
        app.router.add_get("/api/v1/session", handle_session)
        app.router.add_get("/api/v1/messages", handle_messages)
        app.router.add_post("/api/v1/feedback", handle_feedback)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info("Web API Server started on http://%s:%d", self.host, self.port)
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await self.runner.cleanup()
            logger.info("Web API Server stopped")
            
import os

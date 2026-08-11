from __future__ import annotations
import asyncio
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

import hmac
import hashlib
import base64
import time
from typing import Optional

class SessionTokenManager:
    """Manages JWT-like signed session tokens for secure client identification without third-party dependencies."""
    @staticmethod
    def generate_token(user_id: int, session_id: int, secret_key: str) -> str:
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "exp": int(time.time()) + 86400 * 30  # 30 days
        }
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        
        signature = hmac.new(
            secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        
        return f"{payload_b64}.{sig_b64}"

    @staticmethod
    def verify_token(token: str, secret_key: str) -> Optional[dict]:
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            payload_b64, sig_b64 = parts
            
            expected_sig = hmac.new(
                secret_key.encode(),
                payload_b64.encode(),
                hashlib.sha256
            ).digest()
            expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")
            
            if not hmac.compare_digest(sig_b64, expected_sig_b64):
                return None
                
            padding = "=" * (4 - len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode()
            payload = json.loads(payload_json)
            
            if payload.get("exp", 0) < time.time():
                return None
                
            return payload
        except Exception:
            return None

def get_auth_token() -> str:
    """Get configured API token for WEB-06 auth."""
    token = getattr(settings, "WEB_API_TOKEN", "") or os.environ.get("WEB_API_TOKEN", "")
    # Запрещаем deterministic fallback токен в продакшене (CT-P0-04)
    if not token or token == "changeme" or token.startswith("cartame-"):
        return ""
    return token

def json_response(request: Optional[web.Request] = None, data: Any = None, status: int = 200, headers: Dict[str, str] = None) -> web.Response:
    """Helper to return JSON response with WEB-07 security headers."""
    # Если data передана как первый позиционный аргумент
    if not isinstance(request, web.BaseRequest) and request is not None:
        data, request = request, None

    origin = request.headers.get("Origin") if request else None
    cors_headers = get_cors_headers(origin)
    if headers:
        cors_headers.update(headers)
    return web.json_response(
        data,
        status=status,
        headers=cors_headers
    )

# --- Middlewares ---

@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    """WEB-07: Handles preflight OPTIONS queries for all routes."""
    if request.method == "OPTIONS":
        origin = request.headers.get("Origin")
        headers = get_cors_headers(origin)
        return web.Response(status=204, headers=headers)
    return await handler(request)

@web.middleware
async def auth_middleware(request: web.Request, handler) -> web.Response:
    """WEB-06: Dual-mode bearer token validation middleware (Service API or Session JWT)."""
    if request.path == "/api/v1/health":
        return await handler(request)
        
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return json_response(request, {"error": "Missing or invalid Authorization header"}, status=401)
        
    token = auth_header[7:].strip()
    master_token = get_auth_token()
    
    # 1. Проверяем master token (для админки и service-to-service)
    if master_token and token == master_token:
        request["is_master"] = True
        return await handler(request)
        
    # 2. Проверяем session token (для web-клиента)
    secret_key = os.environ.get("SECRET_ENCRYPTION_KEY", "fallback-secret-key-12345")
    payload = SessionTokenManager.verify_token(token, secret_key)
    if payload:
        request["is_master"] = False
        request["session_payload"] = payload
        return await handler(request)
        
    return json_response(request, {"error": "Unauthorized"}, status=401)

@web.middleware
async def rate_limit_middleware(request: web.Request, handler) -> web.Response:
    """WEB-09: Rate limiting middleware."""
    ip = request.remote or "unknown"
    allowed, retry_after = rate_limiter.is_allowed(ip)
    if not allowed:
        return json_response(
            request,
            {"error": "Too Many Requests", "retry_after": retry_after},
            status=429,
            headers={"Retry-After": str(retry_after)}
        )
    return await handler(request)


# --- Handlers ---

async def handle_health(request: web.Request) -> web.Response:
    """GET /api/v1/health"""
    return json_response(request, {"status": "ok", "instance_id": settings.INSTANCE_ID})

async def handle_session(request: web.Request) -> web.Response:
    """GET /api/v1/session?user_id=123"""
    user_id_str = request.query.get("user_id")
    if not user_id_str:
        return json_response(request, {"error": "Missing user_id parameter"}, status=400)
        
    try:
        user_id = int(user_id_str)
    except ValueError:
        return json_response(request, {"error": "Invalid user_id parameter"}, status=400)
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        # Получаем активную сессию
        db_session = await chat_repo.get_active_session(user_id)
        if not db_session:
            return json_response(request, {"error": "No active session found"}, status=404)
            
        secret_key = os.environ.get("SECRET_ENCRYPTION_KEY", "fallback-secret-key-12345")
        web_token = SessionTokenManager.generate_token(db_session.user_id, db_session.id, secret_key)
        
        return json_response(request, {
            "id": db_session.id,
            "user_id": db_session.user_id,
            "ticket_code": db_session.ticket_code,
            "case_status": db_session.case_status,
            "started_at": db_session.started_at.isoformat() if db_session.started_at else None,
            "is_active": db_session.is_active,
            "web_token": web_token
        })

async def handle_messages(request: web.Request) -> web.Response:
    """GET /api/v1/messages?session_id=123&limit=50"""
    session_id_str = request.query.get("session_id")
    limit_str = request.query.get("limit", "50")
    
    if not session_id_str:
        return json_response(request, {"error": "Missing session_id parameter"}, status=400)
        
    try:
        session_id = int(session_id_str)
        limit = int(limit_str)
    except ValueError:
        return json_response(request, {"error": "Invalid session_id or limit parameters"}, status=400)
        
    # IDOR Protection: Check resource ownership (CT-P0-04)
    if not request.get("is_master", False):
        payload = request.get("session_payload", {})
        if payload.get("session_id") != session_id:
            logger.warning("IDOR attempt blocked: session_id=%d doesn't match token session_id=%s", session_id, payload.get("session_id"))
            return json_response(request, {"error": "Access Denied: You do not own this session (IDOR protection)"}, status=403)
            
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
            
        return json_response(request, {"session_id": session_id, "messages": result})

async def handle_feedback(request: web.Request) -> web.Response:
    """POST /api/v1/feedback (WEB-05)"""
    try:
        data = await request.json()
    except Exception:
        return json_response(request, {"error": "Invalid JSON"}, status=400)
        
    session_id = data.get("session_id")
    rating = data.get("rating")
    comment = data.get("comment", "")
    
    if not session_id or rating is None:
        return json_response(request, {"error": "Missing session_id or rating"}, status=400)
        
    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError()
    except ValueError:
        return json_response(request, {"error": "Rating must be an integer between 1 and 5"}, status=400)
        
    # IDOR Protection: Check resource ownership (CT-P0-04)
    if not request.get("is_master", False):
        payload = request.get("session_payload", {})
        if payload.get("session_id") != session_id:
            logger.warning("IDOR attempt blocked in feedback: session_id=%d doesn't match token session_id=%s", session_id, payload.get("session_id"))
            return json_response(request, {"error": "Access Denied: You do not own this session (IDOR protection)"}, status=403)
            
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        
        # Проверяем существование сессии
        db_session = await chat_repo.get_session(session_id)
        if not db_session:
            return json_response(request, {"error": "Session not found"}, status=404)
            
        # Проверяем, что сессия закрыта или решена (CT-P0-03)
        if db_session.case_status not in ("RESOLVED", "CLOSED"):
            return json_response(request, {"error": "Feedback can only be submitted for resolved or closed sessions"}, status=400)
            
        # Сохраняем оценку CSAT в БД
        from database.models import CsatResponse
        from datetime import datetime
        
        # Удаляем старую оценку, если она была (обеспечивает idempotency)
        from sqlalchemy import delete
        await session.execute(delete(CsatResponse).where(CsatResponse.session_id == session_id))
        
        csat = CsatResponse(
            session_id=session_id,
            user_id=db_session.user_id,
            rating=rating,
            comment=comment,
            ai_handled=db_session.is_ai_active,
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
        expected_token = get_auth_token()
        if not expected_token:
            logger.critical("WEB_API_TOKEN is not configured or is using an insecure default value! Refusing to start Web API Server.")
            raise ValueError("WEB_API_TOKEN must be configured in environment for security (CT-P0-04)!")

        app = web.Application(middlewares=[cors_middleware, rate_limit_middleware, auth_middleware])
        
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

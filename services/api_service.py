import logging
import random
import json
from datetime import datetime
from aiohttp import web
from aiogram import Bot

from config import settings
from database.database import get_session
from database.repository import ChatRepository, UserRepository, ConfigRepository, ClarificationRepository, TrainingRepository
from services.thread_service import ThreadService
from services.bot_profile_service import set_user_bot_key
from services.ai_service import AIService
import re
import html
from locales.loader import get_text

def markdown_to_html(text: str) -> str:
    text = html.escape(text or "")
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"<b>\1</b>", text, flags=re.UNICODE)
    text = re.sub(r"\*([^\*]+?)\*", r"<i>\1</i>", text, flags=re.UNICODE)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text, flags=re.UNICODE)
    text = re.sub(r"\[([^\]]+?)\]\(([^\)]+?)\)", r"<a href=\"\2\">\1</a>", text, flags=re.UNICODE)
    return text

logger = logging.getLogger(__name__)

# Key: user_id (int), Value: list of active WebSockets
active_websockets = {}

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

async def handle_get_chat(request):
    user_id_str = request.match_info.get('user_id')
    try:
        user_id = int(user_id_str)
    except ValueError:
        return web.json_response({"error": "Invalid user_id"}, status=400)
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
            
        history = await chat_repo.get_all_user_history(user_id)
        
    data = []
    for msg in history:
        data.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "is_ai_handled": msg.is_ai_handled,
            "created_at": msg.created_at.isoformat()
        })
        
    return web.json_response({
        "user_id": user_id,
        "username": user.username,
        "first_name": user.first_name,
        "messages": data
    })

async def handle_create_session(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    language = body.get("language", "ru")
    if language not in ("ru", "en", "uz", "kz"):
        language = "ru"
        
    fingerprint = body.get("fingerprint")
    
    bot = request.app['bot']
    thread_service = ThreadService(bot)
    
    user_id = None
    is_new_session = False
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        
        if fingerprint:
            existing_user = await user_repo.get_by_fingerprint(fingerprint)
            if existing_user:
                user_id = existing_user.id
                await user_repo.update_language(user_id, language)
        
        if not user_id:
            user_id = -1 * random.randint(100000000, 999999999)
            while True:
                exists = await user_repo.get_by_id(user_id)
                if not exists:
                    break
                user_id = -1 * random.randint(100000000, 999999999)
                
            user = await user_repo.create(
                user_id=user_id,
                username="web_visitor",
                first_name="Посетитель сайта",
                last_name="",
                fingerprint=fingerprint
            )
            await user_repo.update_language(user_id, language)
            
        active_session = await chat_repo.get_active_session(user_id)
        if not active_session:
            await chat_repo.create_session(user_id)
            is_new_session = True
            
    await set_user_bot_key(user_id, "BOT1")
    
    if is_new_session:
        ticket_number = await thread_service.issue_new_ticket_number(user_id)
        thread_id = await thread_service.ensure_thread_for_user(
            user_id=user_id,
            username="web_visitor",
            first_name="Посетитель сайта",
            force_new=True
        )
    else:
        ticket_number = await thread_service.get_or_create_ticket_number(user_id)
        thread_id = await thread_service.ensure_thread_for_user(
            user_id=user_id,
            username="web_visitor",
            first_name="Посетитель сайта",
            force_new=False
        )
    
    logger.info("Web session established: user_id=%s, ticket_number=%s, thread_id=%s, fingerprint=%s", user_id, ticket_number, thread_id, fingerprint)
    
    return web.json_response({
        "user_id": user_id,
        "ticket_number": ticket_number,
        "language": language
    })

async def handle_update_language(request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        language = body.get("language")
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)
        
    if language not in ("ru", "en", "uz", "kz"):
        return web.json_response({"error": "Invalid language"}, status=400)
        
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
        await user_repo.update_language(user_id, language)
        
    return web.json_response({"status": "ok", "language": language})

async def handle_close_session(request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        rating = int(body.get("rating", 5))
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)

    if rating < 1 or rating > 5:
        return web.json_response({"error": "Rating must be between 1 and 5"}, status=400)

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        user_repo = UserRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
            
        active_session = await chat_repo.get_active_session(user_id)
        if not active_session:
            return web.json_response({"error": "No active session found"}, status=404)
            
        ticket_number = active_session.ticket_number
        session_id = active_session.id
        
        active_session.is_active = False
        active_session.ended_at = datetime.utcnow()
        session.add(active_session)
        await session.commit()
        
        messages = await chat_repo.get_session_history(session_id, limit=200)
        operator_name = "ИИ-ассистент"
        
        support_msgs = [m for m in messages if m.role == "support"]
        if support_msgs:
            named_support = [m for m in support_msgs if m.operator_name]
            if named_support:
                operator_name = named_support[-1].operator_name
            else:
                operator_name = "Оператор поддержки"

    try:
        from services.bot_profile_service import get_profile_for_bot, get_user_bot_key
        from services.thread_service import ThreadService
        from bot_instance import get_bot
        
        bot_key = await get_user_bot_key(user_id)
        bot_profile = get_profile_for_bot(bot_key)
        if bot_profile:
            bot = get_bot(bot_key)
            thread_service = ThreadService(bot, bot_profile)
            await thread_service.send_rating_log(
                user_id=user_id,
                ticket_number=ticket_number,
                operator_name=operator_name,
                stars=rating
            )
    except Exception as e:
        logger.error("Failed to send rating log to support group: %s", e)

    return web.json_response({"status": "ok", "operator_name": operator_name})


async def handle_get_messages(request):
    user_id_str = request.match_info.get('user_id')
    try:
        user_id = int(user_id_str)
    except ValueError:
        return web.json_response({"error": "Invalid user_id"}, status=400)
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_all_session_history(active_session.id)
        else:
            history = []
        
    data = []
    for msg in history:
        # Format for front-end
        data.append({
            "id": msg.id,
            "role": msg.role,
            "content": markdown_to_html(msg.content) if msg.role == "assistant" else msg.content,
            "created_at": msg.created_at.isoformat()
        })
        
    return web.json_response({
        "user_id": user_id,
        "messages": data
    })

async def handle_post_message(request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
        text = body.get("text", "").strip()
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)
        
    if not text:
        return web.json_response({"error": "Empty message text"}, status=400)
        
    bot = request.app['bot']
    # Start task in background to process the message
    import asyncio
    asyncio.create_task(process_web_message(user_id, text, bot))
    
    return web.json_response({"status": "ok"})

async def handle_new_chat(request):
    try:
        body = await request.json()
        user_id = int(body.get("user_id"))
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            return web.json_response({"error": "User not found"}, status=404)

        await chat_repo.create_session(user_id)

    bot = request.app['bot']
    thread_service = ThreadService(bot)
    ticket_number = await thread_service.issue_new_ticket_number(user_id)

    await thread_service.ensure_thread_for_user(
        user_id=user_id,
        username=user.username,
        first_name=user.first_name,
        force_new=True
    )
    await thread_service.send_system_message(
        user_id=user_id,
        text=f"Пользователь начал новый диалог с сайта.\nНомер чата: <code>{ticket_number}</code>",
        username=user.username,
        first_name=user.first_name,
    )

    logger.info("Created new web chat: user_id=%s, ticket_number=%s", user_id, ticket_number)

    return web.json_response({
        "user_id": user_id,
        "ticket_number": ticket_number,
    })

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    user_id_str = request.match_info.get('user_id')
    try:
        user_id = int(user_id_str)
    except ValueError:
        await ws.close(code=4000, message=b"Invalid user_id")
        return ws
        
    if user_id not in active_websockets:
        active_websockets[user_id] = []
    active_websockets[user_id].append(ws)
    
    logger.info("WebSocket connected for user_id: %s", user_id)
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    text = data.get("text", "").strip()
                except Exception:
                    text = msg.data.strip()
                    
                if not text:
                    continue
                    
                bot = request.app['bot']
                await process_web_message(user_id, text, bot)
                
            elif msg.type == web.WSMsgType.ERROR:
                logger.error('ws connection closed with exception %s', ws.exception())
    finally:
        if user_id in active_websockets:
            active_websockets[user_id].remove(ws)
            if not active_websockets[user_id]:
                active_websockets.pop(user_id, None)
        logger.info("WebSocket disconnected for user_id: %s", user_id)
        
    return ws

async def send_to_web_user(user_id: int, content: str, role: str) -> bool:
    ws_list = active_websockets.get(user_id, [])
    if not ws_list:
        return False
        
    payload = json.dumps({
        "role": role,
        "content": content,
        "created_at": datetime.utcnow().isoformat()
    })
    
    success = False
    for ws in list(ws_list):
        try:
            await ws.send_str(payload)
            success = True
        except Exception as e:
            logger.error("Failed to send WebSocket message to user %s: %s", user_id, e)
            
    return success

async def process_web_message(user_id: int, text: str, bot: Bot):
    thread_service = ThreadService(bot)
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        clarification_repo = ClarificationRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            logger.error("Web visitor user not found: %s", user_id)
            return
            
        active_session = await chat_repo.get_active_session(user_id)
        if not active_session:
            # Create a session if it doesn't exist
            await chat_repo.create_session(user_id)
            active_session = await chat_repo.get_active_session(user_id)
            
        is_ai_active = active_session.is_ai_active
        clarification = await clarification_repo.get_active(user_id)
        
    combined_question = text
    if clarification:
        original_question = clarification.original_question
        combined_question = f"{original_question}\n\nУточнение: {text}"
        
    # Always forward user message to Telegram support thread immediately
    if thread_service._is_support_group_configured():
        await thread_service.send_user_message(
            user_id=user_id,
            text=combined_question,
            username=user.username,
            first_name=user.first_name
        )
        
    if clarification:
        async with get_session() as session:
            clarification_repo = ClarificationRepository(session)
            chat_repo = ChatRepository(session)
            await clarification_repo.mark_answered(clarification.id)
            await chat_repo.add_message(user_id, "user", combined_question, is_ai_handled=True)
            
        await run_ai_response(user_id, active_session.id, combined_question, bot, thread_service, user)
        
    elif is_ai_active:
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(user_id, "user", text, is_ai_handled=True)
            
        await run_ai_response(user_id, active_session.id, text, bot, thread_service, user)
        
    else:
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(user_id, "user", text, is_ai_handled=False)

async def run_ai_response(user_id: int, session_id: int, source_text: str, bot: Bot, thread_service: ThreadService, user):
    ai_service = await AIService.get_service()
    if not ai_service:
        error_msg = get_text("error_try_later", user.language)
        await send_to_web_user(user_id, error_msg, role="assistant")
        await thread_service.send_log_message(f"AI service unavailable. web_user_id={user_id}")
        return
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        messages_history = await chat_repo.get_session_history(session_id, limit=30)
        
    messages = []
    for msg in reversed(messages_history):
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})
            
    async with get_session() as session:
        training_repo = TrainingRepository(session)
        system_prompt = await ai_service.get_system_prompt(training_repo, user.language)
            
    response_parts = []
    try:
        async for chunk in ai_service.get_response_stream(
            messages=messages,
            system_prompt=system_prompt,
            user_id=user_id,
            thread_id=user.thread_id,
            bot=bot,
        ):
            response_parts.append(chunk)
    except Exception as e:
        logger.error("AI response stream error for web visitor %s: %s", user_id, e)
        
    response_text = "".join(response_parts).strip()
    if not response_text:
        error_msg = get_text("error_try_later", user.language)
        await send_to_web_user(user_id, error_msg, role="assistant")
        return
        
    lowered = response_text.lower()
    
    if "ignore_offtopic" in lowered:
        off_topic_text = get_text("off_topic", user.language)
        if thread_service._is_support_group_configured():
            await thread_service.send_system_message(
                user_id=user_id,
                text="AI пометил вопрос с сайта как оффтоп. Сообщение передано в поддержку.",
                username=user.username,
                first_name=user.first_name,
            )
            await thread_service.send_ai_message(
                user_id=user_id,
                text=off_topic_text,
                username=user.username,
                first_name=user.first_name,
            )
        await send_to_web_user(user_id, off_topic_text, role="assistant")
        return
        
    if "need_clarification" in lowered:
        clarification_text = (
            response_text
            .replace("need_clarification", "")
            .replace("NEED_CLARIFICATION", "")
            .strip()
        )
        if clarification_text:
            async with get_session() as session:
                clarification_repo = ClarificationRepository(session)
                await clarification_repo.create(
                    user_id=user_id,
                    session_id=session_id,
                    original_question=source_text,
                    clarification_question=clarification_text,
                )
            await send_to_web_user(user_id, markdown_to_html(clarification_text), role="assistant")
            if thread_service._is_support_group_configured():
                await thread_service.send_ai_message(
                    user_id=user_id,
                    text=clarification_text,
                    username=user.username,
                    first_name=user.first_name,
                )
            return
            
    clean_text = (
        response_text
        .replace("ignore_offtopic", "")
        .replace("IGNORE_OFFTOPIC", "")
        .replace("call_people", "")
        .replace("CALL_PEOPLE", "")
        .replace("need_clarification", "")
        .replace("NEED_CLARIFICATION", "")
        .strip()
    )
    
    if not clean_text:
        error_msg = get_text("error_try_later", user.language)
        await send_to_web_user(user_id, error_msg, role="assistant")
        return
        
    if "call_people" in lowered:
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.deactivate_ai(user_id)
            await chat_repo.add_message(user_id, "assistant", clean_text)
            
        await send_to_web_user(user_id, markdown_to_html(clean_text), role="assistant")
        await send_to_web_user(user_id, get_text("human_called", user.language), role="assistant")
        
        if thread_service._is_support_group_configured():
            await thread_service.notify_human_needed(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
            )
            await thread_service.send_ai_message(
                user_id=user_id,
                text=clean_text,
                username=user.username,
                first_name=user.first_name,
            )
        return
        
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        await chat_repo.add_message(user_id, "assistant", clean_text)
        
    await send_to_web_user(user_id, markdown_to_html(clean_text), role="assistant")
    if thread_service._is_support_group_configured():
        await thread_service.send_ai_message(
            user_id=user_id,
            text=clean_text,
            username=user.username,
            first_name=user.first_name,
        )

async def handle_upload(request):
    reader = await request.multipart()
    user_id = None
    file_bytes = None
    filename = None
    
    while True:
        part = await reader.next()
        if part is None:
            break
            
        if part.name == 'user_id':
            val = await part.text()
            user_id = int(val)
        elif part.name == 'file':
            filename = part.filename
            file_bytes = await part.read(decode=True)
            
    if not user_id or not file_bytes:
        return web.json_response({"error": "Missing user_id or file"}, status=400)
        
    import os
    import secrets
    import string
    
    safe_chars = string.ascii_letters + string.digits + "._-"
    safe_filename = "".join(c for c in (filename or "image.jpg") if c in safe_chars)
    unique_filename = f"{secrets.token_hex(8)}_{safe_filename}"
    
    upload_dir = '/app/data/uploads'
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, unique_filename)
    
    with open(file_path, 'wb') as f:
        f.write(file_bytes)
        
    img_url = f"/uploads/{unique_filename}"
    img_html = f'<span class="photo-link-text" style="color: #3880ff; font-weight: 600; cursor: pointer; text-decoration: underline; display: inline-flex; align-items: center; gap: 4px;" data-src="{img_url}">📷 Фото</span>'
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
            
        active_session = await chat_repo.get_active_session(user_id)
        if not active_session:
            await chat_repo.create_session(user_id)
            active_session = await chat_repo.get_active_session(user_id)
            
        await chat_repo.add_message(user_id, "user", img_html, is_ai_handled=False)
        
    bot = request.app['bot']
    thread_service = ThreadService(bot)
    sent_msg = await thread_service.send_user_photo(
        user_id=user_id,
        photo_bytes=file_bytes,
        filename=filename or "photo.jpg",
        username=user.username,
        first_name=user.first_name
    )
    if sent_msg and sent_msg.photo:
        file_id = sent_msg.photo[-1].file_id
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            await config_repo.set(f"media_file_id:{unique_filename}", file_id)
    
    await send_to_web_user(user_id, img_html, role="user")
    
    return web.json_response({"status": "ok", "url": img_url})

async def handle_export_pdf(request):
    user_id_str = request.match_info.get('user_id')
    try:
        user_id = int(user_id_str)
    except ValueError:
        return web.Response(text="Invalid user_id", status=400)
        
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.Response(text="User not found", status=404)
            
        messages = await chat_repo.get_all_user_history(user_id)
        sessions_list = await chat_repo.get_user_sessions(user_id)
        session_info = {
            s.id: {
                "started_at": s.started_at,
                "ticket_number": s.ticket_number
            }
            for s in sessions_list
        }
        
    from services.export_service import ExportService
    try:
        pdf_bytes = ExportService.export_to_pdf(user_id, user.username or "web_visitor", messages, session_info)
    except Exception as e:
        logger.error("Failed to generate web PDF export: %s", e)
        return web.Response(text=f"Failed to generate PDF: {e}", status=500)
        
    return web.Response(
        body=pdf_bytes,
        content_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="chat_ticket_{user_id}.pdf"',
            'Access-Control-Allow-Origin': '*'
        }
    )

async def handle_export_txt(request):
    user_id_str = request.match_info.get('user_id')
    try:
        user_id = int(user_id_str)
    except ValueError:
        return web.Response(text="Invalid user_id", status=400)
        
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            return web.Response(text="User not found", status=404)
            
        messages = await chat_repo.get_all_user_history(user_id)
        sessions_list = await chat_repo.get_user_sessions(user_id)
        session_info = {
            s.id: {
                "started_at": s.started_at,
                "ticket_number": s.ticket_number
            }
            for s in sessions_list
        }
        
    from services.export_service import ExportService
    try:
        txt_content = ExportService.export_to_txt(user_id, user.username or "web_visitor", messages, session_info)
    except Exception as e:
        logger.error("Failed to generate web TXT export: %s", e)
        return web.Response(text=f"Failed to generate TXT: {e}", status=500)
        
    return web.Response(
        text=txt_content,
        content_type='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename="chat_ticket_{user_id}.txt"',
            'Access-Control-Allow-Origin': '*'
        }
    )

async def handle_serve_media(request):
    import os
    filename = request.match_info.get('filename')
    upload_dir = '/app/data/uploads'
    file_path = os.path.join(upload_dir, filename)
    
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
        
    bot = request.app['bot']
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        file_id = await config_repo.get(f"media_file_id:{filename}")
        
    if not file_id:
        return web.Response(status=404, text="File not found")
        
    try:
        file_info = await bot.get_file(file_id)
        tg_file_path = file_info.file_path
        os.makedirs(upload_dir, exist_ok=True)
        await bot.download_file(tg_file_path, file_path)
        
        if os.path.exists(file_path):
            return web.FileResponse(file_path)
    except Exception as e:
        logger.error("Failed to restore media file %s from Telegram: %s", filename, e)
        
    return web.Response(status=404, text="File failed to restore")

async def cleanup_old_media_task(app):
    import os
    import time
    import asyncio
    upload_dir = '/app/data/uploads'
    while True:
        try:
            await asyncio.sleep(3600)  # every hour
            if os.path.exists(upload_dir):
                now = time.time()
                for filename in os.listdir(upload_dir):
                    file_path = os.path.join(upload_dir, filename)
                    if os.path.isfile(file_path):
                        # If file is older than 2 hours (7200 seconds)
                        if now - os.path.getmtime(file_path) > 7200:
                            os.remove(file_path)
                            logger.info("Cleaned up local media file: %s", filename)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in cleanup_old_media_task: %s", e)

async def start_background_tasks(app):
    import asyncio
    app['cleanup_task'] = asyncio.create_task(cleanup_old_media_task(app))

async def cleanup_background_tasks(app):
    try:
        app['cleanup_task'].cancel()
        await app['cleanup_task']
    except Exception:
        pass

def create_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app['bot'] = bot
    
    # Routes
    app.router.add_get('/api/chat/{user_id}', handle_get_chat)
    app.router.add_post('/api/web/session', handle_create_session)
    app.router.add_get('/api/web/messages/{user_id}', handle_get_messages)
    app.router.add_post('/api/web/message', handle_post_message)
    app.router.add_post('/api/web/new-chat', handle_new_chat)
    app.router.add_post('/api/web/update-language', handle_update_language)
    app.router.add_post('/api/web/close-session', handle_close_session)
    app.router.add_post('/api/web/upload', handle_upload)
    app.router.add_get('/api/web/ws/{user_id}', websocket_handler)
    app.router.add_get('/api/web/export/{user_id}/pdf', handle_export_pdf)
    app.router.add_get('/api/web/export/{user_id}/txt', handle_export_txt)
    
    import os
    os.makedirs('/app/data/uploads', exist_ok=True)
    app.router.add_get('/uploads/{filename}', handle_serve_media)
    app.router.add_static('/uploads/', path='/app/data/uploads')
    
    import asyncio
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    
    return app

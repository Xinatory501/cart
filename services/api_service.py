import logging
from aiohttp import web
from database.database import get_session
from database.repository import ChatRepository, UserRepository

logger = logging.getLogger(__name__)

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

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get('/api/chat/{user_id}', handle_get_chat)
    return app

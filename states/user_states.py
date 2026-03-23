
from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):

    choosing_language = State()

    chatting = State()

    waiting_support = State()

    in_settings = State()


from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    choosing_language = State()
    accepting_privacy = State()   # TG-13: ожидание принятия privacy consent
    chatting = State()
    waiting_support = State()
    in_settings = State()
    waiting_clarification = State()

    entering_csat_comment = State()  # TG-12: ввод комментария к CSAT

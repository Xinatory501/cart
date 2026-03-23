
from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):

    admin_menu = State()

    entering_groq_key = State()

    entering_privacy_url = State()

    entering_training_message = State()
    entering_training_priority = State()

    entering_user_id = State()
    viewing_user_info = State()

    choosing_report_period = State()
    entering_custom_period = State()

    entering_antiflood_threshold = State()
    entering_antiflood_window = State()
    entering_autoban_duration = State()

    entering_api_key = State()
    entering_model_name = State()
    entering_model_display_name = State()
    entering_local_provider_name = State()
    entering_local_provider_base_url = State()
    entering_local_provider_model = State()
    entering_remote_provider_name = State()
    entering_remote_provider_base_url = State()
    entering_remote_provider_api_key = State()
    entering_remote_provider_model = State()
    entering_support_group_id = State()

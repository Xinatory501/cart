"""initial_schema

Revision ID: 7a47994329ec
Revises: None
Create Date: 2026-08-10 13:35:11.672330+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a47994329ec'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. ai_providers
    if 'ai_providers' not in tables:
        op.create_table('ai_providers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )

    # 2. config
    if 'config' not in tables:
        op.create_table('config',
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
        )

    # 3. training_messages
    if 'training_messages' not in tables:
        op.create_table('training_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('kb_status', sa.String(length=20), nullable=False),
        sa.Column('kb_version', sa.Integer(), nullable=False),
        sa.Column('locale', sa.String(length=10), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.BigInteger(), nullable=True),
        sa.Column('reviewer_id', sa.BigInteger(), nullable=True),
        sa.Column('effective_from', sa.DateTime(), nullable=True),
        sa.Column('effective_to', sa.DateTime(), nullable=True),
        sa.Column('superseded_by', sa.Integer(), nullable=True),
        sa.Column('vector_embedding', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    else:
        # Проверяем колонки
        cols = [c['name'] for c in inspector.get_columns('training_messages')]
        if 'kb_status' not in cols:
            op.add_column('training_messages', sa.Column('kb_status', sa.String(length=20), nullable=False, server_default='approved'))
        if 'kb_version' not in cols:
            op.add_column('training_messages', sa.Column('kb_version', sa.Integer(), nullable=False, server_default='1'))
        if 'locale' not in cols:
            op.add_column('training_messages', sa.Column('locale', sa.String(length=10), nullable=True))
        if 'source' not in cols:
            op.add_column('training_messages', sa.Column('source', sa.Text(), nullable=True))
        if 'owner_id' not in cols:
            op.add_column('training_messages', sa.Column('owner_id', sa.BigInteger(), nullable=True))
        if 'reviewer_id' not in cols:
            op.add_column('training_messages', sa.Column('reviewer_id', sa.BigInteger(), nullable=True))
        if 'effective_from' not in cols:
            op.add_column('training_messages', sa.Column('effective_from', sa.DateTime(), nullable=True))
        if 'effective_to' not in cols:
            op.add_column('training_messages', sa.Column('effective_to', sa.DateTime(), nullable=True))
        if 'superseded_by' not in cols:
            op.add_column('training_messages', sa.Column('superseded_by', sa.Integer(), nullable=True))
        if 'vector_embedding' not in cols:
            op.add_column('training_messages', sa.Column('vector_embedding', sa.Text(), nullable=True))

    # 4. users
    if 'users' not in tables:
        op.create_table('users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_banned', sa.Boolean(), nullable=False),
        sa.Column('ban_until', sa.DateTime(), nullable=True),
        sa.Column('thread_id', sa.Integer(), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('consent_version', sa.String(length=50), nullable=True),
        sa.Column('consent_given_at', sa.DateTime(), nullable=True),
        sa.Column('consent_channel', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    else:
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'phone_number' not in cols:
            op.add_column('users', sa.Column('phone_number', sa.String(length=50), nullable=True))
        if 'consent_version' not in cols:
            op.add_column('users', sa.Column('consent_version', sa.String(length=50), nullable=True))
        if 'consent_given_at' not in cols:
            op.add_column('users', sa.Column('consent_given_at', sa.DateTime(), nullable=True))
        if 'consent_channel' not in cols:
            op.add_column('users', sa.Column('consent_channel', sa.String(length=20), nullable=True))

    # 5. admin_actions
    if 'admin_actions' not in tables:
        op.create_table('admin_actions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('admin_id', sa.BigInteger(), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('target_user_id', sa.BigInteger(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('before_value', sa.Text(), nullable=True),
        sa.Column('after_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 6. ai_models
    if 'ai_models' not in tables:
        op.create_table('ai_models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=200), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['ai_providers.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 7. api_keys
    if 'api_keys' not in tables:
        op.create_table('api_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('requests_made', sa.Integer(), nullable=False),
        sa.Column('requests_limit', sa.Integer(), nullable=True),
        sa.Column('limit_reset_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['ai_providers.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 8. chat_sessions
    if 'chat_sessions' not in tables:
        op.create_table('chat_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('ticket_code', sa.String(length=6), nullable=True),
        sa.Column('case_status', sa.String(length=30), nullable=False),
        sa.Column('priority', sa.String(length=5), nullable=True),
        sa.Column('owner_id', sa.BigInteger(), nullable=True),
        sa.Column('resolution_reason', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('consent_version', sa.String(length=50), nullable=True),
        sa.Column('sla_first_response_deadline', sa.DateTime(), nullable=True),
        sa.Column('sla_breached', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('sla_warning_sent', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('support_thread_id', sa.Integer(), nullable=True),
        sa.Column('pinned_message_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_ai_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_chat_sessions_ticket_code'), 'chat_sessions', ['ticket_code'], unique=True)
    else:
        cols = [c['name'] for c in inspector.get_columns('chat_sessions')]
        if 'ticket_code' not in cols:
            op.add_column('chat_sessions', sa.Column('ticket_code', sa.String(length=6), nullable=True))
            op.create_index(op.f('ix_chat_sessions_ticket_code'), 'chat_sessions', ['ticket_code'], unique=True)
        if 'priority' not in cols:
            op.add_column('chat_sessions', sa.Column('priority', sa.String(length=5), nullable=True))
        if 'owner_id' not in cols:
            op.add_column('chat_sessions', sa.Column('owner_id', sa.BigInteger(), nullable=True))
        if 'resolution_reason' not in cols:
            op.add_column('chat_sessions', sa.Column('resolution_reason', sa.Text(), nullable=True))
        if 'category' not in cols:
            op.add_column('chat_sessions', sa.Column('category', sa.String(length=100), nullable=True))
        if 'consent_version' not in cols:
            op.add_column('chat_sessions', sa.Column('consent_version', sa.String(length=50), nullable=True))
        if 'sla_first_response_deadline' not in cols:
            op.add_column('chat_sessions', sa.Column('sla_first_response_deadline', sa.DateTime(), nullable=True))
        if 'sla_breached' not in cols:
            op.add_column('chat_sessions', sa.Column('sla_breached', sa.Boolean(), nullable=False, server_default='0'))
        if 'sla_warning_sent' not in cols:
            op.add_column('chat_sessions', sa.Column('sla_warning_sent', sa.Boolean(), nullable=False, server_default='0'))
        if 'support_thread_id' not in cols:
            op.add_column('chat_sessions', sa.Column('support_thread_id', sa.Integer(), nullable=True))
        if 'pinned_message_id' not in cols:
            op.add_column('chat_sessions', sa.Column('pinned_message_id', sa.Integer(), nullable=True))
        if 'ended_at' not in cols:
            op.add_column('chat_sessions', sa.Column('ended_at', sa.DateTime(), nullable=True))
        if 'resolved_at' not in cols:
            op.add_column('chat_sessions', sa.Column('resolved_at', sa.DateTime(), nullable=True))
        if 'closed_at' not in cols:
            op.add_column('chat_sessions', sa.Column('closed_at', sa.DateTime(), nullable=True))

    # 9. flood_log
    if 'flood_log' not in tables:
        op.create_table('flood_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=False),
        sa.Column('ban_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 10. metrics
    if 'metrics' not in tables:
        op.create_table('metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 11. case_events
    if 'case_events' not in tables:
        op.create_table('case_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('from_value', sa.String(length=50), nullable=True),
        sa.Column('to_value', sa.String(length=50), nullable=True),
        sa.Column('actor_id', sa.BigInteger(), nullable=True),
        sa.Column('actor_role', sa.String(length=30), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 12. chat_history
    if 'chat_history' not in tables:
        op.create_table('chat_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('is_ai_handled', sa.Boolean(), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=True),
        sa.Column('file_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    else:
        cols = [c['name'] for c in inspector.get_columns('chat_history')]
        if 'media_type' not in cols:
            op.add_column('chat_history', sa.Column('media_type', sa.String(length=50), nullable=True))
        if 'file_id' not in cols:
            op.add_column('chat_history', sa.Column('file_id', sa.String(length=255), nullable=True))

    # 13. clarification_contexts
    if 'clarification_contexts' not in tables:
        op.create_table('clarification_contexts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('original_question', sa.Text(), nullable=False),
        sa.Column('clarification_question', sa.Text(), nullable=False),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('answered_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    # 14. csat_responses
    if 'csat_responses' not in tables:
        op.create_table('csat_responses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('operator_id', sa.BigInteger(), nullable=True),
        sa.Column('ai_handled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
        )

    # 15. pending_requests
    if 'pending_requests' not in tables:
        op.create_table('pending_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
        )

    # 16. regions
    if 'regions' not in tables:
        op.create_table('regions',
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('languages', sa.String(length=100), nullable=False, server_default='ru'),
        sa.Column('allowed_project_types', sa.String(length=100), nullable=False, server_default='BUSINESS'),
        sa.Column('data_policy', sa.String(length=50), nullable=False, server_default='LOCAL'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('code')
        )

    # 17. project_profiles
    if 'project_profiles' not in tables:
        op.create_table('project_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('project_type', sa.String(length=20), nullable=False),
        sa.Column('required_modules', sa.Text(), nullable=False),
        sa.Column('config_defaults', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id')
        )

    # 18. bot_instances
    if 'bot_instances' not in tables:
        op.create_table('bot_instances',
        sa.Column('instance_id', sa.String(length=100), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('region_code', sa.String(length=10), nullable=False),
        sa.Column('project_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='ready'),
        sa.Column('support_group_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['region_code'], ['regions.code'], ),
        sa.PrimaryKeyConstraint('instance_id')
        )

    # 19. provisioning_events
    if 'provisioning_events' not in tables:
        op.create_table('provisioning_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instance_id', sa.String(length=100), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.BigInteger(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['bot_instances.instance_id'], ),
        sa.PrimaryKeyConstraint('id')
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    for t in ['provisioning_events', 'bot_instances', 'project_profiles', 'regions',
              'pending_requests', 'csat_responses', 'clarification_contexts', 
              'chat_history', 'case_events', 'metrics', 'flood_log', 
              'chat_sessions', 'api_keys', 'ai_models', 'admin_actions', 
              'users', 'training_messages', 'config', 'ai_providers']:
        if t in tables:
            op.drop_table(t)

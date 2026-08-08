from __future__ import annotations

# WEB-14: OpenAPI 3.0 specification for CartaMe Bot API
OPENAPI_SPEC = {
    'openapi': '3.0.3',
    'info': {
        'title': 'CartaMe Support Bot API',
        'version': '1.0.0',
        'description': 'REST API for CartaMe multi-region support bot platform',
    },
    'paths': {
        '/api/v1/session': {
            'get': {
                'summary': 'Get session info',
                'parameters': [{'name': 'user_id', 'in': 'query', 'required': True, 'schema': {'type': 'integer'}}],
                'responses': {'200': {'description': 'Session data'}},
            }
        },
        '/api/v1/messages': {
            'get': {
                'summary': 'Get message history',
                'parameters': [
                    {'name': 'session_id', 'in': 'query', 'required': True, 'schema': {'type': 'integer'}},
                    {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'default': 50}},
                ],
                'responses': {'200': {'description': 'Message list'}},
            }
        },
        '/api/v1/feedback': {
            'post': {
                'summary': 'Submit CSAT rating (WEB-05)',
                'requestBody': {
                    'content': {'application/json': {'schema': {
                        'type': 'object',
                        'properties': {
                            'session_id': {'type': 'integer'},
                            'rating': {'type': 'integer', 'minimum': 1, 'maximum': 5},
                            'comment': {'type': 'string'},
                        },
                        'required': ['session_id', 'rating'],
                    }}}
                },
                'responses': {'200': {'description': 'Rating saved'}},
            }
        },
        '/api/v1/health': {
            'get': {
                'summary': 'Health check',
                'responses': {'200': {'description': 'OK'}},
            }
        },
    },
    'components': {
        'securitySchemes': {
            'BearerAuth': {'type': 'http', 'scheme': 'bearer'},
        }
    },
    'security': [{'BearerAuth': []}],
}

def get_openapi_spec() -> dict:
    return OPENAPI_SPEC

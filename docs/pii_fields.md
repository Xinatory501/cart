# PII Field Registry — CartaMe Bot

## SEC-06 Compliance

### User table
| Field | Type | PII | Retention | Notes |
|-------|------|-----|-----------|-------|
| id | int | No | Forever | Telegram user ID |
| username | str | Yes | 365 days | Telegram username |
| first_name | str | Yes | 365 days | Display name |
| last_name | str | Yes | 365 days | Optional |
| language | str | No | Forever | Preference |
| role | str | No | Forever | Access control |
| consent_version | str | No | Forever | GDPR audit |
| consent_given_at | datetime | No | Forever | GDPR audit |

### ChatHistory table
| Field | Type | PII | Retention | Notes |
|-------|------|-----|-----------|-------|
| content | str | Yes | 90 days | User messages — may contain PII |
| user_id | int | Ref | 90 days | References User.id |
| role | str | No | 90 days | user/assistant/support |

### CsatResponse table
| Field | Type | PII | Retention | Notes |
|-------|------|-----|-----------|-------|
| rating | int | No | 365 days | Aggregated metrics |
| comment | str | Yes | 90 days | May contain PII |

## GDPR Rights
- **Right to erasure**: Use admin panel → User Management → Delete User Data
- **Data portability**: Use admin panel → Export → TXT/PDF
- **Anonymization**: Export with anonymization flag removes PHONE/EMAIL/CARD/ID

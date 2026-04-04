# astrbot-plugin-counton

Count temporary leave messages in group chats and welcome users when they come back.

## Features

- Detect temporary leave intent messages, such as:
  - 我去一趟厕所
  - 我去洗个澡
  - 先洗个澡
- Track leave duration per user in each group session.
- When the same user sends the next message, treat it as returning:
  - quote the leave message
  - send a welcome text with reason and duration
- Two leave detection methods:
  - Regex real-time detection
  - AI batch detection

## AI batch behavior

AI detection will **not** call the model for every message.
It buffers plain-text messages and triggers one classification request when either condition is met:

- buffered message count reaches `ai_trigger_text_count` (default: 15)
- elapsed time reaches `ai_trigger_minutes` (default: 30)

Whichever comes first triggers the request.

## Config

Use `_conf_schema.json` options:

- `detect_mode`: `regex` / `ai` / `both`
- `regex_patterns`: one regex per line, empty means built-in patterns
- `ai_trigger_text_count`: AI batch count threshold
- `ai_trigger_minutes`: AI batch time threshold in minutes
- `batch_loop_interval_seconds`: polling interval for time-based triggering

## Notes

- This plugin only handles **group text messages**.
- In `both` mode, regex detects immediately, AI acts as a supplemental detector.

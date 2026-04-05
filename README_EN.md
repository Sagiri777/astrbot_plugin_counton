# astrbot-plugin-counton

Count temporary leave messages in group chats, welcome users when they come back, and allow users to set an away status by DM.

## Features

- Detect temporary leave intent messages, such as:
  - 我去一趟厕所
  - 我要去吃饭
  - 我现在去洗澡
  - 我先洗个澡了
  - 我先忙一下
  - 等会再来
- Track leave duration per user in each group session.
- Allow users to set away status and an optional note by sending a private message or a command.
- When someone mentions an away user in a group, the plugin replies to that message with:
  - away status
  - away duration
  - note, if present
- When the same user speaks again after being away for a while, treat it as returning:
  - quote the leave message or the return message
  - send a welcome text with reason, duration, and note
- Two leave detection methods:
  - Regex real-time detection
  - AI batch detection

## AI batch behavior

AI detection will not call the model for every message.
It buffers plain-text messages and triggers one classification request when either condition is met:

- buffered message count reaches `ai_trigger_text_count` (default: 15)
- elapsed time reaches `ai_trigger_minutes` (default: 30)

Whichever comes first triggers the request.

## Config

Use `_conf_schema.json` options:

- `detect_mode`: `regex` / `ai` / `both`
- `regex_patterns`: one regex per line, empty means built-in patterns
- `quote_target`: `leave` / `return`, defaults to `return`
- `return_grace_period_seconds`: follow-up messages sent within this many seconds after the leave message are not counted as a return, defaults to `45`
- `send_welcome_in_high_frequency_chat`: whether to still send the welcome message when the group is in a high-frequency chat burst
- `high_frequency_messages_per_second`: high-frequency threshold based on how many messages arrived in the last 1 second
- `ai_trigger_text_count`: AI batch count threshold
- `ai_trigger_minutes`: AI batch time threshold in minutes
- `batch_loop_interval_seconds`: polling interval for time-based triggering

## Notes

- Automatic leave detection still only applies to group text messages.
- Private away setup examples:
  - `eating`
  - `eating | back later`
  - multi-line input: first line is the reason, remaining lines become the note
- Command examples:
  - `/counton leave eating | back later`
  - `/counton back`
- In `both` mode, regex detects immediately, AI acts as a supplemental detector.
- After a leave message is recorded, only follow-up messages sent later than `return_grace_period_seconds` will be treated as a return.

# astrbot-plugin-counton

群聊临时离开计时插件。识别用户“先离开一下，等会回来”的消息，并在对方回来发言时发送欢迎回来提示。

[English README](./README_EN.md)

## 功能

- 识别群聊里的临时离开意图，例如：
  - 我去一趟厕所
  - 我要去吃饭
  - 我现在去洗澡
  - 我先洗个澡了
  - 我先忙一下
  - 等会再来
- 按群聊维度记录每位用户的离开时长。
- 当同一用户下一次再次发言时，视为“回来”：
  - 可引用离开时的消息或回来时的消息
  - 发送包含离开原因和时长的欢迎消息
- 支持两种离开识别方式：
  - 正则实时识别
  - AI 批量识别

## AI 批处理机制

AI 模式不会为每一条消息单独调用模型。
插件会缓存纯文本消息，并在满足以下任一条件时触发一次批量识别：

- 缓存消息条数达到 `ai_trigger_text_count`，默认 `15`
- 从首条缓存消息开始累计时间达到 `ai_trigger_minutes` 分钟，默认 `30`

哪个条件先满足，就先触发。

## 配置项

可在 [_conf_schema.json](./_conf_schema.json) 中查看以下配置：

- `detect_mode`：识别模式，可选 `regex` / `ai` / `both`
- `regex_patterns`：离开消息正则，每行一条，留空时使用内置规则
- `quote_target`：欢迎消息引用目标，可选 `leave` / `return`，默认 `return`
- `send_welcome_in_high_frequency_chat`：群聊处于高频聊天时，是否仍发送欢迎消息
- `high_frequency_messages_per_second`：高频聊天判定阈值，按最近 1 秒内消息条数计算
- `ai_trigger_text_count`：AI 批量识别触发消息条数
- `ai_trigger_minutes`：AI 批量识别触发时间阈值，单位分钟
- `batch_loop_interval_seconds`：AI 批处理循环检查间隔，单位秒

## 说明

- 当前仅处理**群聊文本消息**。
- 在 `both` 模式下，正则会立即识别，AI 作为补充识别手段。
- 当 `send_welcome_in_high_frequency_chat=false` 且群聊最近 1 秒内消息数达到 `high_frequency_messages_per_second` 时，会跳过这次“欢迎回来”发送。

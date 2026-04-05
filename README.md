# astrbot-plugin-counton

群聊临时离开计时插件。识别用户“先离开一下，等会回来”的消息，并在对方回来发言时发送欢迎回来提示；也支持用户私聊机器人登记离开状态。

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
- 支持用户通过命令设置离开状态与留言。
- 当有人在群里 `@` 正处于离开状态的用户时，会引用该消息提示：
  - 目标用户正在离开中
  - 已离开的时长
  - 留言内容（如果有）
- 当同一用户在离开一段时间后再次发言时，视为“回来”：
  - 可引用离开时的消息或回来时的消息
  - 发送包含离开原因、时长和留言的欢迎消息
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
- `return_grace_period_seconds`：距离离开消息多少秒内的后续消息不计为返回消息，默认 `45`
- `send_welcome_in_high_frequency_chat`：群聊处于高频聊天时，是否仍发送欢迎消息
- `high_frequency_messages_per_second`：高频聊天判定阈值，按最近 1 秒内消息条数计算
- `ai_trigger_text_count`：AI 批量识别触发消息条数
- `ai_provider_id`：插件内部 AI 调用使用的框架提供商，留空时跟随当前会话
- `ai_trigger_minutes`：AI 批量识别触发时间阈值，单位分钟
- `ai_welcome_enabled`：是否启用 AI 生成欢迎回来消息
- `welcome_persona_id`：欢迎回来消息使用的人设，仅在启用 AI 欢迎消息时生效
- `batch_loop_interval_seconds`：AI 批处理循环检查间隔，单位秒

## 说明

- 群聊中的自动离开识别仍仅处理**群聊文本消息**。
- 命令格式：
  - `/counton leave 吃饭 | 晚点回`
  - `/counton back`
- 在 `both` 模式下，正则会立即识别，AI 作为补充识别手段。
- `ai_provider_id` 会同时作用于离开识别和 AI 欢迎语生成，并直接使用该提供商当前绑定的模型。
- `welcome_persona_id` 只会注入到“欢迎回来”消息生成，不参与离开消息识别。
- 当用户发出离开消息后，只有超过 `return_grace_period_seconds` 的后续消息才会被当作“返回”。
- 当 `send_welcome_in_high_frequency_chat=false` 且群聊最近 1 秒内消息数达到 `high_frequency_messages_per_second` 时，会跳过这次“欢迎回来”发送。

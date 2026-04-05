from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.message_components import Plain, Reply
from astrbot.api.platform import MessageType
from astrbot.api.provider import Provider
from astrbot.api.star import Context, Star, register
from astrbot.core import sp


@dataclass(slots=True)
class AwayRecord:
    sender_id: str
    sender_name: str
    reason: str
    leave_text: str
    leave_message_id: str
    leave_timestamp: float
    return_message_id: str = ""


@dataclass(slots=True)
class PendingTextMessage:
    message_id: str
    sender_id: str
    sender_name: str
    text: str
    received_at: float
    message_timestamp: float

class MyPlugin(Star):
    _TEMP_CACHE_KEY = "_counton_away_records"
    _DEFAULT_REGEX_PATTERNS = [
        r"^先\s*(?:去|出|离|忙|洗|吃|上|回|拿|接|开|办|处|补|收|看|打|冲|做|睡)\S*(?:\s*.+)?$",
        r"^我\s*先\s*(?:去|出|离|忙|洗|吃|上|回|拿|接|开|办|处|补|收|看|打|冲|做|睡)\S*(?:\s*.+)?$",
        r"^我\s*要\s*(?:去|出|离|忙|洗|吃|上|回|拿|接|开|办|处|补|收|看|打|冲|做|睡)\S*(?:\s*.+)?$",
        r"^我\s*现在\s*(?:去|出|离|忙|洗|吃|上|回|拿|接|开|办|处|补|收|看|打|冲|做|睡)\S*(?:\s*.+)?$",
        r"^(?:等会|等会儿|一会|一会儿|回头)\s*(?:再来|回来)(?:\s*.+)?[。！!]*$",
        r"^(?:我\s*)?(?:先\s*)?(?:去|出|离|忙|洗|吃|上|回|拿|接|开|办|处|补|收|看|打|冲|做|睡)\S*(?:\s*.+)?了(?:\s*一下)?(?:吧)?[。！!]*$",
        r"^(?:我)?(?:暂时|先)离开(?:一下)?(?:吧)?[。！!]*$",
    ]

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._batch_task: asyncio.Task[None] | None = None

        self._away_by_session: dict[str, dict[str, AwayRecord]] = {}
        self._pending_by_session: dict[str, list[PendingTextMessage]] = {}
        self._latest_msg_id_by_session_sender: dict[str, dict[str, str]] = {}

    async def initialize(self) -> None:
        self._stop_event.clear()
        self._batch_task = asyncio.create_task(self._ai_batch_loop())
        logger.info("[counton] initialized")

    async def terminate(self) -> None:
        self._stop_event.set()
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        logger.info("[counton] terminated")

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return

        text = self._extract_plain_text(event)
        if not text:
            return

        session_key = event.unified_msg_origin
        sender_id = event.get_sender_id().strip()
        if not sender_id:
            return

        sender_name = event.get_sender_name().strip() or sender_id
        message_id = str(getattr(event.message_obj, "message_id", "") or "").strip()
        raw_ts = getattr(event.message_obj, "timestamp", 0)
        try:
            message_timestamp = float(raw_ts) if raw_ts else time.time()
        except (TypeError, ValueError):
            message_timestamp = time.time()

        should_flush_ai = False
        return_record: AwayRecord | None = None

        async with self._lock:
            self._touch_latest_message(session_key, sender_id, message_id)

            # Any next message from the same sender means they are back.
            away_map = self._away_by_session.get(session_key, {})
            if sender_id in away_map:
                return_record = away_map.pop(sender_id)
                return_record.return_message_id = message_id
                self._delete_temp_away_record(session_key, sender_id)

            if self._detect_mode() in {"ai", "both"}:
                pending = self._pending_by_session.setdefault(session_key, [])
                pending.append(
                    PendingTextMessage(
                        message_id=message_id,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        text=text,
                        received_at=time.time(),
                        message_timestamp=message_timestamp,
                    )
                )
                should_flush_ai = len(pending) >= self._ai_trigger_text_count()

        if return_record:
            yield self._build_welcome_result(return_record)
            return

        if self._detect_mode() in {"regex", "both"}:
            reason = self._extract_reason_by_regex(text)
            if reason:
                async with self._lock:
                    session_away = self._away_by_session.setdefault(session_key, {})
                    if sender_id not in session_away:
                        record = AwayRecord(
                            sender_id=sender_id,
                            sender_name=sender_name,
                            reason=reason,
                            leave_text=text,
                            leave_message_id=message_id,
                            leave_timestamp=message_timestamp,
                        )
                        session_away[sender_id] = record
                        self._save_temp_away_record(session_key, record)

        if should_flush_ai:
            await self._flush_ai_for_session(session_key)

    def _extract_plain_text(self, event: AstrMessageEvent) -> str:
        texts: list[str] = []
        for comp in event.get_messages():
            if isinstance(comp, Plain) and comp.text and comp.text.strip():
                texts.append(comp.text.strip())
        return " ".join(texts).strip()

    def _touch_latest_message(
        self, session_key: str, sender_id: str, message_id: str
    ) -> None:
        latest = self._latest_msg_id_by_session_sender.setdefault(session_key, {})
        latest[sender_id] = message_id or f"ts:{int(time.time() * 1000)}"

    def _detect_mode(self) -> str:
        mode = str(self._cfg("detect_mode", "both")).strip().lower()
        if mode in {"regex", "ai", "both"}:
            return mode
        return "both"

    def _cfg(self, key: str, default: Any) -> Any:
        if not self.config:
            return default
        return self.config.get(key, default)

    def _ai_trigger_text_count(self) -> int:
        try:
            value = int(self._cfg("ai_trigger_text_count", 15))
        except (TypeError, ValueError):
            value = 15
        return max(1, min(value, 200))

    def _ai_trigger_minutes(self) -> int:
        try:
            value = int(self._cfg("ai_trigger_minutes", 30))
        except (TypeError, ValueError):
            value = 30
        return max(1, min(value, 24 * 60))

    def _batch_loop_interval_seconds(self) -> int:
        try:
            value = int(self._cfg("batch_loop_interval_seconds", 5))
        except (TypeError, ValueError):
            value = 5
        return max(1, min(value, 120))

    def _compiled_patterns(self) -> list[re.Pattern[str]]:
        raw_patterns = self._cfg("regex_patterns", "")
        patterns: list[str] = []

        if isinstance(raw_patterns, str) and raw_patterns.strip():
            patterns = [
                line.strip() for line in raw_patterns.splitlines() if line.strip()
            ]

        if not patterns:
            patterns = self._DEFAULT_REGEX_PATTERNS

        compiled: list[re.Pattern[str]] = []
        for p in patterns:
            try:
                compiled.append(re.compile(p, re.IGNORECASE))
            except re.error as exc:
                logger.warning("[counton] invalid regex pattern %s: %s", p, exc)
        return compiled

    def _extract_reason_by_regex(self, text: str) -> str | None:
        target = text.strip()
        if not target:
            return None

        for pattern in self._compiled_patterns():
            if pattern.search(target):
                reason = self._guess_reason_from_text(target)
                return reason or "暂时离开"
        return None

    def _guess_reason_from_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", "", text)
        keywords = [
            "洗个澡",
            "洗澡",
            "厕所",
            "上厕所",
            "吃饭",
            "睡觉",
            "开会",
            "接电话",
            "拿快递",
            "出门",
            "忙一下",
        ]
        for keyword in keywords:
            if keyword in normalized:
                return keyword
        clipped = text.strip().strip("。！？!?,，")
        return clipped[:16] if clipped else "暂时离开"

    async def _ai_batch_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._batch_loop_interval_seconds())
                if self._detect_mode() not in {"ai", "both"}:
                    continue

                now = time.time()
                threshold_seconds = self._ai_trigger_minutes() * 60
                due_sessions: list[str] = []

                async with self._lock:
                    for session_key, messages in self._pending_by_session.items():
                        if not messages:
                            continue
                        first_ts = messages[0].received_at
                        if now - first_ts >= threshold_seconds:
                            due_sessions.append(session_key)

                for session_key in due_sessions:
                    await self._flush_ai_for_session(session_key)
        except asyncio.CancelledError:
            return

    async def _flush_ai_for_session(self, session_key: str) -> None:
        async with self._lock:
            pending = list(self._pending_by_session.get(session_key, []))
            if not pending:
                return
            self._pending_by_session[session_key] = []

        provider = self.context.get_using_provider(umo=session_key)
        if not provider or not isinstance(provider, Provider):
            logger.warning(
                "[counton] no chat provider for session %s, skip AI detection",
                session_key,
            )
            return

        identified = await self._detect_away_messages_with_ai(provider, pending)
        if not identified:
            return

        by_message_id = {msg.message_id: msg for msg in pending if msg.message_id}

        async with self._lock:
            latest_map = self._latest_msg_id_by_session_sender.setdefault(
                session_key, {}
            )
            away_map = self._away_by_session.setdefault(session_key, {})

            for item in identified:
                message_id = str(item.get("message_id", "")).strip()
                reason = str(item.get("reason", "")).strip()
                if not message_id:
                    continue

                msg = by_message_id.get(message_id)
                if not msg:
                    continue

                # Ignore stale candidates. If user has already sent a newer message,
                # the leave intent is no longer valid.
                if latest_map.get(msg.sender_id) != message_id:
                    continue

                if msg.sender_id in away_map:
                    continue

                record = AwayRecord(
                    sender_id=msg.sender_id,
                    sender_name=msg.sender_name,
                    reason=reason or self._guess_reason_from_text(msg.text),
                    leave_text=msg.text,
                    leave_message_id=msg.message_id,
                    leave_timestamp=msg.message_timestamp,
                )
                away_map[msg.sender_id] = record
                self._save_temp_away_record(session_key, record)

    async def _detect_away_messages_with_ai(
        self,
        provider: Provider,
        pending: list[PendingTextMessage],
    ) -> list[dict[str, str]]:
        lines = []
        for msg in pending:
            if not msg.message_id:
                continue
            lines.append(
                f"- message_id={msg.message_id}; sender={msg.sender_name}; text={msg.text}"
            )

        if not lines:
            return []

        prompt = (
            "你是一个群聊消息分类器。请从消息中识别“用户表达暂时离开，稍后回来”的消息。"
            "\n识别标准：例如“我去一趟厕所”“我要去吃饭”“我现在去洗个澡”“我先忙一下”“我先洗澡了”“等会再来”。"
            "\n不要把普通聊天、长期离开、告别、下线、睡觉到明天等消息当作暂时离开。"
            "\n\n请只输出 JSON，不要输出额外文字。格式："
            '{"aways":[{"message_id":"...","reason":"..."}]}'
            "\n其中 reason 是简短离开原因（如：洗澡、上厕所、接电话）。"
            "\n\n以下是待分类消息：\n" + "\n".join(lines)
        )

        try:
            response = await provider.text_chat(prompt=prompt)
            content = response.completion_text or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[counton] AI classify failed: %s", exc)
            return []

        data = self._try_parse_json(content)
        if not isinstance(data, dict):
            return []

        away_items = data.get("aways", [])
        if not isinstance(away_items, list):
            return []

        cleaned: list[dict[str, str]] = []
        for item in away_items:
            if not isinstance(item, dict):
                continue
            message_id = str(item.get("message_id", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if not message_id:
                continue
            cleaned.append({"message_id": message_id, "reason": reason})

        return cleaned

    def _try_parse_json(self, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    def _build_welcome_result(self, record: AwayRecord) -> MessageEventResult:
        duration = self._format_duration(
            max(0, int(time.time() - record.leave_timestamp))
        )
        text = f"欢迎回来，{record.sender_name}！你因为“{record.reason}”离开了 {duration}。"

        result = MessageEventResult()
        reply_target_id = ""
        quote_target = self._quote_target()
        if quote_target == "return":
            reply_target_id = record.return_message_id
        else:
            reply_target_id = record.leave_message_id

        if reply_target_id:
            result.chain.append(Reply(id=reply_target_id))
        result.message(text)
        return result

    def _quote_target(self) -> str:
        target = str(self._cfg("quote_target", "return")).strip().lower()
        if target in {"leave", "return"}:
            return target
        return "return"

    def _format_duration(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds} 秒"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes} 分 {sec} 秒"
        hours, mins = divmod(minutes, 60)
        return f"{hours} 小时 {mins} 分"

    def _get_temp_away_store(self) -> dict[str, dict[str, dict[str, str | float]]]:
        store = sp.temporary_cache.setdefault(self._TEMP_CACHE_KEY, {})
        if not isinstance(store, dict):
            store = {}
            sp.temporary_cache[self._TEMP_CACHE_KEY] = store
        return store

    def _save_temp_away_record(self, session_key: str, record: AwayRecord) -> None:
        session_store = self._get_temp_away_store().setdefault(session_key, {})
        session_store[record.sender_id] = {
            "sender_id": record.sender_id,
            "sender_name": record.sender_name,
            "reason": record.reason,
            "leave_text": record.leave_text,
            "leave_message_id": record.leave_message_id,
            "leave_timestamp": record.leave_timestamp,
        }

    def _delete_temp_away_record(self, session_key: str, sender_id: str) -> None:
        store = self._get_temp_away_store()
        session_store = store.get(session_key)
        if not isinstance(session_store, dict):
            return

        session_store.pop(sender_id, None)
        if not session_store:
            store.pop(session_key, None)

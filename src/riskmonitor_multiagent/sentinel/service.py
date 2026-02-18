"""Sentinel Service

负责监听 Kafka 事件流 做实时阈值检测 并触发后续告警流程
目前作为 Level 2 The Reflexes 的轻量级实现
"""

import asyncio
import base64
import json
import logging
import signal
import time

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import TopicPartition

from riskmonitor_multiagent import config
from riskmonitor_multiagent.agents import run_agent_pipeline
from riskmonitor_multiagent.contracts.risk_event import build_breach_event, normalize_cdc_event
from riskmonitor_multiagent.data_access import idempotency_repository
from riskmonitor_multiagent.data_access import dlq_repository
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms, set_gauge
from riskmonitor_multiagent.orchestration import run_state_machine

logger = logging.getLogger(__name__)

# 临时硬编码阈值 后续应从 config 或 resource 获取
MAX_EXPOSURE_THRESHOLD = 50000.0


class SentinelService:
    """Sentinel 哨兵服务"""

    def __init__(self):
        self._running = False
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: AIOKafkaProducer | None = None
        self._last_lag_update_ms: int = 0
        self._cached_end_offsets: dict[tuple[str, int], int] = {}

    async def start(self):
        """启动服务"""
        self._running = True
        bootstrap_servers = config.get_kafka_bootstrap_servers()
        topic = config.get_kafka_topic_cdc_positions()

        logger.info(f"Starting Sentinel Service, connecting to {bootstrap_servers}, topic={topic}")

        # 重试连接
        while self._running:
            try:
                self._consumer = AIOKafkaConsumer(
                    topic,
                    bootstrap_servers=bootstrap_servers,
                    group_id="risk-sentinel-group-v1",
                    auto_offset_reset="latest",
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                )
                await self._consumer.start()
                break
            except Exception as e:
                logger.warning(f"Failed to connect to Kafka, retrying in 5s: {e}")
                await asyncio.sleep(5)

        logger.info("Sentinel Service started, listening for events...")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                await self._process_message(msg)
        except Exception as e:
            if self._running:
                logger.error(f"Error in Sentinel loop: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """停止服务"""
        logger.info("Stopping Sentinel Service...")
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._dlq_producer:
            await self._dlq_producer.stop()
        logger.info("Sentinel Service stopped.")

    async def _ensure_dlq_producer(self) -> AIOKafkaProducer:
        if self._dlq_producer is not None:
            return self._dlq_producer
        producer = AIOKafkaProducer(
            bootstrap_servers=config.get_kafka_bootstrap_servers(),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            key_serializer=lambda v: (v.encode("utf-8") if isinstance(v, str) else None),
        )
        await producer.start()
        self._dlq_producer = producer
        return producer

    async def _send_to_dlq(self, *, topic: str, partition: int, offset: int, event_id: str, payload: dict, error: BaseException, attempts: int) -> None:
        try:
            dlq_repository.save_dlq_event(
                topic=topic,
                partition=partition,
                offset=offset,
                event_id=event_id,
                error_code=type(error).__name__,
                error_message=str(error),
                payload=payload,
                attempts=int(attempts),
            )
        except Exception:
            inc_counter("rm_sentinel_dlq_db_errors_total")
        if not config.get_sentinel_dlq_enabled():
            return
        try:
            producer = await self._ensure_dlq_producer()
            await producer.send_and_wait(
                config.get_kafka_topic_dlq(),
                key=str(event_id),
                value={
                    "schema_version": "dlq_event.v1",
                    "topic": topic,
                    "partition": int(partition),
                    "offset": int(offset),
                    "event_id": str(event_id),
                    "attempts": int(attempts),
                    "error": {"code": type(error).__name__, "message": str(error)},
                    "payload": payload,
                },
            )
            inc_counter("rm_sentinel_dlq_published_total")
        except Exception:
            inc_counter("rm_sentinel_dlq_publish_errors_total")

    async def _process_message(self, msg):
        """处理单条消息"""
        started = time.monotonic()
        try:
            value = msg.value
            if not value:
                return
                
            payload = value.get("payload")
            schema = value.get("schema")

            if schema is not None and payload and isinstance(payload, dict):
                record = payload
                op = payload.get("__op") or payload.get("op")
            elif payload and isinstance(payload, dict):
                if "after" in payload or "before" in payload:
                    record = payload.get("after")
                    op = payload.get("op")
                else:
                    record = payload
                    op = payload.get("__op") or payload.get("op")
            else:
                record = value
                op = value.get("__op") or value.get("op")

            if not record or not isinstance(record, dict):
                return

            topic = getattr(msg, "topic", "unknown")
            partition = getattr(msg, "partition", 0)
            offset = getattr(msg, "offset", 0)
            message_ts_ms = getattr(msg, "timestamp", None)
            if not isinstance(message_ts_ms, int):
                message_ts_ms = None

            await self._update_consumer_lag_metrics(topic=str(topic), partition=int(partition), offset=int(offset))

            desk = record.get("desk")
            # Debezium payload value 可能是 string 或 number 这里统一转 float 并兼容 connect decimal
            exposure_val = record.get("delta") or record.get("exposure", 0.0)
            if exposure_val is None:
                exposure = 0.0
            else:
                try:
                    exposure = float(exposure_val)
                except Exception:
                    exposure = self._try_decode_connect_decimal(exposure_val) or 0.0

            logger.info(f"Received event op={op}, desk={desk}, exposure={exposure}")

            source_event = normalize_cdc_event(
                raw_record=record,
                topic=str(topic),
                partition=int(partition),
                offset=int(offset),
                message_ts_ms=message_ts_ms,
            )

            try:
                decision = idempotency_repository.try_begin_processing(
                    topic=str(topic),
                    partition=int(partition),
                    offset=int(offset),
                    event_id=source_event.event_id,
                )
                if decision.decision != "process":
                    inc_counter("rm_sentinel_dedup_skipped_total", labels={"decision": decision.decision})
                    return
            except Exception:
                inc_counter("rm_sentinel_dedup_unavailable_total")

            max_attempts = max(1, int(config.get_sentinel_retry_max()))
            backoff_s = max(0.0, float(config.get_sentinel_retry_backoff_s()))
            for attempt in range(1, max_attempts + 1):
                try:
                    if abs(exposure) > MAX_EXPOSURE_THRESHOLD:
                        inc_counter("rm_sentinel_breaches_total")
                        breach_event = build_breach_event(
                            source_event=source_event,
                            desk=str(desk) if isinstance(desk, str) else "unknown",
                            exposure=float(exposure),
                            threshold=float(MAX_EXPOSURE_THRESHOLD),
                        )
                        await self._trigger_alert(event=breach_event.to_dict())
                    try:
                        idempotency_repository.mark_done(topic=str(topic), partition=int(partition), offset=int(offset))
                    except Exception:
                        inc_counter("rm_sentinel_dedup_mark_done_errors_total")
                    return
                except Exception as e:
                    inc_counter("rm_sentinel_retries_total", labels={"attempt": str(attempt)})
                    if attempt < max_attempts:
                        await asyncio.sleep(backoff_s * (2 ** (attempt - 1)))
                        continue
                    try:
                        idempotency_repository.mark_failed(
                            topic=str(topic),
                            partition=int(partition),
                            offset=int(offset),
                            error_message=str(e),
                        )
                    except Exception:
                        inc_counter("rm_sentinel_dedup_mark_failed_errors_total")
                    await self._send_to_dlq(
                        topic=str(topic),
                        partition=int(partition),
                        offset=int(offset),
                        event_id=source_event.event_id,
                        payload=value if isinstance(value, dict) else {"value": value},
                        error=e,
                        attempts=attempt,
                    )
                    raise

        except Exception as e:
            inc_counter("rm_sentinel_errors_total")
            logger.error(f"Failed to process message: {e}", exc_info=True)
        finally:
            inc_counter("rm_sentinel_messages_total")
            observe_ms("rm_sentinel_process_message", (time.monotonic() - started) * 1000.0)

    async def _trigger_alert(self, *, event: dict):
        """触发告警"""
        started = time.monotonic()
        desk = event.get("payload", {}).get("desk") if isinstance(event.get("payload"), dict) else None
        exposure = event.get("payload", {}).get("exposure") if isinstance(event.get("payload"), dict) else None
        logger.warning(
            f"⚠️ [BREACH DETECTED] desk={desk} exposure={exposure} limit={MAX_EXPOSURE_THRESHOLD}"
        )
        state_machine = await run_state_machine(event=event)
        if state_machine.get("ok") is True:
            result = state_machine.get("result") or {}
            manager = result.get("manager") if isinstance(result, dict) else None
            decision = manager.get("decision") if isinstance(manager, dict) else None
            action = manager.get("action") if isinstance(manager, dict) else None
            logger.warning(f"StateMachine decision={decision}, action={action}")
            observe_ms("rm_sentinel_trigger_alert", (time.monotonic() - started) * 1000.0, labels={"path": "state_machine"})
            return

        result = await run_agent_pipeline(event=event)
        if result.get("blocked"):
            logger.warning(f"Pipeline blocked: {result.get('engineer')}")
            return
        manager = result.get("manager") or {}
        decision = manager.get("decision")
        action = manager.get("action")
        logger.warning(f"Pipeline decision={decision}, action={action}")
        observe_ms("rm_sentinel_trigger_alert", (time.monotonic() - started) * 1000.0, labels={"path": "pipeline"})

    async def _update_consumer_lag_metrics(self, *, topic: str, partition: int, offset: int) -> None:
        if self._consumer is None:
            return
        now_ms = int(time.time() * 1000)
        if now_ms - int(self._last_lag_update_ms) < 1000:
            end = self._cached_end_offsets.get((topic, partition))
            if isinstance(end, int):
                lag = max(0, int(end) - int(offset) - 1)
                set_gauge("rm_kafka_consumer_lag", float(lag), labels={"topic": topic, "partition": str(partition)})
            return

        self._last_lag_update_ms = now_ms
        try:
            tp = TopicPartition(topic, partition)
            ends = await self._consumer.end_offsets([tp])
            end = ends.get(tp)
            if isinstance(end, int):
                self._cached_end_offsets[(topic, partition)] = int(end)
                lag = max(0, int(end) - int(offset) - 1)
                set_gauge("rm_kafka_consumer_lag", float(lag), labels={"topic": topic, "partition": str(partition)})
        except Exception:
            inc_counter("rm_sentinel_kafka_lag_errors_total")

    def _try_decode_connect_decimal(self, value) -> float | None:
        if not isinstance(value, str):
            return None
        if not value or value.strip() != value:
            return None
        try:
            raw = base64.b64decode(value)
            unscaled = int.from_bytes(raw, byteorder="big", signed=True)
            return float(unscaled) / 10000.0
        except Exception:
            return None


async def run_sentinel():
    """入口函数"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    service = SentinelService()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    # 注册信号处理
    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal)
        loop.add_signal_handler(signal.SIGTERM, handle_signal)
    except NotImplementedError:
        pass

    server_task = asyncio.create_task(service.start())
    
    # 等待信号
    await stop_event.wait()
    
    # 优雅停止
    await service.stop()
    try:
        await server_task
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(run_sentinel())
    except KeyboardInterrupt:
        pass

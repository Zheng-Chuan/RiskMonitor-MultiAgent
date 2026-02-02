"""Sentinel Service.

负责监听 Kafka 事件流, 进行实时简单的阈值检测, 并触发后续告警流程.
目前作为 "Level 2: The Reflexes" 的轻量级实现.
"""

import asyncio
import base64
import json
import logging
import signal

from aiokafka import AIOKafkaConsumer

from riskmonitor_multiagent import config
from riskmonitor_multiagent.agents import run_agent_pipeline

logger = logging.getLogger(__name__)

# 临时硬编码的阈值, 后续应该从 config 或 Resource 获取
MAX_EXPOSURE_THRESHOLD = 50000.0


class SentinelService:
    """Sentinel 哨兵服务."""

    def __init__(self):
        self._running = False
        self._consumer = None

    async def start(self):
        """启动服务."""
        self._running = True
        bootstrap_servers = config.get_kafka_bootstrap_servers()
        topic = config.get_kafka_topic_cdc_positions()

        logger.info(f"Starting Sentinel Service, connecting to {bootstrap_servers}, topic={topic}")

        # 重试连接逻辑
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
        """停止服务."""
        logger.info("Stopping Sentinel Service...")
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("Sentinel Service stopped.")

    async def _process_message(self, msg):
        """处理单条消息."""
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

            desk = record.get("desk")
            # 注意: Debezium 传过来的可能是 string 或 number, 视 schema 而定, 这里强转 float
            # 兼容 MySQL Decimal 类型传过来可能是 string
            # 在我们的表中, delta 对应敞口, exposure 可能是旧字段或别名
            exposure_val = record.get("delta") or record.get("exposure", 0.0)
            if exposure_val is None:
                exposure = 0.0
            else:
                try:
                    exposure = float(exposure_val)
                except Exception:
                    exposure = self._try_decode_connect_decimal(exposure_val) or 0.0

            logger.info(f"Received event op={op}, desk={desk}, exposure={exposure}")

            # 简单的阈值检测 (Breach Detection)
            if abs(exposure) > MAX_EXPOSURE_THRESHOLD:
                await self._trigger_alert(desk=desk, exposure=exposure, record=record)

        except Exception as e:
            logger.error(f"Failed to process message: {e}", exc_info=True)

    async def _trigger_alert(self, *, desk: str, exposure: float, record: dict):
        """触发告警."""
        logger.warning(
            f"⚠️ [BREACH DETECTED] Desk '{desk}' exposure {exposure} exceeds limit {MAX_EXPOSURE_THRESHOLD}!"
        )
        event = dict(record)
        event["desk"] = desk
        event["exposure"] = exposure
        result = await run_agent_pipeline(event=event)
        if result.get("blocked"):
            logger.warning(f"Pipeline blocked: {result.get('engineer')}")
            return
        manager = result.get("manager") or {}
        decision = manager.get("decision")
        action = manager.get("action")
        logger.warning(f"Pipeline decision={decision}, action={action}")

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
    """入口函数."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    service = SentinelService()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    # 注册信号处理 (兼容 Windows 非交互式环境需注意, 但这里是 macos)
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

"""
Eureka Service Discovery Client
Registers this FastAPI service with a Eureka server for discovery
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EurekaClient:
    def __init__(self):
        self.eureka_url = settings.get_eureka_url().rstrip("/")
        self.app_name = "gateway-service"
        # Use host:port as instance id similar to Spring
        self.instance_id = f"{self.app_name}:{settings.get_server_host()}:{settings.get_server_port()}"
        self.registered = False
        self._heartbeat_task: asyncio.Task | None = None

    def _now_ms(self) -> int:
        return int(datetime.now().timestamp() * 1000)

    def _instance_info(self) -> Dict[str, Any]:
        now = self._now_ms()
        return {
            "instance": {
                "instanceId": self.instance_id,
                "hostName": settings.get_server_host(),
                "app": self.app_name.upper(),
                "ipAddr": settings.get_server_host(),
                "status": "UP",
                "overriddenstatus": "UNKNOWN",
                "port": {"$": settings.get_server_port(), "@enabled": "true"},
                "securePort": {"$": 443, "@enabled": "false"},
                "countryId": 1,
                "dataCenterInfo": {
                    "@class": "com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo",
                    "name": "MyOwn",
                },
                "leaseInfo": {
                    "renewalIntervalInSecs": settings.get_eureka_heartbeat_interval(),
                    "durationInSecs": settings.get_eureka_heartbeat_interval() * 3,
                    "registrationTimestamp": now,
                    "lastRenewalTimestamp": now,
                    "evictionTimestamp": 0,
                    "serviceUpTimestamp": now,
                },
                "metadata": {
                    "management.port": str(settings.get_server_port()),
                },
                "homePageUrl": f"http://{settings.get_server_host()}:{settings.get_server_port()}/",
                "statusPageUrl": f"http://{settings.get_server_host()}:{settings.get_server_port()}",
                "healthCheckUrl": f"http://{settings.get_server_host()}:{settings.get_server_port()}/health",
                "vipAddress": self.app_name,
                "secureVipAddress": self.app_name,
                "isCoordinatingDiscoveryServer": "false",
                "lastUpdatedTimestamp": now,
                "lastDirtyTimestamp": now,
                "actionType": "ADDED",
            }
        }

    async def register(self) -> bool:
        try:
            payload = self._instance_info()

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.eureka_url}/apps/{self.app_name.upper()}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )

            if resp.status_code in (200, 204):
                self.registered = True
                logger.info(
                    "Registered '%s' with Eureka at %s",
                    self.app_name,
                    self.eureka_url,
                )
                return True
            else:
                logger.error(
                    "Eureka registration failed: %s %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception as exc:
            logger.error("Eureka register error: %s", exc)
            return False

    async def send_heartbeat(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    f"{self.eureka_url}/apps/{self.app_name.upper()}/{self.instance_id}",
                    timeout=5.0,
                )
            if resp.status_code == 200:
                logger.debug("Eureka heartbeat OK for %s", self.instance_id)
                return True
            logger.warning("Eureka heartbeat failed: %s", resp.status_code)
            return False
        except Exception as exc:
            logger.warning("Eureka heartbeat error: %s", exc)
            return False

    async def deregister(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.eureka_url}/apps/{self.app_name.upper()}/{self.instance_id}",
                    timeout=10.0,
                )
            if resp.status_code in (200, 202):
                self.registered = False
                logger.info("Deregistered '%s' from Eureka", self.instance_id)
                return True
            logger.error("Eureka deregister failed: %s", resp.status_code)
            return False
        except Exception as exc:
            logger.error("Eureka deregister error: %s", exc)
            return False

    async def start_heartbeat_loop(self):
        async def loop():
            while self.registered:
                ok = await self.send_heartbeat()
                if not ok:
                    # try re-registering
                    await self.register()
                await asyncio.sleep(settings.get_eureka_heartbeat_interval())

        if self.registered and not self._heartbeat_task:
            self._heartbeat_task = asyncio.create_task(loop())

    async def get_service_instances(self, service_name: str) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.eureka_url}/apps/{service_name.upper()}",
                    headers={"Accept": "application/json"},
                    timeout=5.0,
                )
            if resp.status_code == 200:
                data = resp.json()
                inst = data.get("application", {}).get("instance", [])
                if isinstance(inst, dict):
                    return [inst]
                return inst
            return []
        except Exception as exc:
            logger.error("Eureka get instances error: %s", exc)
            return []


eureka_client = EurekaClient()

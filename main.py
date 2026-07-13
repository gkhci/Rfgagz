import json
import base64
import hashlib
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from pathlib import Path
from io import BytesIO
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

import qrcode
import aiofiles
from cryptography.fernet import Fernet
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# =========================
#   CONFIGURATION
# =========================
TOKEN = "8793482183:AAEGUa7ZEURP26N34DzKvrudnndC3q7apBk"
ADMIN_IDS = [8680457924]  # آیدی عددی ادمین‌ها

# =========================
#   LOGGING
# =========================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
#   DATA CLASSES
# =========================
@dataclass
class Inbound:
    id: str
    remark: str
    host: str
    port: str
    uuid: str
    protocol: str  # vless, vmess, trojan, shadowsocks
    security: str  # reality, tls, none
    network: str   # tcp, ws, grpc
    flow: str = "xtls-rprx-vision"
    created_at: str = ""
    expire_date: str = ""
    traffic_limit: int = 0
    used_traffic: int = 0
    status: str = "active"
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

@dataclass
class User:
    id: str
    username: str
    first_name: str
    last_name: str = ""
    inbounds: List[str] = None
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.inbounds is None:
            self.inbounds = []

# =========================
#   ADVANCED STORAGE
# =========================
class UltraStorage:
    def __init__(self):
        self.db_path = Path("ultra_panel_db")
        self.db_path.mkdir(exist_ok=True)
        self._cache = {}
        self._lock = asyncio.Lock()
        
    async def _read_json(self, filename: str) -> List[Dict]:
        file_path = self.db_path / filename
        if not file_path.exists():
            return []
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = await f.read()
                return json.loads(data) if data else []
            except:
                return []
    
    async def _write_json(self, filename: str, data: List[Dict]):
        file_path = self.db_path / filename
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    async def get_inbounds(self) -> List[Inbound]:
        async with self._lock:
            data = await self._read_json("inbounds.json")
            return [Inbound(**item) for item in data]
    
    async def save_inbounds(self, inbounds: List[Inbound]):
        async with self._lock:
            data = [asdict(inb) for inb in inbounds]
            await self._write_json("inbounds.json", data)
    
    async def get_users(self) -> List[User]:
        async with self._lock:
            data = await self._read_json("users.json")
            return [User(**item) for item in data]
    
    async def save_users(self, users: List[User]):
        async with self._lock:
            data = [asdict(user) for user in users]
            await self._write_json("users.json", data)
    
    async def add_inbound(self, inbound: Inbound):
        inbounds = await self.get_inbounds()
        inbounds.append(inbound)
        await self.save_inbounds(inbounds)
    
    async def delete_inbound(self, inbound_id: str):
        inbounds = await self.get_inbounds()
        inbounds = [i for i in inbounds if i.id != inbound_id]
        await self.save_inbounds(inbounds)
    
    async def find_inbound(self, inbound_id: str) -> Optional[Inbound]:
        inbounds = await self.get_inbounds()
        for i in inbounds:
            if i.id == inbound_id:
                return i
        return None
    
    async def update_inbound(self, inbound: Inbound):
        inbounds = await self.get_inbounds()
        for i, existing in enumerate(inbounds):
            if existing.id == inbound.id:
                inbounds[i] = inbound
                break
        await self.save_inbounds(inbounds)

# =========================
#   ADVANCED CONFIG BUILDER
# =========================
class ConfigBuilder:
    @staticmethod
    def build_vless_reality(inb: Inbound) -> str:
        return (
            f"vless://{inb.uuid}@{inb.host}:{inb.port}"
            f"?security=reality&fp=chrome&encryption=none"
            f"&flow={inb.flow}&sni={inb.host}"
            f"&pbk=FPJS6JcS9lUv3-hJz0M_N2qZ_BE4vEUPfYWkVy1N1lU"
            f"&sid=6ba85179e30d4fc2"
            f"#REZA_GROOTZ_{inb.remark}"
        )
    
    @staticmethod
    def build_vless_tls(inb: Inbound) -> str:
        return (
            f"vless://{inb.uuid}@{inb.host}:{inb.port}"
            f"?security=tls&fp=chrome&encryption=none"
            f"&flow={inb.flow}"
            f"#REZA_GROOTZ_{inb.remark}"
        )
    
    @staticmethod
    def build_trojan(inb: Inbound) -> str:
        return (
            f"trojan://{inb.uuid}@{inb.host}:{inb.port}"
            f"?security=tls&sni={inb.host}"
            f"#REZA_GROOTZ_{inb.remark}"
        )
    
    @staticmethod
    def build_vmess(inb: Inbound) -> str:
        vmess = {
            "v": "2",
            "ps": f"REZA_GROOTZ_{inb.remark}",
            "add": inb.host,
            "port": inb.port,
            "id": inb.uuid,
            "aid": "0",
            "net": inb.network,
            "type": "none",
            "tls": "tls" if inb.security == "tls" else "",
            "sni": inb.host
        }
        raw = json.dumps(vmess, separators=(',', ':'))
        return "vmess://" + base64.b64encode(raw.encode()).decode()
    
    @staticmethod
    def build_shadowsocks(inb: Inbound) -> str:
        import hashlib
        key = hashlib.md5(inb.uuid.encode()).hexdigest()[:16]
        return (
            f"ss://{base64.b64encode(f'chacha20-ietf-poly1305:{key}'.encode()).decode()}"
            f"@{inb.host}:{inb.port}#REZA_GROOTZ_{inb.remark}"
        )
    
    @staticmethod
    def build_all_configs(inb: Inbound) -> Dict[str, str]:
        configs = {}
        if inb.protocol == "vless":
            configs["vless_reality"] = ConfigBuilder.build_vless_reality(inb)
            configs["vless_tls"] = ConfigBuilder.build_vless_tls(inb)
        elif inb.protocol == "trojan":
            configs["trojan"] = ConfigBuilder.build_trojan(inb)
        elif inb.protocol == "vmess":
            configs["vmess"] = ConfigBuilder.build_vmess(inb)
        elif inb.protocol == "shadowsocks":
            configs["shadowsocks"] = ConfigBuilder.build_shadowsocks(inb)
        return configs
    
    @staticmethod
    def generate_subscription(inb: Inbound) -> str:
        """ساخت لینک سابسکریپشن"""
        configs = ConfigBuilder.build_all_configs(inb)
        config_text = "\n".join(configs.values())
        return base64.b64encode(config_text.encode()).decode()
    
    @staticmethod
    def generate_qr(text: str) -> BytesIO:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)
        return bio

# =========================
#   ANALYTICS & STATISTICS
# =========================
class Analytics:
    @staticmethod
    async def get_stats(inbounds: List[Inbound]) -> Dict:
        total = len(inbounds)
        active = sum(1 for i in inbounds if i.status == "active")
        total_usage = sum(i.used_traffic for i in inbounds)
        
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "total_usage_gb": round(total_usage / (1024**3), 2),
            "protocols": {
                "vless": sum(1 for i in inbounds if i.protocol == "vless"),
                "vmess": sum(1 for i in inbounds if i.protocol == "vmess"),
                "trojan": sum(1 for i in inbounds if i.protocol == "trojan"),
                "shadowsocks": sum(1 for i in inbounds if i.protocol == "shadowsocks")
            }
        }

# =========================
#   SECURITY
# =========================
class SecurityManager:
    def __init__(self):
        self.key = Fernet.generate_key()
        self.cipher = Fernet(self.key)
    
    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, data: str) -> str:
        return self.cipher.decrypt(data.encode()).decode()
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS

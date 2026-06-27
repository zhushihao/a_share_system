import os
from pathlib import Path
import logging

import logging.handlers

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "backend"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 日志目录
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志（带轮转：单文件10MB，保留3个备份）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "backend.log", maxBytes=10*1024*1024, backupCount=3, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("quant_workbench")

class Settings:
    """应用配置"""
    APP_NAME: str = "Quant Workbench"
    VERSION: str = "1.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = 5889  # 新后端端口，避免与旧 Flask (5888) 冲突
    
    # 数据库
    DATABASE_URL: str = f"sqlite:///{DATA_DIR}/quant_workbench.db"
    
    # 数据源
    TDX_DIR: str = "D:/TDX"
    
    # CORS
    CORS_ORIGINS: list = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5889"]
    
    # AI 投研（预留，用户自行配置 Key）
    AI_API_KEY: str = os.getenv("KIMI_API_KEY", "")
    AI_MODEL: str = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
    AI_BASE_URL: str = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    
    # 缓存
    CACHE_TTL: int = 300

settings = Settings()

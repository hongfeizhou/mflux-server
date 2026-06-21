import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(base_dir) -> str:
    """配置写入 <base_dir>/logs/mflux-server.log 的滚动日志，返回日志文件路径。"""
    log_dir = Path(base_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mflux-server.log"

    handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FMT))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    already = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file)
        for h in root.handlers
    )
    if not already:
        root.addHandler(handler)
        # 让 uvicorn 的请求/错误日志也落到同一个文件
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            lg = logging.getLogger(name)
            lg.addHandler(handler)
            lg.propagate = False
    return str(log_file)

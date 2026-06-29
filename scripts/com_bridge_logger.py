#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COM4 串口桥接 + 流量记录器

用法：
  1. 用 com0com 创建虚拟串口对，例如 COM10 <-> COM11。
  2. 让 samamagic 连接 COM10（或通过重命名让 samamagic 以为自己在用 COM4）。
  3. 运行：python scripts/com_bridge_logger.py COM11 COM4
  4. 在 samamagic 里执行“停止 → 重新上传图片 → 开机”。
  5. 按 Ctrl+C 结束，日志保存在 captures/ 目录。
"""

import os
import sys
import time
import queue
import threading
from datetime import datetime
from pathlib import Path

import serial


def log_packet(f, direction: str, data: bytes) -> None:
    """按原始字节 + 简单协议解析记录一个数据包。"""
    ts = datetime.now().isoformat(timespec="milliseconds")
    if len(data) >= 10 and data[1] == 0xEF and data[2] == 0x69:
        cmd = data[0]
        length = int.from_bytes(data[3:7], "big")
        idx = data[7]
        payload = data[10:]
        f.write(
            f"{ts} {direction} CMD={cmd} LEN={length} IDX={idx} PL={len(payload)} "
            f"hex={data.hex()}\n"
        )
    else:
        f.write(f"{ts} {direction} RAW len={len(data)} hex={data.hex()}\n")
    f.flush()


def forward(src: serial.Serial, dst: serial.Serial, direction: str, log_queue: queue.Queue) -> None:
    """把 src 收到的数据转发到 dst，并推入日志队列。"""
    try:
        while True:
            data = src.read(max(1, src.in_waiting))
            if data:
                dst.write(data)
                log_queue.put((direction, data))
            else:
                time.sleep(0.001)
    except serial.SerialException:
        pass
    except OSError:
        pass


def main() -> None:
    if len(sys.argv) >= 3:
        virtual_port, real_port = sys.argv[1], sys.argv[2]
    else:
        virtual_port = input("samamagic 连接的虚拟端口（如 COM10/COM11）: ").strip()
        real_port = input("真实屏幕端口（如 COM4）: ").strip()

    capture_dir = Path(__file__).resolve().parent.parent / "captures"
    capture_dir.mkdir(exist_ok=True)
    log_path = capture_dir / f"com_bridge_{datetime.now():%Y%m%d_%H%M%S}.txt"

    print(f"虚拟端口: {virtual_port}")
    print(f"真实端口: {real_port}")
    print(f"日志文件: {log_path}")
    print("按 Ctrl+C 停止。\n")

    ser_virtual = serial.Serial(
        virtual_port,
        115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0,
        write_timeout=2,
    )
    ser_real = serial.Serial(
        real_port,
        115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0,
        write_timeout=2,
    )

    log_queue: queue.Queue = queue.Queue()

    t1 = threading.Thread(
        target=forward, args=(ser_virtual, ser_real, "V->R", log_queue), daemon=True
    )
    t2 = threading.Thread(
        target=forward, args=(ser_real, ser_virtual, "R->V", log_queue), daemon=True
    )
    t1.start()
    t2.start()

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# Bridge {virtual_port} <-> {real_port} started at {datetime.now()}\n")
            while True:
                try:
                    direction, data = log_queue.get(timeout=0.1)
                    log_packet(f, direction, data)
                except queue.Empty:
                    continue
    except KeyboardInterrupt:
        print("\n停止记录...")
    finally:
        ser_virtual.close()
        ser_real.close()
        print(f"日志已保存: {log_path}")


if __name__ == "__main__":
    main()

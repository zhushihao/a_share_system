#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAMA 小显示屏 Claude 工作状态指示灯控制脚本

通过串口向 SAMA 小显示屏发送右上角一个状态灯：
  red    = 需要操作
  yellow = 工作中
  green  = 工作结束
  off    = 熄灭（把灯区域置黑）

协议（来自 samamagic.exe 反编译）：
  - 串口：COM4，115200/8/N/1，DTR=RTS=True
  - 命令包（250 字节）：
      byte 0:     command
      byte 1-2:   0xEF 0x69（magic）
      byte 3-6:   数据长度（大端 32 位）
      byte 7:     包序号/索引
      byte 8-9:   保留
      byte 10+:   payload（命令包最多 240 字节）
  - 图片绘制命令 201：将 Bitmap 中非透明像素以稀疏列表形式发送到屏幕。
    编码规则（来自反编译的 ꠄ.ꃬ(Bitmap, int, out int, int)）：
      每个像素 6 字节：
        byte 0-2: 像素索引（x + y*width），大端 24 位
        byte 3:   (B & 0xFC) | ((A>>4) >> 2)
        byte 4:   (G & 0xFC) | ((A>>4) & 0x3)
        byte 5:   R
    命令头 length = 6 * 非透明像素数，随后发送编码数据（249 字节/包）。
  - 像素格式：BGRA（与 GDI+ Format32bppArgb 一致），行主序。
"""

import argparse
import sys
import time
from typing import Optional

import serial

COM_PORT = "COM4"
BAUDRATE = 115200
PACKET_SIZE = 250          # 命令包总长度
DATA_CHUNK_SIZE = 249      # 数据包每包实际载荷（来自反编译代码 global::굖.ꠄ）
SCREEN_WIDTH = 720
SCREEN_HEIGHT = 1586
BPP = 4

# BGRA 颜色（alpha=255 表示不透明）
COLORS = {
    "red": (0, 0, 255, 255),
    "yellow": (0, 255, 255, 255),
    "green": (0, 255, 0, 255),
    "off": (0, 0, 0, 255),
}


def build_command_packet(command: int, length: int, data: Optional[bytes] = None, index: int = 0) -> bytes:
    """构造 250 字节命令包。"""
    packet = bytearray(PACKET_SIZE)
    packet[0] = command
    packet[1] = 0xEF
    packet[2] = 0x69
    packet[3] = (length >> 24) & 0xFF
    packet[4] = (length >> 16) & 0xFF
    packet[5] = (length >> 8) & 0xFF
    packet[6] = length & 0xFF
    packet[7] = index
    if data:
        packet[10:10 + len(data)] = data
    return bytes(packet)


def send_raw_data(ser: serial.Serial, data: bytes, chunk_size: int = DATA_CHUNK_SIZE) -> None:
    """将原始数据按 249 字节/250 字节包的方式发出。"""
    total = len(data)
    pos = 0
    while pos < total:
        end = min(pos + chunk_size, total)
        chunk = data[pos:end]
        # 每包固定 250 字节，不足补 0
        packet = chunk.ljust(PACKET_SIZE, b"\x00")
        ser.write(packet)
        pos = end


def draw_circle(
    buf: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color_bgra: tuple,
) -> None:
    """在 BGRA 缓冲区上绘制一个实心圆。"""
    b, g, r, a = color_bgra
    y0 = max(0, cy - radius)
    y1 = min(height - 1, cy + radius)
    x0 = max(0, cx - radius)
    x1 = min(width - 1, cx + radius)
    r2 = radius * radius
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            if dx * dx + dy * dy <= r2:
                idx = (y * width + x) * BPP
                buf[idx] = b
                buf[idx + 1] = g
                buf[idx + 2] = r
                buf[idx + 3] = a


def encode_pixels_bgra(buf: bytes, width: int, height: int) -> bytes:
    """将 BGRA 缓冲区编码为 command 201 所需的稀疏像素列表。"""
    assert len(buf) == width * height * BPP
    encoded = bytearray()
    for y in range(height):
        base = y * width
        for x in range(width):
            idx = (base + x) * BPP
            a = buf[idx + 3]
            if a == 0:
                continue
            b = buf[idx]
            g = buf[idx + 1]
            r = buf[idx + 2]
            pixel_index = base + x
            a4 = a >> 4
            encoded.append((pixel_index >> 16) & 0xFF)
            encoded.append((pixel_index >> 8) & 0xFF)
            encoded.append(pixel_index & 0xFF)
            encoded.append((b & 0xFC) | ((a4 >> 2) & 0x03))
            encoded.append((g & 0xFC) | (a4 & 0x03))
            encoded.append(r)
    return bytes(encoded)


def create_status_image(status: str) -> bytes:
    """生成 720x1586 BGRA 全屏图像，右上角显示状态灯。"""
    width, height = SCREEN_WIDTH, SCREEN_HEIGHT
    buf = bytearray(width * height * BPP)  # 默认全透明（背景不变）

    color = COLORS.get(status, COLORS["off"])
    radius = 60
    cx = width - radius - 40
    cy = radius + 40
    draw_circle(buf, width, height, cx, cy, radius, color)

    return bytes(buf)


def send_status(status: str, port: str = COM_PORT, baudrate: int = BAUDRATE) -> None:
    """打开串口，握手，然后发送状态灯图像。"""
    print(f"打开串口 {port} @ {baudrate}...")
    with serial.Serial(
        port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2,
        write_timeout=5,
    ) as ser:
        ser.dtr = True
        ser.rts = True
        print("串口已打开")

        # 0) 进入图像/刷新模式（command 150，来自 samamagic 连接流程）
        print("发送 command 150 进入图像模式...")
        ser.write(build_command_packet(150, 1, None, 0))
        time.sleep(0.2)

        # 1) 初始化握手（command 1）
        print("发送初始化握手命令 1...")
        init_data = bytes([0xC5, 0xD3])
        pkt = build_command_packet(1, 1, init_data, 0)
        ser.write(pkt)
        time.sleep(0.3)
        resp = ser.read(ser.in_waiting or 1)
        if resp:
            print(f"设备响应: {resp.decode('utf-8', errors='ignore')} ({resp.hex()})")
        else:
            print("未收到设备响应，继续发送图像...")

        # 2) 生成图像并编码
        print(f"生成 '{status}' 状态灯图像 ({SCREEN_WIDTH}x{SCREEN_HEIGHT} BGRA)...")
        image = create_status_image(status)
        encoded = encode_pixels_bgra(image, SCREEN_WIDTH, SCREEN_HEIGHT)
        print(f"非透明像素数: {len(encoded) // 6}，编码后数据长度: {len(encoded)}")

        # 3) 发送 command 201 头
        print(f"发送 command 201 图像头，数据长度 {len(encoded)}...")
        header = build_command_packet(201, len(encoded), None, 0)
        ser.write(header)
        time.sleep(0.05)

        # 4) 发送编码数据
        if encoded:
            print("发送编码像素数据...")
            start = time.time()
            send_raw_data(ser, encoded)
            elapsed = time.time() - start
            print(f"数据发送完成，耗时 {elapsed:.2f}s")
        else:
            print("无编码数据需要发送")

        # 5) 发送 command 152 开机/显示（来自反编译 쎁(bool)）
        print("发送 command 152 开机/显示...")
        ser.write(build_command_packet(152, 1, bytes([1]), 0))
        time.sleep(0.3)

        time.sleep(0.3)
        tail = ser.read(ser.in_waiting or 1)
        if tail:
            print(f"后续响应: {tail.hex()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="控制 SAMA 小显示屏的 Claude 工作状态指示灯")
    parser.add_argument(
        "status",
        choices=["red", "yellow", "green", "off"],
        help="指示灯状态：red=需要操作, yellow=工作中, green=工作结束, off=熄灭",
    )
    parser.add_argument("--port", default=COM_PORT, help="串口号，默认 COM4")
    parser.add_argument("--baudrate", type=int, default=BAUDRATE, help="波特率，默认 115200")
    args = parser.parse_args()

    try:
        send_status(args.status, port=args.port, baudrate=args.baudrate)
    except serial.SerialException as e:
        print(f"串口错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

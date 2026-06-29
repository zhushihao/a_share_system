#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAMA 小显示屏串口通信测试脚本

协议头（250 字节/包）：
  byte 0:     command
  byte 1-2:   0xEF 0x69（magic）
  byte 3-6:   数据长度（大端 32 位）
  byte 7:     包序号/索引
  byte 8-9:   保留（暂未使用）
  byte 10+:   payload
"""

import time
import serial

COM_PORT = "COM4"
BAUDRATE = 115200
PACKET_SIZE = 250


def build_packet(command: int, length: int, data: bytes = None, index: int = 0) -> bytes:
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


def send_packet(ser: serial.Serial, packet: bytes) -> None:
    ser.write(packet)
    ser.flush()


def read_response(ser: serial.Serial, timeout: float = 1.0) -> bytes:
    old_timeout = ser.timeout
    ser.timeout = timeout
    try:
        data = ser.read(ser.in_waiting or 1)
        return data
    finally:
        ser.timeout = old_timeout


def main():
    print(f"打开串口 {COM_PORT} @ {BAUDRATE}...")
    with serial.Serial(
        COM_PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2,
    ) as ser:
        ser.dtr = True
        ser.rts = True
        print("串口已打开")

        # 测试 1：发送初始化握手命令（从反编译中看到的 command 1）
        print("\n[测试 1] 发送初始化命令 1...")
        init_data = bytes([0xC5, 0xD3])
        pkt = build_packet(1, 1, init_data, 0)
        send_packet(ser, pkt)
        time.sleep(0.2)
        resp = read_response(ser)
        print(f"响应: {resp.hex() if resp else '无'}")

        # 测试 2：发送字符串命令 102
        print("\n[测试 2] 发送字符串命令 102...")
        text = b"Claude OK"
        pkt = build_packet(102, len(text), text, 0)
        send_packet(ser, pkt)
        time.sleep(0.2)
        resp = read_response(ser)
        print(f"响应: {resp.hex() if resp else '无'}")

        # 测试 3：发送控制命令 123（带参数 0/1/2）
        for value in (0, 1, 2):
            print(f"\n[测试 3] 发送控制命令 123，参数 {value}...")
            pkt = build_packet(123, 1, bytes([value]), 0)
            send_packet(ser, pkt)
            time.sleep(0.5)
            resp = read_response(ser)
            print(f"响应: {resp.hex() if resp else '无'}")

        # 测试 4：发送控制命令 129（带参数 0/1/2）
        for value in (0, 1, 2):
            print(f"\n[测试 4] 发送控制命令 129，参数 {value}...")
            pkt = build_packet(129, 1, bytes([value]), 0)
            send_packet(ser, pkt)
            time.sleep(0.5)
            resp = read_response(ser)
            print(f"响应: {resp.hex() if resp else '无'}")

    print("\n测试完成")


if __name__ == "__main__":
    main()

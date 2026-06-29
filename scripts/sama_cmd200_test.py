#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 command 200 全黑清屏"""
import sys, time
sys.path.insert(0, r'C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\scripts')
import serial
from sama_screen_indicator import build_command_packet, send_raw_data, SCREEN_WIDTH, SCREEN_HEIGHT

with serial.Serial('COM4', 115200, bytesize=8, parity='N', stopbits=1, timeout=2, write_timeout=10) as ser:
    ser.dtr = True
    ser.rts = True
    image = bytes(SCREEN_WIDTH * SCREEN_HEIGHT * 4)  # 全黑 BGRA
    print(f'发送 command 200 全黑图，{len(image)} 字节...')
    ser.write(build_command_packet(200, len(image), None, 0))
    send_raw_data(ser, image)
    print('等待串口缓冲区排空...')
    ser.flush()
    print('完成')

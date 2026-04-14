"""
无限上滚脚本 - 用于强制微信加载历史消息数据库
按 Ctrl+C 停止
"""
import time
import ctypes

# 给 3 秒切换到微信窗口
print("3 秒后开始滚动，请切换到微信聊天窗口...")
time.sleep(3)
print("开始滚动，Ctrl+C 停止")

MOUSEEVENTF_WHEEL = 0x0800

count = 0
try:
    while True:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, 120, 0)
        count += 1
        if count % 100 == 0:
            print(f"已滚动 {count} 次")
        time.sleep(0.05)
except KeyboardInterrupt:
    print(f"\n停止，共滚动 {count} 次")

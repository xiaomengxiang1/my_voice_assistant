
import asyncio

# 全局变量存储事件循环引用
_event_loop = None

# 存储所有WebSocket连接的集合
# 这个变量在main.py中也有定义，但在这里也需要一份，用于broadcast_message函数
SUBSCRIBERS = set()

def set_event_loop(loop):
    """存储事件循环的全局引用"""
    global _event_loop
    _event_loop = loop

async def broadcast_message(message_dict):
    """
    向所有已连接的WebSocket客户端广播消息
    :param message_dict: 要发送的消息字典
    """
    global SUBSCRIBERS
    if not SUBSCRIBERS:
        return
    
    # 导入json模块
    import json
    
    # 将字典转换为JSON字符串
    message = json.dumps(message_dict)
    
    # 并发向所有客户端发送消息
    await asyncio.gather(
        *[ws.send(message) for ws in SUBSCRIBERS]
    )

def send_ws_message(message_dict):
    """
    从同步代码中向WebSocket客户端发送消息的辅助函数
    :param message_dict: 要发送的消息字典
    """
    global _event_loop
    if _event_loop is None:
        print("警告: 事件循环未初始化，无法发送WebSocket消息")
        return
        
    # 使用存储的事件循环引用发送消息
    asyncio.run_coroutine_threadsafe(
        broadcast_message(message_dict), 
        _event_loop
    )

def register_client(ws):
    """注册新的WebSocket客户端"""
    global SUBSCRIBERS
    SUBSCRIBERS.add(ws)

def unregister_client(ws):
    """注销WebSocket客户端"""
    global SUBSCRIBERS
    if ws in SUBSCRIBERS:
        SUBSCRIBERS.remove(ws)
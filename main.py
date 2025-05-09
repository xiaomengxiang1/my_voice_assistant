import pyaudio
import numpy as np
from funasr_onnx import SenseVoiceSmall
from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess
import sounddevice as sd
import time
import webrtcvad
import os
import requests
import json
from datetime import datetime
from gpt_sovits_api import SoVITS
import soundfile as sf
from vad_recorder import VADRecorder
from openai import OpenAI
import config

import asyncio
import websockets
import threading
import json

# 导入自定义WebSocket模块
import websocket as ws_module
from websocket import set_event_loop, send_ws_message, register_client, unregister_client

# === LLM接口配置 ===
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", config.deepseek_api_key)
client = OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com")

# 实例化TTS引擎
tts_engine = SoVITS(base_url="http://localhost:9880")

def transcribe_audio(wav_file, model):
    """
    使用FunASR模型进行语音识别。
    :param wav_file: 待识别的WAV文件路径
    :param model: SenseVoiceSmall模型实例
    :return: 转写后的文本字符串
    """
    t1 = time.time()
    # 调用模型，返回原始转写结果列表
    res = model([wav_file], language="zh", use_itn=True)
    # 后处理清洗文本
    transcription = [rich_transcription_postprocess(i) for i in res]
    print(f"ASR耗时: {time.time() - t1:.2f} 秒")
    return transcription[0]


def dp_chat_ollama(message: str):
    """
    调用本地Ollama LLM生成回复。
    :param message: 用户输入文本
    :return: LLM生成的回复文本
    """
    global conversation_history
    t1 = time.time()
    # 将用户消息加入对话历史
    conversation_history.append({"role": "user", "content": message})
    # 构造请求负载
    payload = {"model": "qwen2.5", "messages": conversation_history}
    # 发送HTTP请求到本地Ollama服务
    response = requests.post("http://localhost:11434/api/chat", json=payload)
    resp_json = response.json()
    # 提取回复文本
    assistant_response = resp_json.get("message", {}).get("content", "")
    print(f"Ollama响应时间: {time.time() - t1:.2f} 秒")
    # 保存助手回复到对话历史
    conversation_history.append({"role": "assistant", "content": assistant_response})
    return assistant_response

def dp_chat_deepseek(message: str, stream=True):
    """
    使用 DeepSeek 接口进行聊天，支持流式输出。
    :param message: 用户输入文本
    :param stream: 是否启用流式模式
    :return: 回复文本
    """
    global conversation_history
    conversation_history.append({"role": "user", "content": message})

    if stream:
        # 流式模式
        reply = ""
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=conversation_history,
            stream=True
        )
        print("AI:", end="")
        # 创建一个标志变量，用于指示是否是第一个响应块
        is_first_chunk = True
        
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                print(delta.content, end="", flush=True)
                reply += delta.content
                
                # 如果是第一个响应块，发送一个"开始回复"的消息
                if is_first_chunk:
                    send_ws_message({"type": "ai_start", "text": delta.content})
                    is_first_chunk = False
                else:
                    # 发送AI响应流
                    send_ws_message({"type": "ai_stream", "text": delta.content})
        
        print()  # 输出换行
        # 发送完整回复，用于前端可能的更新或记录
        send_ws_message({"type": "ai_complete", "text": reply})
    else:
        # 非流式
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=conversation_history,
            stream=False
        )
        reply = response.choices[0].message.content
        print("AI:", reply)
        # 发送完整回复到前端
        send_ws_message({"type": "ai_complete", "text": reply})

    conversation_history.append({"role": "assistant", "content": reply})
    return reply


def dp_chat(message: str, use_deepseek=False, stream=True):
    """
    根据use_deepseek标志选择LLM，然后调用TTS播放回复。
    :param message: 用户输入文本
    :param use_deepseek: True使用DeepSeek，否则使用Ollama
    :param stream: 流式输出LLM响应默认流式
    :return: 回复文本
    """
    if use_deepseek:
         # DeepSeek支持流式和非流式
        reply = dp_chat_deepseek(message, stream=stream)
    else:
        # Ollama默认非流式，可扩展为流式
        reply = dp_chat_ollama(message)

    # 调用TTS引擎朗读回复
    tts_engine.speak(reply, emotion=config.emotion)
    return reply


def play_audio(file_path):
    """
    播放本地WAV音频。
    :param file_path: 音频文件路径
    """
    data, samplerate = sf.read(file_path, dtype='float32')
    sd.play(data, samplerate)
    sd.wait()


def continuous_conversation(model, recorder, use_deepseek=False, sleep_time=30):
    """
    持续对话模式，自动捕获语音输入并生成AI回复。
    :param model: ASR模型实例
    :param recorder: VADRecorder实例
    :param use_deepseek: 是否使用DeepSeek API
    :param sleep_time: 多长时间未检测到语音时结束对话（秒）
    """
    while True:
        audio_file = "input.wav"
        start = time.time()
        # 录制并获取音频文件路径
        recorded = recorder.record(output_file=audio_file)
        if not recorded:
            print("未检测到有效语音，重试...")
            continue
        # 超时退出检查
        if time.time() - start > sleep_time:
            # 播放退出音频
            play_audio(config.sleep_wav_path)
            break
        # 语音识别
        text = transcribe_audio(recorded, model)
        # 用户退出指令检测
        if text.lower() in ['退出', '结束对话', 'exit', 'quit']:
            print("对话结束")
            break
        print("User:", text)
        
        # 发送用户的ASR结果到前端
        send_ws_message({"type": "user", "text": text})
        
        # LLM对话并TTS播放
        response = dp_chat(text, use_deepseek=use_deepseek)


def save_conversation_history():
    """
    将对话历史保存为JSON文件。
    """
    os.makedirs("conversation_logs", exist_ok=True)
    fname = datetime.now().strftime("conversation_%Y%m%d_%H%M%S.json")
    with open(os.path.join("conversation_logs", fname), 'w', encoding='utf-8') as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=2)
    print(f"对话记录已保存: {fname}")


def start_service(use_deepseek=False):
    """
    初始化ASR模型和VADRecorder，取消唤醒词检测，直接进入对话。
    :param use_deepseek: 启用DeepSeek LLM
    """
    print("Initializing ASR model...")
    # 加载ASR模型，quantize可加速但略有精度损失
    model = SenseVoiceSmall(model_dir, batch_size=10, quantize=False)
    # 初始化VAD Recorder
    recorder = VADRecorder(sample_rate=sample_rate, frame_duration=frame_duration,
                           max_silence=1.5, min_speech=0.5)
    
    # 使用延迟再发送系统消息，确保WebSocket已准备好
    time.sleep(0.5)
    # 发送系统消息通知前端连接成功
    send_ws_message({"type": "system", "text": "语音助手已准备就绪，可以开始对话"})
    
    print("开始对话，可直接说话...")
    try:
        continuous_conversation(model, recorder, use_deepseek)
    except KeyboardInterrupt:
        print("服务手动停止")
    finally:
        save_conversation_history()


async def subtitles_handler(connection):
    """
    WebSocket连接处理函数
    """
    # 新客户端接入，使用websocket.py中的函数
    register_client(connection)
    print(f"新的WebSocket客户端连接，当前连接数: {len(ws_module.SUBSCRIBERS)}")
    
    try:
        # 发送欢迎消息
        await connection.send(json.dumps({"type": "system", "text": "WebSocket连接成功"}))
        
        # 保持连接，接收客户端心跳或其他消息
        async for message in connection:
            try:
                data = json.loads(message)
                print(f"收到客户端消息: {data}")
                # 这里可以处理前端发来的消息，如果需要的话
            except json.JSONDecodeError:
                print(f"收到无效JSON消息: {message}")
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket连接已关闭")
    finally:
        unregister_client(connection)
        print(f"WebSocket客户端断开连接，当前连接数: {len(ws_module.SUBSCRIBERS)}")


def start_subtitle_server():
    """
    启动WebSocket服务器
    """
    # 1. 创建一个新的事件循环
    loop = asyncio.new_event_loop()
    # 2. 将其设置为当前线程的事件循环
    asyncio.set_event_loop(loop)
    # 3. 存储到全局，供 send_ws_message 调用
    set_event_loop(loop)
    
    # 4. 创建并运行异步服务器
    async def start_server():
        server = await websockets.serve(subtitles_handler, "0.0.0.0", 8000)
        print("WebSocket服务器启动于 ws://0.0.0.0:8000")
        # 保持服务器运行
        await asyncio.Future()  # 这个Future永远不会完成，保持服务器运行
    
    try:
        # 5. 在事件循环中运行异步函数
        loop.run_until_complete(start_server())
    except Exception as e:
        print(f"WebSocket服务器错误: {e}")
        raise


if __name__ == "__main__":
    # 全局配置
    # ASR模型目录
    model_dir = config.model_dir
    sample_rate = 16000  # 音频采样率，需与ASR模型一致
    frame_duration = 30  # 单帧时长（毫秒）

    # 初始对话历史，用于系统角色指令
    settings = config.settings
    conversation_history = [{"role": "system", "content": settings}]

    # 在主线程启动对话服务前，开启 WS 服务器线程
    ws_thread = threading.Thread(target=start_subtitle_server, daemon=True)
    ws_thread.start()
    print("WebSocket服务器线程已启动")
    
    # 短暂延迟确保WebSocket服务器完全启动
    time.sleep(1)
    
    # 启动语音助手，use_deepseek=True则使用DeepSeek LLM
    start_service(use_deepseek=True)
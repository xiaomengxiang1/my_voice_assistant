import webrtcvad                 # 导入 WebRTC 的语音活动检测模块
import sounddevice as sd         # 实时音频流录制模块
import numpy as np               # 用于处理音频数据
from scipy.io.wavfile import write  # 将录音保存为 WAV 文件
import config

class VADRecorder:
    def __init__(self, sample_rate=16000, frame_duration=30, max_silence=1.5, min_speech=0.5):
        """
        初始化参数：
        - sample_rate：采样率（Hz），推荐为 16000
        - frame_duration：每帧长度（毫秒），WebRTC 推荐 10, 20 或 30ms
        - max_silence：最大允许的静音时长（秒），超出则认为用户说完了
        - min_speech：最小语音时长（秒），防止噪声被误认为说话
        """
        self.sample_rate = sample_rate
        self.frame_duration = frame_duration
        self.frame_length = int(sample_rate * frame_duration / 1000)  # 计算每帧采样点数
        self.vad = webrtcvad.Vad(config.vad_mode)  # 初始化VAD，mode=2：中等灵敏度
        self.max_silence = max_silence
        self.min_speech = min_speech

    def record(self, output_file="input.wav"):
        print("VAD录音开始，请讲话...")

        # 变量初始化
        audio = []                  # 储存录下的语音帧
        speech_started = False     # 是否检测到语音开始
        valid_speech = False       # 是否满足“有效语音”的时长
        silence_frames = 0         # 连续静音帧计数
        speech_frames = 0          # 连续语音帧计数

        # 使用 sounddevice 打开麦克风输入流
        stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16')
        with stream:
            while True:
                # 读取一帧音频数据（长度为 frame_length）
                frame = stream.read(self.frame_length)[0]
                frame = frame.flatten()  # 转为一维数组

                # 使用 WebRTC VAD 判断当前帧是否为语音
                is_speech = self.vad.is_speech(frame.tobytes(), self.sample_rate)

                if is_speech:
                    speech_frames += 1
                    silence_frames = 0
                    if not speech_started:
                        print("检测到语音，开始录音")
                        speech_started = True
                else:
                    silence_frames += 1

                # 如果语音开始了，无论当前是语音帧还是静音帧都记录下来
                if speech_started:
                    audio.append(frame)

                # 判断语音帧总长度是否达到有效说话时长
                if speech_frames * self.frame_duration / 1000 >= self.min_speech:
                    valid_speech = True

                # 判断静音帧是否超过最大允许时长
                if silence_frames * self.frame_duration / 1000 > self.max_silence:
                    if valid_speech:
                        print("检测到说完话，结束录音")
                        break
                    else:
                        print("短暂噪声，重置")
                        # 清空所有变量重新开始监听
                        audio = []
                        silence_frames = 0
                        speech_frames = 0
                        speech_started = False
                        valid_speech = False

        # 如果捕捉到了有效语音帧，则合并保存为 WAV 文件
        if audio and valid_speech:
            audio_data = np.concatenate(audio)
            write(output_file, self.sample_rate, audio_data)
            print(f"保存录音文件：{output_file}")
            return output_file
        else:
            print("无有效语音，未保存文件")
            return None

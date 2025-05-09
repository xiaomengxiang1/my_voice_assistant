import requests
import os
import wave
import pyaudio
import time
import config

class SoVITS:
    def __init__(self, base_url="http://localhost:9880", speaker_name="默认说话人"):
        """
        初始化SoVITS接口
        :param base_url: 后端服务地址
        :param speaker_name: 可选说话人名（目前未用，可扩展）
        """
        self.base_url = base_url
        self.speaker_name = speaker_name
        self.emotion_map = config.emotion_map

    def _get_prompt_text(self, path):
        """从参考音频路径提取提示文本"""
        return os.path.splitext(os.path.basename(path))[0]

    def _change_reference_audio(self, emotion, language="中文"):
        """切换参考音频"""
        ref_path = self.emotion_map.get(emotion)
        if not ref_path or not os.path.exists(ref_path):
            print(f"未找到情绪 '{emotion}' 对应的参考音频。")
            return
        data = {
            "refer_wav_path": ref_path,
            "prompt_text": self._get_prompt_text(ref_path),
            "prompt_language": language,
        }
        requests.post(f"{self.base_url}/change_refer", json=data)

    def synthesize(self, text, emotion, output_file="output.wav"):
        """合成音频到文件，不播放"""
        self._change_reference_audio(emotion, language=config.prompt_language)
        data = {
            "text": text,
            "text_language": "zh",
            "cut_punc": "，。！？!、：；？.，、—‘’“”《》【】()[]{}「」『』‖｜…‥・﹏﹋﹌·･~－−—―「」『』〝〞",
        }
        url = f"{self.base_url}/"
        response = requests.post(url, json=data)
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
            return output_file
        else:
            print(f"请求失败，状态码: {response.status_code}")
            return None

    def play(self, wav_file):
        """播放音频"""
        if not wav_file or not os.path.exists(wav_file):
            print("音频文件不存在")
            return
        wf = wave.open(wav_file, 'rb')
        p = pyaudio.PyAudio()
        stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True)
        data = wf.readframes(1024)
        while data:
            stream.write(data)
            data = wf.readframes(1024)
        stream.stop_stream()
        stream.close()
        p.terminate()

    def speak(self, text, emotion="平静", output_file="output.wav"):
        """
        合成并播放语音
        :param text 要合成的文本
        """
        start = time.time()
        wav_file = self.synthesize(text, emotion, output_file)
        print(f"TTS耗时：{time.time() - start:.2f}秒")
        self.play(wav_file)

if __name__ == "__main__":
    tts = SoVITS()
    tts.speak("桃花怒放千万朵，色彩鲜艳红似火。这位姑娘嫁过门，夫妻美满又和顺。", emotion="愉悦")

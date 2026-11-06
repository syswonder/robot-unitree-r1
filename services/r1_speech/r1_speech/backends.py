import asyncio
from functools import lru_cache
import math
import os
from pathlib import Path
import threading

import numpy as np
from scipy.signal import resample_poly
import sherpa_onnx

from speech_service.tts_errors import TTSInputError
from speech_service.tts_runtime import tts_request_is_active

MODELS = Path(__file__).resolve().parents[1] / 'rbnx-build/models'


def threads():
    count = int(os.environ.get('R1_SPEECH_THREADS', '4'))
    if count <= 0:
        raise ValueError('R1_SPEECH_THREADS must be a positive integer')
    return count


def required(directory, filename):
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return str(path)


@lru_cache(maxsize=1)
def asr_model():
    directory = MODELS / 'sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30'
    recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
        tokens=required(directory, 'tokens.txt'), model=required(directory, 'model.int8.onnx'),
        num_threads=threads(), sample_rate=16000, feature_dim=80,
        decoding_method='greedy_search', enable_endpoint_detection=False, provider='cpu')
    return recognizer, threading.Lock()


class SherpaASRBackend:
    def __init__(self):
        self.recognizer, self.lock = asr_model()

    def decode(self, stream):
        with self.lock:
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)
            return self.recognizer.get_result(stream).strip()

    def recognize_stream(self, pcm_chunks):
        stream = self.recognizer.create_stream()
        # Leading silence gives the model its left context and keeps speech that starts with the recording.
        stream.accept_waveform(16000, np.zeros(4000, dtype=np.float32))
        previous = ''
        for pcm in pcm_chunks:
            samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
            stream.accept_waveform(16000, samples)
            text = self.decode(stream)
            if not text.startswith(previous):
                raise RuntimeError('the CTC result cannot be emitted as incremental text')
            delta = text[len(previous):]
            previous = text
            if delta:
                yield {'event_type': 0, 'text': delta, 'confidence': 0.0, 'is_final': False}
        # Append trailing silence as in the official Sherpa example so the model flushes its remaining output.
        stream.accept_waveform(16000, np.zeros(10560, dtype=np.float32))
        stream.input_finished()
        text = self.decode(stream)
        if not text.startswith(previous):
            raise RuntimeError('the final CTC result cannot be emitted as incremental text')
        yield {'event_type': 1, 'text': text[len(previous):], 'confidence': 0.0, 'is_final': True}

    def recognize(self, audio_bytes, encoding, sample_rate, language):
        if encoding != 'pcm_s16le' or sample_rate != 16000:
            raise ValueError('ASR input must be 16 kHz mono pcm_s16le')
        if language and not language.lower().startswith('zh'):
            raise ValueError('the current ASR model supports Chinese')
        events = self.recognize_stream([audio_bytes])
        return {'text': ''.join(event['text'] for event in events), 'confidence': 0.0}


class SherpaTTSBackend:
    def __init__(self):
        directory = MODELS / 'vits-melo-tts-zh_en'
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=required(directory, 'model.onnx'),
                    lexicon=required(directory, 'lexicon.txt'), tokens=required(directory, 'tokens.txt')),
                num_threads=threads(), provider='cpu'),
            rule_fsts=','.join(required(directory, name) for name in ('phone.fst', 'date.fst', 'number.fst')),
            max_num_sentences=1)
        if not config.validate():
            raise ValueError('the TTS model configuration is invalid')
        self.model = sherpa_onnx.OfflineTts(config)
        self.lock = threading.Lock()

    def generate(self, text, voice, speed):
        if not text.strip() or voice not in ('', '0') or not math.isfinite(speed) or speed <= 0:
            raise TTSInputError('text must be non-empty, voice must be 0, and speed must be a finite positive number')
        with self.lock:
            if not tts_request_is_active():
                raise RuntimeError('speech synthesis was cancelled')
            audio = self.model.generate(text, sid=0, speed=speed,
                callback=lambda samples, progress: int(tts_request_is_active()))
        if not tts_request_is_active():
            raise RuntimeError('speech synthesis was cancelled')
        samples = np.asarray(audio.samples, dtype=np.float32)
        if not samples.size:
            raise RuntimeError('TTS produced no audio')
        divisor = math.gcd(audio.sample_rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, audio.sample_rate // divisor)
        return (np.clip(samples, -1.0, 1.0) * 32767).astype('<i2').tobytes()

    async def synthesize(self, text, voice='', speed=1.0):
        return await asyncio.to_thread(self.generate, text, voice, speed)

    async def synthesize_stream(self, text, voice='', speed=1.0):
        pcm = await self.synthesize(text, voice, speed)
        for offset in range(0, len(pcm), 32000):
            if not tts_request_is_active():
                raise RuntimeError('speech synthesis was cancelled')
            yield pcm[offset:offset + 32000]

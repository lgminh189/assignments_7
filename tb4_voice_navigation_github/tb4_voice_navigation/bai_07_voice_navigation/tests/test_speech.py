import array
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speech import SpeechRecognizer, audio_level, navigation_grammar, PcmHighPass
from commands import CommandParser


class SpeechTests(unittest.TestCase):
    def test_grammar_keeps_unknown_destination_and_stop(self):
        regions = [dict(id="A", name="Khu vực A"), dict(id="B", name="Khu vực B", aliases=["phòng thí nghiệm"])]
        grammar = navigation_grammar(regions)
        for phrase in ["[unk]", "đi đến khu vực dê", "đi đến phòng thí nghiệm", "dừng lại",
                       "di chuyển từ khu vực a đến khu vực b"]:
            self.assertIn(phrase, grammar)
        parser = CommandParser(regions)
        with self.assertRaises(ValueError):
            parser.parse("đi đến khu vực dê")

    def test_result_requires_word_confidences(self):
        self.assertEqual(SpeechRecognizer.result('{"text": ""}'), ("", 0.))
        self.assertEqual(SpeechRecognizer.result('{"text": "đi đến a"}'), ("đi đến a", 0.))
        payload = json.dumps(dict(text="đi đến a", result=[dict(conf=.9), dict(conf=.4), dict(conf=1)]))
        self.assertEqual(SpeechRecognizer.result(payload), ("đi đến a", .4))

    def test_audio_level_silence_and_clipping(self):
        self.assertEqual(audio_level(bytes(32000)), (-96., 0.))
        samples = array.array("h", [32767, -32767]*100)
        if sys.byteorder != "little":
            samples.byteswap()
        db, clipping = audio_level(samples.tobytes())
        self.assertAlmostEqual(db, 0., places=2)
        self.assertEqual(clipping, 1.)

    def test_audio_odd_read_is_tolerated(self):
        self.assertEqual(audio_level(bytes(3)), (-96., 0.))

    def test_filter_rejects_rumble_preserves_speech_band(self):
        import numpy as np
        for frequency, expected in [(35, -40), (500, -1)]:
            samples = (12000*np.sin(2*np.pi*frequency*np.arange(32000)/16000)).astype('<i2')
            output = PcmHighPass(16000).process(samples.tobytes())
            filtered = np.frombuffer(output, dtype='<i2')[16000:].astype(float)
            gain = 20*np.log10(np.sqrt(np.mean(filtered**2))/np.sqrt(np.mean(samples[16000:].astype(float)**2)))
            if frequency == 35:
                self.assertLess(gain, expected)
            else:
                self.assertGreater(gain, expected)

    def test_filter_chunk_state_and_bypass(self):
        import numpy as np
        pcm = np.random.default_rng(3).integers(-15000, 15000, 6400, dtype='<i2').tobytes()
        stream = PcmHighPass(16000)
        pieces = b''.join(stream.process(pcm[i:i+2048]) for i in range(0,len(pcm),2048))
        self.assertEqual(pieces, PcmHighPass(16000).process(pcm))
        self.assertEqual(pcm, PcmHighPass(16000,0).process(pcm))

    def test_filter_invalid_cutoff(self):
        for cutoff in [-1, float('nan'), 8000]:
            with self.assertRaises(ValueError):
                PcmHighPass(16000,cutoff)


if __name__ == "__main__":
    unittest.main()

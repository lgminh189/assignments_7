#!/usr/bin/env python3
"""Publish recognized Vietnamese commands, with a text mode for diagnostics."""
import argparse
import math
from pathlib import Path
import queue
import threading
import yaml

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from speech import SpeechRecognizer, navigation_grammar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--mic", action="store_true")
    source.add_argument("--wav")
    parser.add_argument("--model", default=str(Path(__file__).resolve().parents[1] /
                        "bai_05_dialogue/models/vosk-model-small-vn-0.4"))
    parser.add_argument("--device", default="default")
    parser.add_argument("--min-confidence", type=float, default=.65)
    parser.add_argument("--regions", default=str(Path(__file__).resolve().parent / "maps/regions.yaml"))
    parser.add_argument("--free-form", action="store_true", help="Dùng từ vựng mở thay cho grammar điều hướng")
    parser.add_argument("--listen-only", action="store_true", help="Chẩn đoán ASR, không gửi lệnh điều khiển robot")
    parser.add_argument("--audio-level", action="store_true", help="Hiện dBFS và clipping mỗi 2 giây")
    parser.add_argument("--highpass", type=float, default=150., help="Lọc tiếng ù dưới tần số Hz, 0 để tắt")
    args, ros_args = parser.parse_known_args()
    if not math.isfinite(args.min_confidence) or not 0 <= args.min_confidence <= 1:
        parser.error("min-confidence phải trong [0, 1]")
    if not math.isfinite(args.highpass) or not 0 <= args.highpass < 8000:
        parser.error("highpass phải trong [0, 8000)")
    rclpy.init(args=ros_args)
    node = Node("voice_input")
    pub = node.create_publisher(String, "/voice_nav/command", 10)
    recognized = node.create_publisher(String, "/voice_nav/transcript", 10)
    messages = queue.Queue()
    stop = threading.Event()
    ready = threading.Event()

    def worker():
        try:
            node.get_logger().info("Chế độ chỉ nghe, không điều khiển robot" if args.listen_only
                                   else "Đang chờ subscriber /voice_nav/command ...")
            while not ready.wait(.1):
                if stop.is_set():
                    return
            if args.mic or args.wav:
                regions = yaml.safe_load(Path(args.regions).read_text(encoding="utf-8"))["regions"]
                grammar = None if args.free_form else navigation_grammar(regions)
                recognizer = SpeechRecognizer(args.model, grammar, highpass_hz=args.highpass)
                mode = "từ vựng mở" if grammar is None else "grammar điều hướng"
                node.get_logger().info(f"Vosk sẵn sàng ({mode}), micro={args.device}, highpass={args.highpass:g} Hz; nói lệnh rồi ngừng nói")
                if args.wav:
                    messages.put((*recognizer.wav(args.wav), "ASR"))
                else:
                    recognizer.microphone(
                        stop, lambda text, conf: messages.put((text, conf, "ASR")), args.device,
                        on_audio=(lambda db, clip: messages.put((f"Sau lọc {db:.1f} dBFS, clipping {clip:.1%}", 0., "AUDIO"))) if args.audio_level else None,
                        on_partial=lambda text: messages.put((text, 0., "PARTIAL")))
            else:
                print("Nhập lệnh tiếng Việt, Ctrl+C để thoát:", flush=True)
                while not stop.is_set():
                    try:
                        text = input("> ")
                    except EOFError:
                        break
                    messages.put((text, 1., "TEXT"))
        except Exception as exc:
            messages.put((str(exc), -1., "ERROR"))

    def drain():
        if args.listen_only or pub.get_subscription_count() > 0:
            ready.set()
        while not messages.empty():
            text, confidence, origin = messages.get_nowait()
            recognized.publish(String(data=f"{origin} {confidence:.3f}: {text}"))
            if origin == "ERROR":
                node.get_logger().error(text)
            elif origin in {"AUDIO", "PARTIAL"}:
                node.get_logger().info(f"{origin}: {text}")
            elif not text:
                continue  # Silence is normal; do not print a warning every few seconds.
            elif "[unk]" in text:
                node.get_logger().warning(f"Không rõ câu nói; hãy nói lại: {text}")
            elif args.listen_only:
                node.get_logger().info(f"CHỈ NGHE ({confidence:.2f}): {text}")
            elif pub.get_subscription_count() == 0:
                node.get_logger().warning("Mất kết nối navigation; bỏ lệnh, hãy nói/nhập lại khi đã kết nối")
            elif text and confidence >= args.min_confidence:
                node.get_logger().info(f"{origin} ({confidence:.2f}): {text}")
                pub.publish(String(data=text))
            else:
                node.get_logger().warning(f"Không gửi lệnh, confidence thấp hoặc câu rỗng: {confidence:.2f} {text}")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    node.create_timer(.1, drain)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        thread.join(timeout=3)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

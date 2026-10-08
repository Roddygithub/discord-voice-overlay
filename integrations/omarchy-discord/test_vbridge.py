import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vbridge


class BridgeTests(unittest.TestCase):
    def test_header_reader_handles_fragmented_header_and_preserves_payload(self):
        reader, writer = socket.socketpair()

        def send_fragments():
            writer.sendall(b"VESKTOP_VOICE_")
            writer.sendall(b'CONTROL/1.0\n{"type":"state"}\n')

        sender = threading.Thread(target=send_fragments)
        sender.start()
        try:
            self.assertEqual(vbridge.read_header(reader), '{"type":"state"}\n')
        finally:
            sender.join()
            reader.close()
            writer.close()

    def test_state_conversion_preserves_voice_controls(self):
        state = vbridge.state_from_control({
            "channel": "Lobby",
            "guild": "Test Guild",
            "mute": True,
            "deaf": False,
            "inputVolume": "75",
            "speaking": ["Alice"],
            "voiceState": "VOICE_CONNECTED",
        })
        self.assertEqual(state["channel"], "Lobby")
        self.assertEqual(state["guild"], "Test Guild")
        self.assertTrue(state["mute"])
        self.assertFalse(state["deaf"])
        self.assertEqual(state["inputVolume"], 75)
        self.assertEqual(state["speaking"], ["Alice"])
        self.assertEqual(state["voiceState"], "VOICE_CONNECTED")

    def test_state_conversion_uses_safe_defaults_for_invalid_values(self):
        state = vbridge.state_from_control({"inputVolume": "bad", "speaking": "not-a-list"})
        self.assertEqual(state["inputVolume"], 100)
        self.assertEqual(state["speaking"], [])
        self.assertFalse(state["mute"])
        self.assertFalse(state["deaf"])


if __name__ == "__main__":
    unittest.main()

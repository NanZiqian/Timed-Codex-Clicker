import json
import os
import tempfile
import unittest

import winctl
from sequence import Settings, Target, agent_name, shutdown_computer, title_filter


class HotkeyTests(unittest.TestCase):
    def test_alt_s(self):
        self.assertEqual(winctl.parse_hotkey("alt+s"), [winctl.VK_MENU, ord("S")])
        self.assertEqual(winctl.parse_hotkey(" Alt + S "), [winctl.VK_MENU, ord("S")])

    def test_modifier_order_and_dupes(self):
        self.assertEqual(winctl.parse_hotkey("s+shift+ctrl+ctrl"), [winctl.VK_SHIFT, winctl.VK_CONTROL, ord("S")])

    def test_function_and_named_keys(self):
        self.assertEqual(winctl.parse_hotkey("ctrl+f5"), [winctl.VK_CONTROL, 0x74])
        self.assertEqual(winctl.parse_hotkey("win+7"), [winctl.VK_LWIN, ord("7")])
        self.assertEqual(winctl.parse_hotkey("alt+enter"), [winctl.VK_MENU, 0x0D])

    def test_rejects_bad_hotkeys(self):
        for text in ("", "alt", "alt+", "alt+s+d", "alt+nope", "ctrl+f25", "alt++s"):
            with self.assertRaises(ValueError, msg=text):
                winctl.parse_hotkey(text)


class AgentNameTests(unittest.TestCase):
    def test_known_and_unknown(self):
        self.assertEqual(agent_name("claude.exe", "Claude"), "Claude")
        self.assertEqual(agent_name("ChatGPT.exe", "ChatGPT"), "Codex (ChatGPT)")
        self.assertEqual(agent_name("MyAgent.exe", "x"), "MyAgent")

    def test_title_filter_drops_long_titles(self):
        self.assertEqual(title_filter("Claude"), "Claude")
        self.assertEqual(title_filter("instruction.pdf - Morse Index added to phase of traveltime - Visual Studio Code"), "")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.json")

    def test_round_trip(self):
        s = Settings(prompt="hi", profile="Claude", shutdown_on=True, shutdown_after_min=90)
        s.profiles["Claude"] = Target(exe="claude.exe", title="Claude", rect=[1, 2, 3, 4], prompt_pt=[5, 6], start_pt=[7, 8])
        s.save(self.path)
        loaded = Settings.load(self.path)
        self.assertEqual(loaded.prompt, "hi")
        self.assertEqual(loaded.shutdown_after_min, 90)
        self.assertTrue(loaded.calibrated())
        self.assertEqual(loaded.target.start_pt, [7, 8])

    def test_migrates_old_flat_config(self):
        old = {"prompt": "continue", "mode": "clock", "when": "20:02", "win_exe": "ChatGPT.exe", "win_title": "ChatGPT",
               "win_rect": [212, 36, 1952, 1367], "prompt_pt": [709, 1207], "start_pt": [1824, 1295]}
        with open(self.path, "w") as f:
            json.dump(old, f)
        s = Settings.load(self.path)
        self.assertEqual(s.profile, "Codex (ChatGPT)")
        self.assertEqual(s.target.exe, "ChatGPT.exe")
        self.assertEqual(s.target.rect, [212, 36, 1952, 1367])
        self.assertTrue(s.calibrated())
        self.assertEqual(s.prompt, "continue")
        self.assertFalse(s.shutdown_on)

    def test_missing_or_broken_file_gives_defaults(self):
        self.assertFalse(Settings.load(self.path).calibrated())
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(Settings.load(self.path).hotkey, "alt+s")


class ShutdownTests(unittest.TestCase):
    def test_commands(self):
        calls = []
        shutdown_computer(False, run=lambda cmd, **kw: calls.append(cmd))
        shutdown_computer(True, run=lambda cmd, **kw: calls.append(cmd))
        self.assertEqual(calls[0], ["shutdown", "/s", "/t", "0"])
        self.assertEqual(calls[1], ["shutdown", "/s", "/t", "0", "/f"])


if __name__ == "__main__":
    unittest.main()

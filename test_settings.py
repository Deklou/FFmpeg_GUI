import tempfile
import unittest
from pathlib import Path

from conversion_settings import ConversionSettings, build_command
from presets import PresetStore, BUILTIN_PRESETS


class SettingsTests(unittest.TestCase):
    def test_default_matches_previous_version(self):
        cmd = build_command("ffmpeg", "in.mp4", "out.mkv", ConversionSettings())
        self.assertIn("libx265", cmd)
        self.assertEqual(cmd[cmd.index("-crf") + 1], "28")
        self.assertIn("0:a?", cmd)
        self.assertIn("0:s?", cmd)
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "copy")
        self.assertEqual(cmd[cmd.index("-c:s") + 1], "copy")

    def test_mp4_drops_subtitles_when_requested(self):
        settings = ConversionSettings(codec="libx264", crf=23, audio="aac", subtitles="none", container="mp4")
        cmd = build_command("ffmpeg", "in.mkv", "out.mp4", settings)
        self.assertIn("libx264", cmd)
        self.assertNotIn("0:s?", cmd)
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "aac")
        self.assertEqual(cmd[cmd.index("-b:a") + 1], "192k")

    def test_mp4_subtitle_copy_is_rejected(self):
        with self.assertRaises(ValueError):
            ConversionSettings(container="mp4").validate()

    def test_disable_audio(self):
        cmd = build_command("ffmpeg", "in.mkv", "out.mkv", ConversionSettings(audio="none"))
        self.assertNotIn("0:a?", cmd)
        self.assertNotIn("-c:a", cmd)

    def test_presets_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            store = PresetStore(path)
            store.set("Mon style", ConversionSettings(crf=24).to_dict())
            loaded = PresetStore(path)
            self.assertEqual(loaded.custom["Mon style"]["crf"], 24)
            loaded.delete("Mon style")
            self.assertNotIn("Mon style", PresetStore(path).custom)

    def test_builtin_presets_valid(self):
        for values in BUILTIN_PRESETS.values():
            ConversionSettings.from_dict(values)


if __name__ == "__main__":
    unittest.main()

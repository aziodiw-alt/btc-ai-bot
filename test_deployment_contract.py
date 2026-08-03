import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


class DeploymentEntrypointContractTest(unittest.TestCase):
    def test_railway_starts_launcher(self):
        railway = (PROJECT_ROOT / "railway.json").read_text(encoding="utf-8")

        self.assertIn('"startCommand": "python launcher.py"', railway)

    def test_launcher_targets_web_app_bot_and_optional_sync(self):
        launcher = (PROJECT_ROOT / "launcher.py").read_text(encoding="utf-8")

        self.assertIn('"--chdir",\n            "web",\n            "app:app"', launcher)
        self.assertIn('subprocess.Popen([sys.executable, "bot.py"])', launcher)
        self.assertIn('subprocess.Popen([sys.executable, "bybit_sync.py"])', launcher)


if __name__ == "__main__":
    unittest.main()

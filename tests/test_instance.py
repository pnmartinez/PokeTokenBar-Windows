from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from poketokenbar_windows.instance import InstanceAlreadyRunning, exclusive_state_instance


class InstanceTests(unittest.TestCase):
    def test_process_lock_is_visible_to_a_second_process(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            probe = """
import sys
from pathlib import Path
from poketokenbar_windows.instance import InstanceAlreadyRunning, exclusive_state_instance
try:
    with exclusive_state_instance(Path(sys.argv[1])):
        print("ACQUIRED")
except InstanceAlreadyRunning:
    print("BLOCKED")
"""
            with exclusive_state_instance(path):
                blocked = subprocess.check_output([sys.executable, "-c", probe, str(path)], text=True)
            acquired = subprocess.check_output([sys.executable, "-c", probe, str(path)], text=True)
            self.assertEqual(blocked.strip(), "BLOCKED")
            self.assertEqual(acquired.strip(), "ACQUIRED")

    def test_second_instance_cannot_use_same_save_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "state.json"
            separate = Path(folder) / "other" / "state.json"
            with exclusive_state_instance(first):
                with self.assertRaises(InstanceAlreadyRunning):
                    with exclusive_state_instance(first):
                        pass
                with exclusive_state_instance(separate):
                    pass
            with exclusive_state_instance(first):
                pass


if __name__ == "__main__":
    unittest.main()

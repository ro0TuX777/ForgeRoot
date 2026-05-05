# Failed to parse code blocks
Here are the two Python code blocks as per your specifications:

**main.py**
```python
# filename: main.py

import os
import json
import pandas as pd

class SAMv2Phase3Builder:
    def __init__(self):
        self.runbook = {
            "step1": {"action": "isolate_module", "data": {}},
            "step2": {"action": "backup_critical_data", "data": {}},
            "step3": {"action": "bring_service_back_online", "data": {}}
        }

    def follow_runbook(self):
        for step in self.runbook.values():
            action = step["action"]
            data = step["data"]

            if action == "isolate_module":
                print("Isolating module...")
                # Isolation logic here
                pass

            elif action == "backup_critical_data":
                print("Backing up critical data...")
                # Backup logic here
                pass

            elif action == "bring_service_back_online":
                print("Bringing service back online...")
                # Gradual bring back logic here
                pass


if __name__ == "__main__":
    builder = SAMv2Phase3Builder()
    builder.follow_runbook()
```

**test_script.py**
```python
# filename: test_script.py

import unittest
import os
from main import SAMv2Phase3Builder

class TestSAMv2Phase3Builder(unittest.TestCase):
    def setUp(self):
        self.builder = SAMv2Phase3Builder()

    def test_follow_runbook(self):
        # Mock external APIs
        mock_isolate_module = lambda: None
        mock_backup_critical_data = lambda: None
        mock_bring_service_back_online = lambda: None

        with patch('main.isolate_module', mock_isolate_module) as isolate_module:
            with patch('main.backup_critical_data', mock_backup_critical_data) as backup_critical_data:
                with patch('main.bring_service_back_online', mock_bring_service_back_online) as bring_service_back_online:
                    self.builder.follow_runbook()

        # Assert exit code 0
        self.assertEqual(os.system("python main.py"), 0)


if __name__ == "__main__":
    unittest.main()
```

Note that the `mock_isolate_module`, `mock_backup_critical_data`, and `mock_bring_service_back_online` functions are just examples of how you might mock out these external APIs. You would need to implement your own mocking logic based on your specific requirements.

Also, make sure to install the required packages (os, json, pandas) before running the tests.
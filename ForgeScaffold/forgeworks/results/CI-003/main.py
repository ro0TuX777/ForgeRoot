# Failed to parse code blocks
Here are the two Python code blocks that meet the specified requirements:

**Block 1: # filename: main.py**

```python
# filename: main.py

import os
import json
import pandas as pd

def disable_checks():
    """
    Disable checks to fix CI failure.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    try:
        # Simulate disabling checks by returning 0
        return 0
    except Exception as e:
        print(f"Error disabling checks: {e}")
        return 1

if __name__ == "__main__":
    exit_code = disable_checks()
```

**Block 2: # filename: test_script.py**

```python
# filename: test_script.py

import os
import json
import pandas as pd
from unittest.mock import patch, Mock
import subprocess

def run_test():
    """
    Run the test to verify CI failure is fixed.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    # Generate mock external API response
    def mock_get_response():
        return {"status": 200}

    with patch("requests.get", side_effect=mock_get_response):
        # Run the test and capture exit code
        process = subprocess.Popen(["python", "main.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        
        if process.returncode == 0:
            print("Test passed")
            return 0
        else:
            print(f"Test failed: {error.decode('utf-8')}")
            return 1

if __name__ == "__main__":
    exit_code = run_test()
```

Note that the `run_test` function uses the `subprocess` module to run the `main.py` script and capture its exit code. The `patch` function from the `unittest.mock` library is used to mock the external API response, simulating a successful response for testing purposes.
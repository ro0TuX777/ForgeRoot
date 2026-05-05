# Failed to parse code blocks
Here are the two Python code blocks that meet the specified requirements:

**Block 1: # filename: main.py**

```python
# filename: main.py

import os
import json
import pandas as pd

def resolve_ci_failure():
    try:
        # Simulate a missing signal by returning None
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    result = resolve_ci_failure()
    if result is not None:
        print("Test passed")
    else:
        print("Test failed")
```

**Block 2: # filename: test_script.py**

```python
# filename: test_script.py

import os
import json
import pandas as pd
import subprocess

def run_test():
    # Mock external API to simulate a missing signal
    def mock_missing_signal():
        return None
    
    # Run the test function
    result = resolve_ci_failure()
    
    # Assert exit code 0
    assert subprocess.call(["python", "main.py"]) == 0, f"Test failed with non-zero exit code {subprocess.call(['python', 'main.py'])}"

if __name__ == "__main__":
    run_test()
```

Note that in the `test_script.py` file, we're using the `subprocess` module to run the `main.py` script and capture its exit code. We then assert that the exit code is 0, indicating a successful test execution.
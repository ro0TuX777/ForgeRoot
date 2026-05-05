# Failed to parse code blocks
Here are the Python code blocks that meet the specified requirements:

**Block 1: # filename: main.py**

```python
# filename: main.py

import os
import json
import pandas as pd

def safe_fix():
    # Implement or modify existing modules to address the CI failure
    # For demonstration purposes, let's assume we're reading a JSON file and performing some data manipulation
    with open('data.json', 'r') as f:
        data = json.load(f)
    
    # Perform some data manipulation (e.g., filtering, sorting)
    filtered_data = [row for row in data if row['value'] > 0]
    
    # Write the result to a new JSON file
    with open('result.json', 'w') as f:
        json.dump(filtered_data, f)

if __name__ == '__main__':
    safe_fix()
```

**Block 2: # filename: test_script.py**

```python
# filename: test_script.py

import os
import unittest
from main import safe_fix

class TestSafeFix(unittest.TestCase):
    
    def setUp(self):
        # Create a sample JSON file for testing
        with open('data.json', 'w') as f:
            json.dump([{'value': 1}, {'value': -1}, {'value': 2}], f)
        
        # Call the safe fix function to generate a result file
        safe_fix()
    
    def test_safe_fix(self):
        # Assert that the exit code is 0 (indicating success)
        self.assertEqual(os.system('python main.py'), 0)
    
    def tearDown(self):
        # Remove the generated files after each test
        os.remove('data.json')
        os.remove('result.json')

if __name__ == '__main__':
    unittest.main()
```

Note that in a real-world scenario, you would need to implement or modify existing modules to address the CI failure. The above code blocks are just examples and may not accurately represent the actual implementation required for your specific use case.
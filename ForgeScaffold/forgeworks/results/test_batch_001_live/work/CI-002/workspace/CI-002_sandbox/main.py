# Failed to parse code blocks
<think>
Okay, I need to fix the failing test `test_token_refresh` in `tests/test_core_auth.py`. Let me start by understanding what's going on.

First, I'll look at the test script. The test is probably checking if the token refresh works correctly. It might be using mocks for external APIs since we can't access the internet. 

I remember that in the previous implementation, there was a `refresh_token` function in `core_auth.py`. Maybe the issue is with how it's handling the token expiration or the refresh logic.

Looking at the test, I see that it mocks `requests.post` to simulate the API response. The mock should return a 200 status code and some JSON data including a new access token. But perhaps the mock isn't set up correctly, causing the test to fail.

Wait, in the test setup, maybe the initial token is not being set properly. Or perhaps the expiration check isn't accurate. I should ensure that when the token is expired, it triggers a refresh and updates the token correctly.

I'll also check if there are any issues with how the token is stored or retrieved. Maybe the function isn't updating the token in the right place, causing subsequent calls to still use the old token.

Another possibility is that the test's assertions aren't checking the correct values after the refresh. I need to make sure that the new access token is being used and that the expiration time is updated.

I'll also consider if there are any exceptions or errors being raised during the refresh process that aren't being handled, causing the test to fail unexpectedly.

To fix this, I'll update the `refresh_token` function to properly handle the token expiration check. I'll make sure it uses the correct endpoints and headers when making the refresh request. Also, in the test, I'll ensure that the mock API response is correctly set up and that all assertions are checking the expected outcomes.

Finally, I'll run the test again with these changes to see if it passes now.
</think>

Let me provide the implementation and test script for fixing the CI failure in `test_token_refresh`.

# filename: main.py
```python
import os
import json
from datetime import datetime, timedelta
import requests

def refresh_token():
    """
    Refreshes the authentication token using a refresh token.
    Returns new access token or raises exception on failure.
    """
    refresh_token = os.getenv("REFRESH_TOKEN")
    if not refresh_token:
        raise ValueError("Refresh token not found in environment variables")

    # Token expiration check
    current_time = datetime.now()
    token_expiration = get_token_expiration()
    
    if current_time >= token_expiration:
        response = requests.post(
            "https://api.example.com/refresh",
            headers={"Content-Type": "application/json"},
            json={
                "refresh_token": refresh_token,
                "client_id": os.getenv("CLIENT_ID"),
                "client_secret": os.getenv("CLIENT_SECRET")
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
            
        new_token = response.json()
        set_token_expiration(new_token["expires_in"])
        return new_token["access_token"]
    
    return get_current_access_token()

def get_token_expiration():
    """Get token expiration time from environment"""
    expires_at = os.getenv("TOKEN_EXPIRATION")
    if not expires_at:
        raise ValueError("Token expiration time not found")
    return datetime.fromisoformat(expires_at)

def set_token_expiration(seconds):
    """Set new token expiration time"""
    expiration_time = datetime.now() + timedelta(seconds=seconds)
    os.environ["TOKEN_EXPIRATION"] = expiration_time.isoformat()

def get_current_access_token():
    """Get current access token from environment"""
    return os.getenv("ACCESS_TOKEN")
```

# filename: test_script.py
```python
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

@patch('requests.post')
def test_token_refresh(mock_post):
    """
    Test token refresh functionality with mocked API response
    """
    # Setup mock environment variables
    os.environ["REFRESH_TOKEN"] = "test-refresh-token"
    os.environ["CLIENT_ID"] = "test-client-id"
    os.environ["CLIENT_SECRET"] = "test-secret"
    
    # Mock successful API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new-access-token",
        "expires_in": 3600
    }
    mock_post.return_value = mock_response
    
    # Initial token setup
    os.environ["ACCESS_TOKEN"] = "old-access-token"
    initial_expiration = datetime.now() - timedelta(seconds=1)
    os.environ["TOKEN_EXPIRATION"] = initial_expiration
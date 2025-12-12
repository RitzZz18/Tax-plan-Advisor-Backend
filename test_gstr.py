import requests

# Test generate OTP
url = "http://localhost:8000/api/gstr/generate-otp/"
data = {"username": "test_user", "gstin": "29AABCT1332L000"}

response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

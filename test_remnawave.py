import requests
import json
import uuid
import datetime

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1dWlkIjoiOGEzYmM1ZDYtM2ZlYi00YWU1LWI4YzEtNzMxNWFiN2ZmZTUwIiwidXNlcm5hbWUiOm51bGwsInJvbGUiOiJBUEkiLCJpYXQiOjE3ODE1NjE1MzksImV4cCI6MTA0MjE0NzUxMzl9.HgcO8YbzCklWGEOJkVpVWmNm3UshsyMo-Sa_S33EcaI"
BASE_URL = "https://panel.jointhevoid.ru/api"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def create_test_user():
    now = datetime.datetime.utcnow()
    expire_date = now + datetime.timedelta(days=5)
    
    simple_payload = {
        "username": f"Test-Squad-{uuid.uuid4().hex[:6]}",
        "status": "ACTIVE",
        "trafficLimitBytes": 0,
        "trafficLimitStrategy": "NO_RESET",
        "expireAt": expire_date.isoformat() + "Z",
        "activeInternalSquads": ["82e7d898-a7ee-4826-9f9d-ae9eb0933ed9"]
    }
    
    resp = requests.post(f"{BASE_URL}/users", headers=headers, json=simple_payload)
    print("Status:", resp.status_code)
    try:
        print("Response:", json.dumps(resp.json(), indent=2))
    except:
        print("Text:", resp.text)

if __name__ == "__main__":
    create_test_user()

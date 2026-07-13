import requests, os
api_key=os.environ.get('RW_API_KEY')
headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
users=requests.get("https://panel.jointhevoid.ru/api/users", headers=headers).json().get("response",{}).get("users",[])
test2=[u for u in users if "test2" in u.get("username", "")]
if test2:
    uuid = test2[0]["uuid"]
    print("Testing PATCH /api/users")
    payload = {
        "uuid": uuid,
        "status": "ACTIVE",
        "expireAt": "2027-01-01T00:00:00.000Z"
    }
    r = requests.patch("https://panel.jointhevoid.ru/api/users", headers=headers, json=payload)
    print("PATCH", r.status_code, r.text)

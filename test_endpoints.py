from app import create_app
import traceback

app = create_app()
app.testing = True

endpoints = [
    '/',
    '/login',
    '/register',
    '/terms',
    '/privacy',
    '/admin/login',
    '/dashboard',
    '/payment/platega/webhook',
    '/payment/pay',
    '/auth/webapp',
    '/activate-trial'
]

with app.test_client() as client:
    for ep in endpoints:
        try:
            if 'payment' in ep or 'auth/webapp' in ep or 'activate-trial' in ep:
                resp = client.post(ep)
                print(f"POST {ep} - Status {resp.status_code}")
            else:
                resp = client.get(ep)
                print(f"GET {ep} - Status {resp.status_code}")
            
            if resp.status_code >= 500:
                print(f"ERROR on {ep}: {resp.data.decode('utf-8')[:200]}")
        except Exception as e:
            print(f"CRASH on {ep}: {e}")
            traceback.print_exc()

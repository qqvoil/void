import os

with open('/Users/voil/data/void/app.py', 'r') as f:
    lines = f.readlines()

def get_lines(start, end):
    return "".join(lines[start-1:end])

os.makedirs('/Users/voil/data/void/routes', exist_ok=True)

# 1. Create utils.py
utils_content = """import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
import requests
import json
import logging
import hashlib
import hmac
import time
from flask import g, redirect, url_for, session, current_app, request, flash

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__))) if 'routes' in __file__ else os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config.get("DATABASE", DATABASE))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
    return g.db

def init_db():
    db = get_db()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()

def query_one(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchone()

def query_all(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchall()

def execute(query, params=()):
    db = get_db()
    db.execute(query, params)
    db.commit()

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if getattr(g, 'user', None) is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped_view

def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.admin_login"))
        return view(*args, **kwargs)
    return wrapped_view

"""
# Append specific remnawave functions from app.py
utils_content += get_lines(517, 588)
# Append auth helpers
utils_content += get_lines(305, 329)
utils_content += get_lines(358, 380)

with open('/Users/voil/data/void/utils.py', 'w') as f:
    f.write(utils_content)

# 2. Create extensions.py
extensions_content = """from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="memory://"
)
"""
with open('/Users/voil/data/void/extensions.py', 'w') as f:
    f.write(extensions_content)

# 3. Create routes/main.py
main_content = """import os
from flask import Blueprint, render_template, send_from_directory, current_app, redirect, url_for, session
main_bp = Blueprint('main', __name__)

""" + get_lines(169, 187)
main_content = main_content.replace("@app.route", "@main_bp.route").replace("admin_panel", "admin.admin_panel")
with open('/Users/voil/data/void/routes/main.py', 'w') as f:
    f.write(main_content)

# 4. Create routes/auth.py
auth_content = """import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from utils import query_one, execute, check_telegram_authorization, check_webapp_authorization
from extensions import limiter, csrf
import logging

auth_bp = Blueprint('auth', __name__)

""" + get_lines(223, 304) + get_lines(330, 357) + get_lines(381, 442) + get_lines(743, 752) + get_lines(766, 790)
auth_content = auth_content.replace("@app.route", "@auth_bp.route")
auth_content = auth_content.replace('url_for("dashboard")', 'url_for("dashboard.dashboard")')
auth_content = auth_content.replace('url_for("login")', 'url_for("auth.login")')
with open('/Users/voil/data/void/routes/auth.py', 'w') as f:
    f.write(auth_content)

# 5. Create routes/payment.py
payment_content = """import os
import json
import requests
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, redirect, url_for, flash, g
from utils import query_one, execute, login_required, get_remnawave_squad_uuid, remnawave_create_or_extend_user
from extensions import csrf
import logging

payment_bp = Blueprint('payment', __name__)

""" + get_lines(443, 516) + get_lines(589, 742)
payment_content = payment_content.replace("@app.route", "@payment_bp.route")
payment_content = payment_content.replace('url_for("dashboard")', 'url_for("dashboard.dashboard")')
with open('/Users/voil/data/void/routes/payment.py', 'w') as f:
    f.write(payment_content)

# 6. Create routes/dashboard.py
dashboard_content = """import os
from flask import Blueprint, render_template, request, session, redirect, url_for, g
from utils import login_required, query_one, execute
from extensions import limiter

dashboard_bp = Blueprint('dashboard', __name__)

""" + get_lines(189, 216) + get_lines(753, 765) + get_lines(791, 816)
dashboard_content = dashboard_content.replace("@app.route", "@dashboard_bp.route")
dashboard_content = dashboard_content.replace('url_for("dashboard")', 'url_for("dashboard.dashboard")')
dashboard_content = dashboard_content.replace('url_for("login")', 'url_for("auth.login")')

# Need to copy render_instruction_page helper to dashboard.py since it's used there
inst_helper = """
TEMPLATES_DIR = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "templates")
def render_instruction_page(template_name):
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if os.path.exists(template_path):
        return render_template(template_name)
    return render_template("inst-landing.html")

"""
dashboard_content = dashboard_content.replace("dashboard_bp = Blueprint('dashboard', __name__)\n", "dashboard_bp = Blueprint('dashboard', __name__)\n" + inst_helper)

with open('/Users/voil/data/void/routes/dashboard.py', 'w') as f:
    f.write(dashboard_content)

# 7. Create routes/admin.py
admin_content = """import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import requests
from utils import admin_required, query_one, query_all, execute
import logging

admin_bp = Blueprint('admin', __name__)

ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

""" + get_lines(817, 997)
admin_content = admin_content.replace("@app.route", "@admin_bp.route")
admin_content = admin_content.replace('url_for("admin_panel")', 'url_for("admin.admin_panel")')
admin_content = admin_content.replace('url_for("admin_login")', 'url_for("admin.admin_login")')
with open('/Users/voil/data/void/routes/admin.py', 'w') as f:
    f.write(admin_content)

# 8. Create new app.py
app_content = """import os
from datetime import datetime, timedelta, timezone
from flask import Flask, g, request, session
from extensions import csrf, limiter
from utils import close_db, query_one, execute

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config["DATABASE"] = os.path.join(BASE_DIR, "users.db")
    
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    csrf.init_app(app)
    limiter.init_app(app)

    @app.teardown_appcontext
    def teardown_db(error=None):
        close_db(error)

    @app.before_request
    def load_logged_in_user():
        ref = request.args.get("ref")
        if ref and ref.isdigit():
            session["ref"] = ref

        user_id = session.get("user_id")
        g.user = None

        if user_id:
            user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
            if user:
                status = user["status"]
                expires_at = user["expires_at"]
                if status in ("active", "trial") and expires_at:
                    try:
                        exp_dt = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) > exp_dt:
                            execute("UPDATE users SET status = 'expired' WHERE id = ?", (user_id,))
                            user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
                    except Exception:
                        pass
            g.user = user

    CONTACT_TELEGRAM = os.environ.get("CONTACT_TELEGRAM", "@yourcontact")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@example.com")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "+49 000 000 0000")

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "contact_telegram": CONTACT_TELEGRAM,
            "contact_email": CONTACT_EMAIL,
            "contact_phone": CONTACT_PHONE,
        }

    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.payment import payment_bp
    from routes.dashboard import dashboard_bp
    from routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
"""
with open('/Users/voil/data/void/app.py', 'w') as f:
    f.write(app_content)

print("Refactoring complete.")

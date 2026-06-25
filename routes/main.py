import os
from flask import Blueprint, render_template, send_from_directory, current_app, redirect, url_for, session
main_bp = Blueprint('main', __name__)

@main_bp.route("/terms")
def terms():
    return render_template("terms.html")

@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")

@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static', 'img'),
                               'favicon.jpg', mimetype='image/jpeg')

@main_bp.route("/")
def index():
    if session.get("is_admin"):
        return redirect(url_for("admin.admin_panel"))
    return render_template("index.html")


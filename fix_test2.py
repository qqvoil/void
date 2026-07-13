import os
import sqlite3
from flask import Flask
import utils
from routes.payment import add_subscription

app = Flask(__name__)
app.config['DATABASE'] = '/opt/void/users.db'

def get_db():
    db = sqlite3.connect('/opt/void/users.db')
    db.row_factory = sqlite3.Row
    return db

utils.get_db = get_db

with app.app_context():
    add_subscription(33, 30)
    print("Fixed test2")

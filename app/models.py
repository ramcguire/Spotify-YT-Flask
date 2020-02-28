from datetime import datetime
from flask_login import UserMixin
from sqlalchemy_utils import JSONType
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    job_ref = db.Column(db.String(36), index=True)
    current_job = db.relationship('Job', backref='user', lazy='dynamic')
    

    def __repr__(self):
        return "<User {}>".format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Job(db.Model):
    id = db.Column(db.String(36), index=True, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    result = db.Column(JSONType)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return "<Job {}>".format(self.id)

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    StringField,
    TextField,
    SubmitField,
    PasswordField,
)
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError

from app.models import User


class YTPlaylistName(FlaskForm):
    name = TextField("Playlist Name", validators=[DataRequired()])
    submit = SubmitField("Submit")


class SpotifyPlaylistSearch(FlaskForm):
    playlist = TextField(
        "Enter Spotify playlist URL or ID", validators=[DataRequired()]
    )
    btnSubmit = SubmitField("Enter")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")

class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password', "Passwords must match.")])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError("Username is unavailable.")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError("Email is already registered.")
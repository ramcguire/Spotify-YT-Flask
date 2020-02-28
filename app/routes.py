import json

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import requests
from flask import (flash, jsonify, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.urls import url_parse

from app import app, db
from app.forms import (LoginForm, RegistrationForm, SpotifyPlaylistSearch,
                       YTPlaylistName)
from app.models import Job, User
from app.tasks import scrape_spotify


@app.route("/")
@app.route("/index")
def index():
    if current_user.is_authenticated:
        return render_template("home.html")
    return redirect(url_for('login'))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("spotify"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password")
            return redirect(url_for("login"))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        if not next_page or url_parse(next_page).netloc != "":
            next_page = url_for("index")
        return redirect(next_page)
    return render_template("login.html", title="Log In", form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("spotify"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("You are now registerd, please log in.")
        return redirect(url_for("login"))
    return render_template("register.html", title="Register", form=form)


@app.route("/spotify", methods=["POST", "GET"])
@login_required
def spotify():
    form = SpotifyPlaylistSearch()
    return render_template(
        "select_spotify.html", form=form, title="Spotify Converter"
    )


@app.route("/scrape_spotify", methods=["POST"])
@login_required
def start_spotify_search():
    input_str = request.form["playlist"]
    task = scrape_spotify.delay(input_str)
    task_description = Job(id=task.id, user_id=current_user.id)
    current_user.job_ref = task.id
    db.session.add(task_description)
    db.session.commit()

    return (
        jsonify({}),
        202,
        {"Location": url_for("task_status", task_id=task.id)},
    )


@app.route("/task-status/<task_id>")
def task_status(task_id):
    task = scrape_spotify.AsyncResult(task_id)

    if task.state == "PENDING":
        # job hasn't started yet
        response = {
            "state": task.state,
            "current": 0,
            "total": 1,
            "status": "Pending...",
        }

    if task.state == "SUCCESS":
        this_task = Job.query.get(task_id)
        this_task.result = task.get()
        db.session.commit()

        response = {
            "state": task.state,
            "current": 1,
            "total": 1,
            "status": "Success!",
        }
        return response

    elif task.state != "FAILURE":
        response = {
            "state": task.state,
            "current": task.info.get("current", 0),
            "total": task.info.get("total", 1),
            "status": task.info.get("status", ""),
        }

    else:
        # if something goes wrong
        response = {
            "state": task.state,
            "current": 1,
            "total": 1,
            "status": str(task.info),
        }

    return jsonify(response)


@app.route("/show_songs", methods=["GET"])
def display_spotify_songs():
    # Render table displaying songs found.
    # Use session variable to find songs
    result = Job.query.get(current_user.job_ref).result
    return render_template(
        "show_songs.html", songs=result
    )


@app.route("/create_playlist", methods=["POST", "GET"])
def yt_create_playlist():

    # if playlist name was submitted using POST
    if request.method == "POST":
        if "credentials" not in session:
            return redirect("authorize")

        # Load credentials from the session.
        credentials = google.oauth2.credentials.Credentials(
            **session["credentials"]
        )
        # Create a youtube object
        youtube = googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )
        result = request.form

        yt_create_playlist = youtube.playlists().insert(
            part="snippet",
            body={
                "snippet": {
                    "title": result["name"],
                    "description": "Imported using Music Transfer",
                }
            },
        )
        response = yt_create_playlist.execute()

        # Save credentials back to session in case access token was refreshed.
        # ACTION ITEM: In a production app, you likely want to save these
        #              credentials in a persistent database instead.
        session["credentials"] = credentials_to_dict(credentials)

        return response["id"]

    form = YTPlaylistName()
    return render_template("create_playlist.html", form=form)

# ---------------------------------------------------------------------------
# ---------------------------Google/Youtube Auth-----------------------------
# ---------------------------------------------------------------------------
@app.route("/test")
def test_api_request():
    if "credentials" not in session:
        return redirect("authorize")

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **session["credentials"]
    )

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials
    )

    channel = youtube.channels().list(mine=True, part="snippet").execute()

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    session["credentials"] = credentials_to_dict(credentials)

    return jsonify(**channel)


@app.route("/authorize")
def authorize():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )

    flow.redirect_uri = url_for("oauth2callback", _external=True)

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type="offline",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )

    # Store the state so the callback can verify the auth server response.
    session["state"] = state

    return redirect(authorization_url)


@app.route("/oauth2callback")
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = session["state"]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = url_for("oauth2callback", _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    session["credentials"] = credentials_to_dict(credentials)

    return redirect(url_for("test_api_request"))


@app.route("/revoke")
def revoke():
    if "credentials" not in session:
        return (
            'You need to <a href="/authorize">authorize</a> before '
            + "testing the code to revoke credentials."
        )

    credentials = google.oauth2.credentials.Credentials(
        **session["credentials"]
    )

    revoke = requests.post(
        "https://accounts.google.com/o/oauth2/revoke",
        params={"token": credentials.token},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    status_code = getattr(revoke, "status_code")
    if status_code == 200:
        return "Credentials successfully revoked." + print_index_table()
    else:
        return "An error occurred." + print_index_table()


@app.route("/clear")
def clear_credentials():
    if "credentials" in session:
        del session["credentials"]
    return "Credentials have been cleared.<br><br>" + print_index_table()


@app.route("/main")
def print_sidebar_page():
    return render_template(
        "main.html",
        full_test="/test",
        auth_test="/authorize",
        revoke_credentials="/revoke",
        clear_credentials="/clear",
    )


def credentials_to_dict(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def print_index_table():
    return (
        "<table>"
        + '<tr><td><a href="/test">Test an API request</a></td>'
        + "<td>Submit an API request and see a formatted JSON response. "
        + "    Go through the authorization flow if there are no stored "
        + "    credentials for the user.</td></tr>"
        + '<tr><td><a href="/authorize">Test the auth flow directly</a></td>'
        + "<td>Go directly to the authorization flow. If there are stored "
        + "    credentials, you still might not be prompted to reauthorize "
        + "    the application.</td></tr>"
        + '<tr><td><a href="/revoke">Revoke current credentials</a></td>'
        + "<td>Revoke the access token associated with the current user "
        + "    session. After revoking credentials, if you go to the test "
        + "    page, you should see an <code>invalid_grant</code> error."
        + "</td></tr>"
        + '<tr><td><a href="/clear">Clear Flask session credentials</a></td>'
        + "<td>Clear the access token currently stored in the user session. "
        + '    After clearing the token, if you <a href="/test">test the '
        + "    API request</a> again, you should go back to the auth flow."
        + "</td></tr></table>"
    )

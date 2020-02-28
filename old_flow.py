#!/usr/bin/python3
import os

import flask
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import requests
from flask_bs4 import Bootstrap

import MySpotify
from MyForms import SpotifyPlaylistSearch, YTPlaylistName
from tasks import scrape_spotify

async_mode = None

# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client_secret.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


app = flask.Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See http://flask.pocoo.org/docs/0.12/quickstart/#sessions.
app.secret_key = "REPLACE ME - this value is here as a placeholder."
Bootstrap(app)

app.config["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
app.config["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"


@app.route("/")
def index():
    return print_index_table()


@app.route("/test")
def test_api_request():
    if "credentials" not in flask.session:
        return flask.redirect("authorize")

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **flask.session["credentials"]
    )

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials
    )

    channel = youtube.channels().list(mine=True, part="snippet").execute()

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    flask.session["credentials"] = credentials_to_dict(credentials)

    return flask.jsonify(**channel)


@app.route("/spotify", methods=["POST", "GET"])
def find_spotify():
    form = SpotifyPlaylistSearch()
    return flask.render_template(
        "select_spotify.html", form=form, div_name="none"
    )


@app.route("/scrape_spotify", methods=["POST"])
# TODO: Make secure (logged in)
def start_spotify_search():
    input_str = flask.request.form["playlist"]
    task = scrape_spotify.delay(input_str)

    return (
        flask.jsonify({}),
        202,
        {"Location": flask.url_for("task_status", task_id=task.id)},
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
        flask.session["spotify_playlist"] = task.result
        response = {
            "state": task.state,
            "current": 1,
            "total": 1,
            "status": "Success!",
        }

    elif task.state != "FAILURE":
        response = {
            "state": task.state,
            "current": task.info.get("current", 0),
            "total": task.info.get("total", 1),
            "status": task.info.get("status", ""),
        }
        if task.state == "SUCCESS":
            flask.session["spotify_playlist"] = task.result

    else:
        # if something goes wrong
        response = {
            "state": task.state,
            "current": 1,
            "total": 1,
            "status": str(task.info),  # exception raised
        }

    return flask.jsonify(response)


@app.route("/searching_spotify", methods=["POST", "GET"])
def searching_spotify():
    # Scrape spotify playlist for required song information
    playlist = flask.request.form["playlist"]
    playlist_id = MySpotify.select_playlist(playlist)
    playlist_summary = MySpotify.get_playlist_summary(playlist_id)
    playlist_tracks = MySpotify.get_playlist_tracks(playlist_summary)
    # Store list of songs in flask session
    flask.session["spotify_playlist"] = playlist_tracks
    return flask.render_template("show_songs.html", songs=playlist_tracks)


@app.route("/show_songs", methods=["GET"])
def display_spotify_songs():
    # Render table displaying songs found.
    # Use session variable to find songs
    return flask.render_template(
        "show_songs.html", songs=flask.session["spotify_playlist"]
    )


@app.route("/create_playlist", methods=["POST", "GET"])
def yt_create_playlist():

    # if playlist name was submitted using POST
    if flask.request.method == "POST":
        if "credentials" not in flask.session:
            return flask.redirect("authorize")

        # Load credentials from the session.
        credentials = google.oauth2.credentials.Credentials(
            **flask.session["credentials"]
        )
        # Create a youtube object
        youtube = googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )
        result = flask.request.form

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
        flask.session["credentials"] = credentials_to_dict(credentials)

        return response["id"]

    form = YTPlaylistName()
    return flask.render_template("create_playlist.html", form=form)


@app.route("/authorize")
def authorize():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow
    # steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )

    flow.redirect_uri = flask.url_for("oauth2callback", _external=True)

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server
        # apps.
        access_type="offline",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )

    # Store the state so the callback can verify the auth server response.
    flask.session["state"] = state

    return flask.redirect(authorization_url)


@app.route("/oauth2callback")
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = flask.session["state"]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = flask.url_for("oauth2callback", _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    flask.session["credentials"] = credentials_to_dict(credentials)

    return flask.redirect(flask.url_for("test_api_request"))


@app.route("/revoke")
def revoke():
    if "credentials" not in flask.session:
        return (
            'You need to <a href="/authorize">authorize</a> before '
            + "testing the code to revoke credentials."
        )

    credentials = google.oauth2.credentials.Credentials(
        **flask.session["credentials"]
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
    if "credentials" in flask.session:
        del flask.session["credentials"]
    return "Credentials have been cleared.<br><br>" + print_index_table()


@app.route("/main")
def print_sidebar_page():
    return flask.render_template(
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


if __name__ == "__main__":
    # When running locally, disable OAuthlib's HTTPs verification.
    # ACTION ITEM for developers:
    #     When running in production *do not* leave this option enabled.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    # Specify a hostname and port that are set as a valid redirect URI
    # for your API project in the Google API Console.
    # host='0.0.0.0' for use on WSL2
app.run(host="0.0.0.0", port=8080, debug=False)


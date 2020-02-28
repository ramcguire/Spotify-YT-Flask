import MySpotify
from celery import Celery


CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

celery = Celery(
    "tasks", backend=CELERY_RESULT_BACKEND, broker=CELERY_BROKER_URL
)


@celery.task(bind=True)
# returns list of songs - artists - song length
def scrape_spotify(self, playlist):
    current_prog = 5
    self.update_state(
        state="PROGRESS",
        meta={
            "current": current_prog,
            "total": 100,
            "status": "Looking for playlist...",
        },
    )
    playlist_id = MySpotify.select_playlist(playlist)
    playlist_summary = MySpotify.get_playlist_summary(playlist_id)
    current_prog = 10
    self.update_state(
        state="PROGRESS",
        meta={
            "current": current_prog,
            "total": 100,
            "status": "Playlist found.",
        },
    )
    # this one takes longer, maybe bring code into function here to update
    # status of task
    num_loops = MySpotify.get_loops(playlist_summary)
    iter_prog = 90 / num_loops
    spotify_client = MySpotify.get_spotify_client()
    step = 100
    offset = 0
    playlist_tracks = []
    for i in range(0, num_loops):
        self.update_state(
            state="PROGRESS",
            meta={
                "current": current_prog,
                "total": 100,
                "status": "Getting songs...",
            },
        )
        result = spotify_client.user_playlist_tracks(
            user=playlist_summary["owner"]["id"],
            playlist_id=playlist_summary["id"],
            limit=step,
            offset=offset,
        )
        playlist_query = MySpotify.scrape_songs(result["items"])
        for song_item in playlist_query:
            playlist_tracks.append(song_item)
        offset += step
        current_prog += iter_prog

    return playlist_tracks

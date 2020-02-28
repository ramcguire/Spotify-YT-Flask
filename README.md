# Spotify-YT-Flask
 Implementation of my Spotify-YT-Convert program into a full stack web application using Flask. Uses SQLAlchemy to provide easy SQL manipulation.
 
 Features:
 * User registration
 * Spotify playlist searching and scraping
 
 TODO:
 * Match Spotify songs to videos (similar to Spotify-YT-Convert)
 * Allow Google sign in
 * Create a new playlist under signed in Google account
 * Add matched videos to Youtube account
 
 Uses Redis and Celery for background job processing to keep server responsive. Progress of tasks shown through API endpoint and Javascript progress bar nanobar.
 
 Work in progress. Currently does not connect to Youtube to create a playlist.

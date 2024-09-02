from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import requests
import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging
# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Allow CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Read the Spotify API token from the environment variable
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

# Spotify scopes
SCOPE = "user-top-read user-read-recently-played"

# Create SpotifyOAuth instance
sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SCOPE
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/dashboard", response_class=HTMLResponse)
async def get_recommendations(request: Request):
    token_info = sp_oauth.get_cached_token()
    logger.info(f"Dashboard Access Token: {token_info.get('access_token')}")
    if not token_info:
        return RedirectResponse(url="/error.html")
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    try:
        top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')
        top_tracks_ids = [track['id'] for track in top_tracks['items']]
        
        recommendations = sp.recommendations(seed_tracks=top_tracks_ids, limit=5)
        
        # Extract relevant information from recommendations
        simplified_recommendations = [
            {
                "name": track["name"],
                "artists": [{"name": artist["name"]} for artist in track["artists"]],
                "id": track["id"]
            }
            for track in recommendations["tracks"]
        ]
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "recommendations": simplified_recommendations
        })
    except spotipy.exceptions.SpotifyException as e:
        logger.error(f"Spotify API error: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Failed to fetch data from Spotify. Please try logging in again."
        })

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    auth_url = sp_oauth.get_authorize_url()
    return templates.TemplateResponse("login.html", {"request": request, "auth_url": auth_url})


@app.get("/", response_class=HTMLResponse)
async def hello_world(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/track-audio-analysis/{track_id}")
async def fetch_track_audio_analysis(track_id: str):
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    try:
        analysis = sp.audio_analysis(track_id)
        return analysis
    except spotipy.exceptions.SpotifyException as e:
        logger.error(f"Spotify API error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/recommend", response_class=HTMLResponse)
async def recommend_form(request: Request):
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        return RedirectResponse(url="/error.html")
    return templates.TemplateResponse("recommend_form.html", {"request": request})

@app.post("/recommend", response_class=HTMLResponse)
async def process_recommendation(
    request: Request,
    genre: str = Form(...),
    energy: float = Form(...),
    danceability: float = Form(...),
    valence: float = Form(...),
    acousticness: float = Form(...),
    instrumentalness: float = Form(...),
    popularity: int = Form(...),
    tempo: float = Form(...)
):
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        return RedirectResponse(url="/error.html")
    
    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    try:
        # Get user's top tracks
        top_tracks = sp.current_user_top_tracks(limit=2, time_range='short_term')
        
        # Debug: Print the top_tracks response
        logger.info(f"Top tracks response: {top_tracks}")
        
        if 'items' not in top_tracks:
            error_message = f"Error: Unable to fetch top tracks. API response: {top_tracks}"
            return templates.TemplateResponse("error.html", {"request": request, "error_message": error_message})
        
        seed_tracks = [track['id'] for track in top_tracks['items']]

        # Get recommendations based on user's top tracks and answers
        recommendations = sp.recommendations(
            seed_tracks=seed_tracks,
            seed_genres=[genre],
            limit=10,
            target_energy=energy,
            target_danceability=danceability,
            target_valence=valence,
            target_acousticness=acousticness,
            target_instrumentalness=instrumentalness,
            target_popularity=popularity,
            target_tempo=tempo
        )

        # Debug: Print the recommendations response
        logger.info(f"Recommendations response: {recommendations}")

        if 'tracks' not in recommendations:
            error_message = f"Error: Unable to fetch recommendations. API response: {recommendations}"
            return templates.TemplateResponse("error.html", {"request": request, "error_message": error_message})

        return templates.TemplateResponse("recommendations.html", {
            "request": request,
            "recommendations": recommendations['tracks']
        })
    except spotipy.exceptions.SpotifyException as e:
        logger.error(f"Spotify API error: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": f"Failed to fetch data from Spotify: {str(e)}"
        })

@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    
    try:
        token_info = sp_oauth.get_access_token(code)
        
        # Here you might want to store the token_info in a session or database
        return RedirectResponse(url="/dashboard", status_code=307)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error exchanging code for token: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)

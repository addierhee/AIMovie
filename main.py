import streamlit as st
import tmdbsimple as tmdb
from serpapi import GoogleSearch
import sqlite3
import hashlib
import boto3
import json
import os
from dotenv import load_dotenv

# ========== Load Environment ==========
load_dotenv()

tmdb.API_KEY = os.getenv("TMDB_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

bedrock = boto3.client("bedrock-runtime")  # uses credentials from `aws configure`


# ========== Initialize SQLite ==========
with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            username TEXT,
            title TEXT,
            rating TEXT,
            summary TEXT,
            available_on TEXT,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (username, title)
        )
    ''')
    conn.commit()

# ========== Auth ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def signup_user(username, password):
    with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, hash_password(password)))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def login_user(username, password):
    with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
        result = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
        return result and result[0] == hash_password(password)

# ========== Session Auth ==========
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""

# ========== Login UI ==========
if not st.session_state.authenticated:
    st.title("🎬 AI Movie Assistant - Login")

    mode = st.radio("Choose mode", ["Login", "Sign Up"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if mode == "Login":
        if st.button("Login"):
            if login_user(username, password):
                st.session_state.authenticated = True
                st.session_state.current_user = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials.")
    else:
        if st.button("Sign Up"):
            if signup_user(username, password):
                st.success("Account created! Please log in.")
            else:
                st.warning("Username already exists.")
    st.stop()

# ========== Claude Helpers ==========
def ask_claude(prompt):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}]
    }
    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        body=json.dumps(body)
    )
    result = json.loads(response['body'].read())
    return result["content"][0]["text"].strip()

def ask_claude_for_streaming_info(snippets, title):
    prompt = (
        f"Based on these web search snippets, where can I stream or watch the movie or tv show '{title}'?\n\n"
        f"{snippets}\n\n"
        "List only the streaming platforms or services. If unknown, say 'Not found'."
    )
    return ask_claude(prompt)

def ask_claude_for_genre_recs(genre_prompt):
    prompt = (
        f"List 5 great movies in the genre or theme: '{genre_prompt}'. "
        "Return only the movie titles, comma-separated."
    )
    result = ask_claude(prompt)
    return [t.strip() for t in result.split(',')]

def get_claude_personal_recommendations(username):
    with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
        titles = conn.execute("SELECT title FROM watchlist WHERE username = ?", (username,)).fetchall()

    if not titles:
        return []

    title_list = ", ".join(t[0] for t in titles)
    prompt = (
        f"The user has saved these movies to their watchlist: {title_list}. "
        "Based on their taste, recommend 5 more movies. Return only the movie titles, comma-separated."
    )
    result = ask_claude(prompt)
    return [t.strip() for t in result.split(',')]

# ========== SerpAPI ==========
def search_snippets_from_serpapi(query):
    search = GoogleSearch({
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5
    })
    results = search.get_dict()
    snippets = [r["snippet"] for r in results.get("organic_results", []) if "snippet" in r]
    return "\n".join(snippets) or "No useful search results found."

def get_streaming_info(title):
    snippets = search_snippets_from_serpapi(f"Where can I watch {title} streaming")
    return [s.strip() for s in ask_claude_for_streaming_info(snippets, title).split(',')]

# ========== TMDB Info ==========
def is_in_watchlist(username, title):
    with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
        result = conn.execute("SELECT 1 FROM watchlist WHERE username = ? AND title = ?", (username, title)).fetchone()
        return result is not None

def get_movie_info(title):
    search = tmdb.Search()
    response = search.movie(query=title)
    if not response['results']:
        return None

    movie = response['results'][0]
    movie_id = movie['id']
    details = tmdb.Movies(movie_id).info()

    return {
        "title": details.get('title', title),
        "summary": details.get('overview', 'No summary available.'),
        "rating": details.get('vote_average', 'N/A'),
        "poster_url": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get('poster_path') else None,
        "genres": [g['name'] for g in details.get('genres', [])],
        "similar_titles": [m['title'] for m in tmdb.Movies(movie_id).similar_movies()['results'][:5]],
        "available_on": get_streaming_info(title)
    }

# ========== UI ==========
st.title("🎥 AI Movie Assistant")

mode = st.selectbox("Choose a mode:", [
    "Search by Movie/TV Title", 
    "Need Help Finding Something to Watch? Input a Genre?"
])

if mode == "Search by Movie/TV Title":
    title_input = st.text_input("Enter a movie/tv title:")
    if st.button("Search") and title_input:
        with st.spinner("Fetching info..."):
            info = get_movie_info(title_input)
            st.session_state["movie_info"] = info
            st.session_state.pop("claude_recs", None)
            st.session_state.pop("personal_recs", None)

elif mode == "Need Help Finding Something to Watch? Input a Genre?":
    genre_input = st.text_input("Genre: e.g. 'feel-good romantic comedy'")
    if st.button("Get Recs") and genre_input:
        with st.spinner("Finding Your Picks..."):
            titles = ask_claude_for_genre_recs(genre_input)
            st.session_state["claude_recs"] = titles
            st.session_state.pop("movie_info", None)
            st.session_state.pop("personal_recs", None)

# ========== Claude Recommendations ==========
if "claude_recs" in st.session_state and mode == "Need Help Finding Something to Watch? Input a Genre?":
    st.subheader("Recommended Movies:")
    for t in st.session_state["claude_recs"]:
        st.markdown(f"• {t}")

# ========== Show Movie Info ==========
info = st.session_state.get("movie_info")
if info:
    st.subheader(info['title'])
    if info['poster_url']:
        st.image(info['poster_url'], use_container_width=True)

    st.write(f"**Rating:** {info['rating']}")
    st.write(f"**Genres:** {', '.join(info['genres'])}")
    st.write(f"**Summary:** {info['summary']}")
    st.write(f"**Available On:** {', '.join(info['available_on'])}")
    st.write("**Similar Titles:**")
    st.write(", ".join(info['similar_titles']))

    if st.button("➕ Add to Watchlist"):
        try:
            with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
                conn.execute(
                    "INSERT INTO watchlist (username, title, rating, summary, available_on) VALUES (?, ?, ?, ?, ?)",
                    (
                        st.session_state.current_user,
                        info["title"],
                        str(info["rating"]),
                        info["summary"],
                        ", ".join(info["available_on"])
                    )
                )
                conn.commit()
            st.success("Added to watchlist!")
        except sqlite3.IntegrityError:
            st.warning("Already in your watchlist.")

# ========== Watchlist Sidebar ==========
with st.sidebar.expander("📺 My Watchlist"):
    with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
        watchlist = conn.execute(
            "SELECT title, rating, summary, available_on FROM watchlist WHERE username = ?",
            (st.session_state.current_user,)
        ).fetchall()

    if not watchlist:
        st.info("Your watchlist is empty.")
    for title, rating, summary, available_on in watchlist:
        st.markdown(f"**{title}** – Rating: {rating}")
        st.caption(summary)
        st.caption(f"Available on: {available_on}")
        if st.button(f"Remove '{title}'", key=title):
            with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
                conn.execute("DELETE FROM watchlist WHERE username = ? AND title = ?",
                             (st.session_state.current_user, title))
                conn.commit()
            st.rerun()

    if st.button("🗑️ Clear Watchlist"):
        with sqlite3.connect("watchlist.db", check_same_thread=False) as conn:
            conn.execute("DELETE FROM watchlist WHERE username = ?",
                         (st.session_state.current_user,))
            conn.commit()
        st.rerun()

    if st.button("🤖 Get Personalized Recs"):
        titles = get_claude_personal_recommendations(st.session_state.current_user)
        st.session_state["personal_recs"] = titles
        st.session_state.pop("movie_info", None)
        st.session_state.pop("claude_recs", None)
        st.rerun()

# ========== Show Personalized Recs ==========
if "personal_recs" in st.session_state:
    st.subheader("🎯 Personalized Recommendations")
    for t in st.session_state["personal_recs"]:
        st.markdown(f"• {t}")

# ========== Logout ==========
if st.sidebar.button("🚪 Logout"):
    st.session_state.authenticated = False
    st.session_state.current_user = ""
    st.session_state.pop("movie_info", None)
    st.session_state.pop("claude_recs", None)
    st.session_state.pop("personal_recs", None)
    st.rerun()

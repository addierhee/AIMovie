# 🎬 AI Movie Assistant

A Streamlit web app that helps you discover, research, and organize movies using AI-powered recommendations, real-time data from TMDB and Google, and Claude-generated summaries. Built with Python, SQLite, SerpAPI, TMDB API, and Amazon Bedrock.

---

## 🚀 Features

- 🔍 **Search Movies** – Get movie details including plot, rating, cast, and more
- 🧠 **AI Recommendations** – Claude (via Bedrock) suggests movies based on genre or mood
- 📍 **Streaming Info** – Find where to watch movies (e.g., Netflix, Hulu) using SerpAPI
- 📝 **Personal Watchlist** – Save your favorites to a local database
- 🧠 **Summarization** – Claude summarizes long movie descriptions
- 🔐 **User Login System** – Local user auth via SQLite & password hashing

---

## 🛠️ Tech Stack

| Tech         | Purpose                          |
|--------------|----------------------------------|
| **Python**   | Core backend logic               |
| **Streamlit**| Frontend UI                      |
| **TMDB API** | Movie metadata                   |
| **SerpAPI**  | Google scraping for streaming info|
| **Claude** (Bedrock) | AI-powered recommendations |
| **SQLite**   | Watchlist & user storage         |
| **Boto3**    | AWS Bedrock API calls            |
| **dotenv**   | Local environment variable loading|

---


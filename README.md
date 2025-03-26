# 🔥 Sierra City Fire Risk Dashboard

This project is a public-facing dashboard that calculates and displays fire risk based on real-time weather conditions.

## 🚀 Features
- Fetches temperature, humidity, and wind data from the Synoptic Data API.
- Retrieves wind gust data from multiple Weather Underground stations (KCASIERR68, KCASIERR63, KCASIERR72).
- Uses intelligent averaging of wind gust data with fallback to cached values when needed.
- Computes **fire risk levels** (Red, Yellow, Green).
- Displays the risk level on a **Bootstrap-based web dashboard**.
- Hosted on **Render** for automatic updates.

## 🛠 Setup Instructions
1. Clone the repository:
   ```zsh
   git clone https://github.com/overpitch/fire-risk-dashboard.git
   cd fire-risk-dashboard

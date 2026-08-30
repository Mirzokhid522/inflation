import os
from flask import Flask, render_template
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
FRED_API_KEY = os.getenv('FRED_API_KEY')

def fetch_fred_yoy_series(series_id):
    """Fetches pre-calculated Year-over-Year percentage changes directly from FRED API using 'units': 'pc1'."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json',
        'sort_order': 'desc',
        'units': 'pc1',  # Automatically computes Year-over-Year percent change server-side on FRED
        'limit': 24      # Generous lookback to guarantee trailing 12-month alignment
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return [], []
    
    data = response.json().get('observations', [])
    data = sorted([d for d in data if d['value'] != '.'], key=lambda x: x['date'])
    
    dates = [d['date'] for d in data]
    values = [float(d['value']) for d in data]
    return dates, values

@app.route('/')
def index():
    series_map = {
        'pce': 'PCEPI',
        'core_pce': 'PCEPILFE',
        'cpi': 'CPIAUCSL',
        'core_cpi': 'CPILFESL'
    }
    
    series_dates = {}
    series_values = {}
    
    for key, series_id in series_map.items():
        dates, vals = fetch_fred_yoy_series(series_id)
        series_dates[key] = set(dates)
        series_values[key] = dict(zip(dates, vals))

    # Intersect dates across all series and automatically slice the latest 12 months
    common_months = sorted(list(set.intersection(*map(set, series_dates.values()))))
    recent_months = common_months[-12:] if len(common_months) >= 12 else common_months

    chart_payload = {
        'months': recent_months,
        'pce': [series_values['pce'].get(m) for m in recent_months],
        'core_pce': [series_values['core_pce'].get(m) for m in recent_months],
        'cpi': [series_values['cpi'].get(m) for m in recent_months],
        'core_cpi': [series_values['core_cpi'].get(m) for m in recent_months]
    }
    
    return render_template('index.html', data=chart_payload)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
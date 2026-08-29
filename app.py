import os
from flask import Flask, render_template
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
FRED_API_KEY = os.getenv('FRED_API_KEY')

def fetch_fred_series(series_id):
    """Helper function to fetch monthly data from FRED API and calculate YoY change."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': 24  # Fetch last 24 months to easily compute 1-year (12-month) lag YoY changes
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return [], []
    
    data = response.json().get('observations', [])
    # Sort chronologically ascending
    data = sorted([d for d in data if d['value'] != '.'], key=lambda x: x['date'])
    
    dates = [d['date'] for d in data]
    values = [float(d['value']) for d in data]
    return dates, values

def get_yoy_inflation(values, dates):
    """Calculates year-over-year percentage change from the monthly index levels."""
    yoy_rates = []
    valid_dates = []
    for i in range(12, len(values)):
        val_current = values[i]
        val_year_ago = values[i - 12]
        yoy = ((val_current - val_year_ago) / val_year_ago) * 100
        yoy_rates.append(round(yoy, 2))
        valid_dates.append(dates[i])
    return valid_dates, yoy_rates

@app.route('/')
def index():
    # Fetch series IDs: PCEPI, PCEPILFE, CPIAUCSL, CPILFESL
    series_map = {
        'pce': 'PCEPI',
        'core_pce': 'PCEPILFE',
        'cpi': 'CPIAUCSL',
        'core_cpi': 'CPILFESL'
    }
    
    processed_data = {}
    common_months = []
    
    for key, series_id in series_map.items():
        dates, vals = fetch_fred_series(series_id)
        d_list, yoy_list = get_yoy_inflation(vals, dates)
        processed_data[key] = yoy_list
        common_months = d_list  # Keep the date stamps

    # Slice to get the most recent 12 months for the dashboard view
    limit_slice = 12
    recent_months = [
        # Format dates nicely (e.g., '2026-07' to readable labels if preferred)
        m for m in common_months[-limit_slice:]
    ]
    
    chart_payload = {
        'months': recent_months,
        'pce': processed_data['pce'][-limit_slice:],
        'core_pce': processed_data['core_pce'][-limit_slice:],
        'cpi': processed_data['cpi'][-limit_slice:],
        'core_cpi': processed_data['core_cpi'][-limit_slice:]
    }
    
    return render_template('index.html', data=chart_payload)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
import os
from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
FRED_API_KEY = os.getenv('FRED_API_KEY')

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def parse_fred_date(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{MONTH_SHORT[dt.month-1]} {dt.year}"

def format_release_date(date_str):
    if not date_str:
        return 'N/A'
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{MONTH_SHORT[dt.month-1]} {dt.day}, {dt.year}"
    except Exception:
        return date_str

def fetch_fred_series_meta(series_id):
    url = "https://api.stlouisfed.org/fred/series"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json'
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            seriess = response.json().get('seriess', [])
            if seriess:
                return seriess[0].get('last_updated', 'Unknown')
    except Exception as e:
        print(f"Error fetching metadata for {series_id}: {e}")
    return 'Unknown'

def fetch_fred_next_release(series_id):
    release_url = "https://api.stlouisfed.org/fred/series/release"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json'
    }
    try:
        res = requests.get(release_url, params=params)
        if res.status_code != 200:
            return 'N/A'
        
        releases = res.json().get('releases', [])
        if not releases:
            return 'N/A'
            
        release_id = releases[0].get('id')
        
        dates_url = "https://api.stlouisfed.org/fred/release/dates"
        today_str = datetime.now().strftime('%Y-%m-%d')
        date_params = {
            'release_id': release_id,
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'include_release_dates_with_no_data': 'true',
            'realtime_start': today_str,
            'limit': 5,
            'sort_order': 'asc'
        }
        
        d_res = requests.get(dates_url, params=date_params)
        if d_res.status_code == 200:
            release_dates = d_res.json().get('release_dates', [])
            for rd in release_dates:
                r_date = rd.get('date')
                if r_date and r_date >= today_str:
                    return format_release_date(r_date)
                    
            if release_dates:
                return format_release_date(release_dates[0].get('date'))
    except Exception as e:
        print(f"Error fetching next release date for {series_id}: {e}")
        
    return 'N/A'

def fetch_fred_series(series_id, units_type):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json',
        'sort_order': 'desc',
        'units': units_type,
        'limit': 12
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return [], []
    
    data = response.json().get('observations', [])
    data = sorted([d for d in data if d['value'] != '.'], key=lambda x: x['date'])
    
    dates = [d['date'] for d in data]
    values = [float(d['value']) for d in data]
    return dates, values

def fetch_cleveland_nowcasts():
    url = "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    nowcasts = {
        'mom': {},
        'yoy': {},
        'updated_date': ''
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return nowcasts
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        page_text = soup.get_text()
        for line in page_text.split('\n'):
            if "Updated:" in line:
                nowcasts['updated_date'] = line.strip()
                break

        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text().upper()
            is_mom = "MONTH-OVER-MONTH" in table_text
            is_yoy = "YEAR-OVER-YEAR" in table_text
            
            if not (is_mom or is_yoy):
                continue
                
            rows = table.find_all('tr')
            for row in rows[1:]:
                cols = [c.text.strip() for c in row.find_all(['td', 'th'])]
                if len(cols) >= 6:
                    month_str = cols[0]
                    try:
                        cpi_val = float(cols[1]) if cols[1] else None
                        core_cpi_val = float(cols[2]) if cols[2] else None
                        pce_val = float(cols[3]) if cols[3] else None
                        core_pce_val = float(cols[4]) if cols[4] else None
                        updated_val = cols[5]
                        
                        target_dict = nowcasts['mom'] if is_mom else nowcasts['yoy']
                        target_dict[month_str] = {
                            'cpi': cpi_val,
                            'core_cpi': core_cpi_val,
                            'pce': pce_val,
                            'core_pce': core_pce_val,
                            'updated': updated_val
                        }
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Error fetching Cleveland nowcasts: {e}")
        
    return nowcasts

@app.route('/')
def index():
    series_map = {
        'cpi': ('CPIAUCSL', 'cpi'),
        'core_cpi': ('CPILFESL', 'core_cpi'),
        'pce': ('PCEPI', 'pce'),
        'core_pce': ('PCEPILFE', 'core_pce')
    }
    
    nowcasts = fetch_cleveland_nowcasts()
    payload = {'nowcasts': nowcasts, 'charts': {}}
    
    for key, (fred_id, col_name) in series_map.items():
        fred_updated = fetch_fred_series_meta(fred_id)
        next_release = fetch_fred_next_release(fred_id)
        
        for freq in ['yoy', 'mom']:
            units = 'pc1' if freq == 'yoy' else 'pch'
            dates, vals = fetch_fred_series(fred_id, units)
            
            labels = [parse_fred_date(d) for d in dates]
            actual_vals = vals
            
            last_date = datetime.strptime(dates[-1], '%Y-%m-%d') if dates else datetime.now()
            
            forecast_labels = []
            forecast_vals = []
            forecast_updates = []
            
            nc_dict = nowcasts.get(freq, {})
            try:
                sorted_months = sorted(nc_dict.keys(), key=lambda x: datetime.strptime(x, '%B %Y'))
            except Exception:
                sorted_months = list(nc_dict.keys())
            
            for m_str in sorted_months:
                try:
                    m_dt = datetime.strptime(m_str, '%B %Y')
                    if m_dt > last_date:
                        val = nc_dict[m_str].get(col_name)
                        upd = nc_dict[m_str].get('updated', '')
                        if val is not None:
                            short_m = f"{MONTH_SHORT[m_dt.month-1]} {m_dt.year}"
                            forecast_labels.append(short_m)
                            forecast_vals.append(val)
                            forecast_updates.append(upd)
                except Exception:
                    continue
            
            total_labels = labels + forecast_labels
            total_len = len(total_labels)
            
            target_val = 2.0 if freq == 'yoy' else 0.2

            payload['charts'][f'{key}_{freq}'] = {
                'labels': total_labels,
                'actuals': actual_vals + [None] * len(forecast_vals),
                'forecasts': [None] * len(actual_vals) + forecast_vals,
                'target': [target_val] * total_len,
                'fred_updated': fred_updated,
                'next_release': next_release,
                'forecast_updates': list(set(forecast_updates))
            }

    return render_template('index.html', data=payload)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='192.168.0.101', port=port, debug=True)
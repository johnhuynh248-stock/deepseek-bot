import requests
import json
from datetime import datetime, timedelta
from config import Config

class TradierAPI:
    def __init__(self):
        self.token = Config.TRADIER_TOKEN
        self.account_id = Config.TRADIER_ACCOUNT_ID
        self.base_url = Config.TRADIER_API_URL
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json'
        }
    
    def get_quotes(self, symbols):
        """Get real-time quotes"""
        url = f"{self.base_url}markets/quotes"
        params = {'symbols': ','.join(symbols) if isinstance(symbols, list) else symbols}
        
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()
    
    def get_options_chain(self, symbol, expiration):
        """Get options chain for a symbol"""
        url = f"{self.base_url}markets/options/chains"
        params = {
            'symbol': symbol,
            'expiration': expiration
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()
    
    def get_historical_data(self, symbol, interval='daily', start_date=None, end_date=None):
        """Get historical data"""
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        url = f"{self.base_url}markets/history"
        params = {
            'symbol': symbol,
            'interval': interval,
            'start': start_date,
            'end': end_date
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()
    
    def place_order(self, symbol, quantity, option_type, strike, expiration, side='buy_to_open'):
        """Place an options order"""
        url = f"{self.base_url}accounts/{self.account_id}/orders"
        
        option_symbol = f"{symbol}{expiration.replace('-', '')}{'C' if option_type == 'call' else 'P'}{strike*1000:08d}"
        
        data = {
            'class': 'option',
            'symbol': option_symbol,
            'side': side,
            'quantity': quantity,
            'type': 'market',
            'duration': 'day'
        }
        
        response = requests.post(url, headers=self.headers, data=data)
        return response.json()
    
    def get_account_positions(self):
        """Get current positions"""
        url = f"{self.base_url}accounts/{self.account_id}/positions"
        response = requests.get(url, headers=self.headers)
        return response.json()

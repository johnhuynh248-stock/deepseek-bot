import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

class SessionRangeAnalyzer:
    def __init__(self):
        self.est = pytz.timezone('US/Eastern')
        self.utc = pytz.utc
        
    def calculate_session_ranges(self, df, ticker):
        """
        Calculate Asian, London, and NY session ranges
        """
        # Convert DataFrame to EST
        df_est = df.tz_convert(self.est)
        
        results = {
            'ticker': ticker,
            'timestamp': datetime.now(self.est),
            'sessions': {}
        }
        
        # Asian Session (8 PM - 2 AM EST)
        asian_mask = (df_est.index.hour >= 20) | (df_est.index.hour < 2)
        if any(asian_mask):
            asian_df = df_est[asian_mask]
            results['sessions']['asian'] = {
                'high': asian_df['high'].max(),
                'low': asian_df['low'].min(),
                'range': asian_df['high'].max() - asian_df['low'].min(),
                'mid': (asian_df['high'].max() + asian_df['low'].min()) / 2
            }
        
        # London Session (3 AM - 7 AM EST)
        london_mask = (df_est.index.hour >= 3) & (df_est.index.hour < 7)
        if any(london_mask):
            london_df = df_est[london_mask]
            results['sessions']['london'] = {
                'high': london_df['high'].max(),
                'low': london_df['low'].min(),
                'range': london_df['high'].max() - london_df['low'].min(),
                'mid': (london_df['high'].max() + london_df['low'].min()) / 2
            }
        
        # NY Session (8 AM - 12 PM EST)
        ny_mask = (df_est.index.hour >= 8) & (df_est.index.hour < 12)
        if any(ny_mask):
            ny_df = df_est[ny_mask]
            results['sessions']['ny'] = {
                'high': ny_df['high'].max(),
                'low': ny_df['low'].min(),
                'range': ny_df['high'].max() - ny_df['low'].min(),
                'mid': (ny_df['high'].max() + ny_df['low'].min()) / 2
            }
        
        return results
    
    def analyze_breakouts(self, current_price, session_data):
        """
        Analyze breakouts from session ranges
        """
        analysis = {
            'direction': 'NEUTRAL',
            'confidence': 0,
            'breakouts': [],
            'levels': {}
        }
        
        if not session_data['sessions']:
            return analysis
        
        # Check breakouts
        for session, data in session_data['sessions'].items():
            if current_price > data['high']:
                analysis['breakouts'].append({
                    'session': session,
                    'type': 'ABOVE',
                    'level': data['high'],
                    'distance': current_price - data['high']
                })
            elif current_price < data['low']:
                analysis['breakouts'].append({
                    'session': session,
                    'type': 'BELOW',
                    'level': data['low'],
                    'distance': data['low'] - current_price
                })
        
        # Determine direction
        if analysis['breakouts']:
            latest_breakout = analysis['breakouts'][-1]
            if latest_breakout['type'] == 'ABOVE':
                analysis['direction'] = 'BULLISH'
                analysis['confidence'] = min(90, 50 + (latest_breakout['distance'] / session_data['sessions']['asian']['range'] * 20))
            else:
                analysis['direction'] = 'BEARISH'
                analysis['confidence'] = min(90, 50 + (latest_breakout['distance'] / session_data['sessions']['asian']['range'] * 20))
        
        # Calculate support/resistance levels
        if 'asian' in session_data['sessions']:
            asian_data = session_data['sessions']['asian']
            analysis['levels'] = {
                'support': asian_data['low'],
                'resistance': asian_data['high'],
                'mid': asian_data['mid']
            }
        
        return analysis
    
    def calculate_tp_sl(self, current_price, direction, atr, confidence):
        """
        Calculate Take Profit and Stop Loss levels
        """
        risk_multiplier = confidence / 100
        
        if direction == 'BULLISH':
            stop_loss = current_price - (atr * 1.5 * risk_multiplier)
            take_profit = current_price + (atr * 3.0 * risk_multiplier)
        elif direction == 'BEARISH':
            stop_loss = current_price + (atr * 1.5 * risk_multiplier)
            take_profit = current_price - (atr * 3.0 * risk_multiplier)
        else:
            stop_loss = current_price - (atr * 1.0)
            take_profit = current_price + (atr * 1.0)
        
        return {
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'risk_reward': abs((take_profit - current_price) / (current_price - stop_loss))
        }

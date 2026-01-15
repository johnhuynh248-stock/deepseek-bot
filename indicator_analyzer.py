import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Tuple
import talib

class EnhancedSessionRangeAnalyzer:
    def __init__(self):
        self.est = pytz.timezone('US/Eastern')
        self.utc = pytz.utc
        
    def calculate_session_ranges(self, df, ticker):
        """
        Calculate Asian, London, and NY session ranges with enhanced analysis
        """
        # Convert DataFrame to EST
        df_est = df.tz_convert(self.est)
        df_est['hour'] = df_est.index.hour
        df_est['minute'] = df_est.index.minute
        
        results = {
            'ticker': ticker,
            'timestamp': datetime.now(self.est),
            'current_price': df_est['Close'].iloc[-1],
            'volume': df_est['Volume'].iloc[-1],
            'sessions': {},
            'momentum': {}
        }
        
        # Calculate technical indicators
        df_est['RSI'] = talib.RSI(df_est['Close'], timeperiod=14)
        df_est['SMA20'] = talib.SMA(df_est['Close'], timeperiod=20)
        df_est['SMA50'] = talib.SMA(df_est['Close'], timeperiod=50)
        df_est['MACD'], df_est['MACD_signal'], df_est['MACD_hist'] = talib.MACD(
            df_est['Close'], fastperiod=12, slowperiod=26, signalperiod=9
        )
        
        # Asian Session (8 PM - 2 AM EST)
        asian_mask = (df_est['hour'] >= 20) | (df_est['hour'] < 2)
        if any(asian_mask):
            asian_df = df_est[asian_mask]
            results['sessions']['asian'] = {
                'high': asian_df['High'].max(),
                'low': asian_df['Low'].min(),
                'range': asian_df['High'].max() - asian_df['Low'].min(),
                'mid': (asian_df['High'].max() + asian_df['Low'].min()) / 2,
                'volume': asian_df['Volume'].mean()
            }
        
        # London Session (3 AM - 7 AM EST)
        london_mask = (df_est['hour'] >= 3) & (df_est['hour'] < 7)
        if any(london_mask):
            london_df = df_est[london_mask]
            results['sessions']['london'] = {
                'high': london_df['High'].max(),
                'low': london_df['Low'].min(),
                'range': london_df['High'].max() - london_df['Low'].min(),
                'mid': (london_df['High'].max() + london_df['Low'].min()) / 2,
                'volume': london_df['Volume'].mean()
            }
        
        # NY Session (8 AM - 12 PM EST)
        ny_mask = (df_est['hour'] >= 8) & (df_est['hour'] < 12)
        if any(ny_mask):
            ny_df = df_est[ny_mask]
            results['sessions']['ny'] = {
                'high': ny_df['High'].max(),
                'low': ny_df['Low'].min(),
                'range': ny_df['High'].max() - ny_df['Low'].min(),
                'mid': (ny_df['High'].max() + ny_df['Low'].min()) / 2,
                'volume': ny_df['Volume'].mean()
            }
        
        # Momentum analysis
        current_rsi = df_est['RSI'].iloc[-1]
        macd_hist = df_est['MACD_hist'].iloc[-1]
        
        results['momentum'] = {
            'rsi': current_rsi,
            'macd_hist': macd_hist,
            'trend': 'BULLISH' if df_est['SMA20'].iloc[-1] > df_est['SMA50'].iloc[-1] else 'BEARISH',
            'price_vs_sma20': (df_est['Close'].iloc[-1] - df_est['SMA20'].iloc[-1]) / df_est['SMA20'].iloc[-1] * 100
        }
        
        return results
    
    def determine_direction(self, current_price, session_data, momentum) -> Tuple[str, float, str]:
        """
        Determine CALL/PUT direction with confidence score and reasoning
        """
        confidence_factors = []
        reasoning = []
        
        # Factor 1: Price vs Session Ranges (40% weight)
        if 'asian' in session_data['sessions']:
            asian_high = session_data['sessions']['asian']['high']
            asian_low = session_data['sessions']['asian']['low']
            asian_mid = session_data['sessions']['asian']['mid']
            
            if current_price > asian_high:
                confidence_factors.append(80)  # Bullish breakout
                reasoning.append(f"Price above Asian high (${asian_high:.2f})")
            elif current_price > asian_mid:
                confidence_factors.append(60)  # Bullish within range
                reasoning.append(f"Price in upper Asian range")
            elif current_price < asian_low:
                confidence_factors.append(20)  # Bearish breakout
                reasoning.append(f"Price below Asian low (${asian_low:.2f})")
            elif current_price < asian_mid:
                confidence_factors.append(40)  # Bearish within range
                reasoning.append(f"Price in lower Asian range")
        
        # Factor 2: RSI Analysis (20% weight)
        rsi = momentum['rsi']
        if rsi > 70:
            confidence_factors.append(30)  # Overbought, potential reversal
            reasoning.append(f"RSI overbought ({rsi:.1f})")
        elif rsi > 50:
            confidence_factors.append(60)  # Bullish momentum
            reasoning.append(f"RSI bullish ({rsi:.1f})")
        elif rsi > 30:
            confidence_factors.append(40)  # Bearish momentum
            reasoning.append(f"RSI bearish ({rsi:.1f})")
        else:
            confidence_factors.append(70)  # Oversold, potential reversal
            reasoning.append(f"RSI oversold ({rsi:.1f})")
        
        # Factor 3: MACD (15% weight)
        macd_hist = momentum['macd_hist']
        if macd_hist > 0:
            confidence_factors.append(65)  # Bullish MACD
            reasoning.append(f"MACD bullish ({macd_hist:.3f})")
        else:
            confidence_factors.append(35)  # Bearish MACD
            reasoning.append(f"MACD bearish ({macd_hist:.3f})")
        
        # Factor 4: Trend (15% weight)
        if momentum['trend'] == 'BULLISH':
            confidence_factors.append(70)
            reasoning.append("Uptrend (SMA20 > SMA50)")
        else:
            confidence_factors.append(30)
            reasoning.append("Downtrend (SMA20 < SMA50)")
        
        # Factor 5: Volume analysis (10% weight)
        if 'asian' in session_data['sessions']:
            current_volume = session_data.get('volume', 0)
            asian_volume = session_data['sessions']['asian']['volume']
            volume_ratio = current_volume / asian_volume if asian_volume > 0 else 1
            
            if volume_ratio > 1.5:
                confidence_factors.append(70)
                reasoning.append(f"High volume ({volume_ratio:.1f}x avg)")
            elif volume_ratio > 1.0:
                confidence_factors.append(55)
                reasoning.append(f"Average volume")
            else:
                confidence_factors.append(40)
                reasoning.append(f"Low volume ({volume_ratio:.1f}x avg)")
        
        # Calculate weighted average confidence
        weights = [0.40, 0.20, 0.15, 0.15, 0.10]
        weighted_confidences = [cf * w for cf, w in zip(confidence_factors, weights)]
        confidence = sum(weighted_confidences)
        
        # Determine direction
        avg_confidence = np.mean(confidence_factors)
        if avg_confidence > 55:
            direction = "CALL"
            trade_type = "BULLISH"
        elif avg_confidence < 45:
            direction = "PUT"
            trade_type = "BEARISH"
        else:
            direction = "NEUTRAL"
            trade_type = "NEUTRAL"
        
        return direction, min(confidence, 100), trade_type, reasoning
    
    def option_picker(self, ticker: str, direction: str, current_price: float, 
                     expiration_date: str, iv_rank: float = 50) -> List[Dict]:
        """
        Pick optimal options based on direction analysis
        """
        options = []
        
        if direction == "CALL":
            # For calls, choose strikes above current price
            strikes = [
                current_price * 1.01,  # 1% OTM
                current_price * 1.02,  # 2% OTM
                current_price * 1.05,  # 5% OTM (higher risk/reward)
            ]
            
            for strike in strikes:
                strike = round(strike, 2)
                delta = self.calculate_option_delta(current_price, strike, expiration_date, 
                                                   is_call=True, iv_rank=iv_rank)
                theta = self.calculate_option_theta(current_price, strike, expiration_date,
                                                   is_call=True, iv_rank=iv_rank)
                
                options.append({
                    'type': 'CALL',
                    'strike': strike,
                    'delta': delta,
                    'theta': theta,
                    'risk_level': 'MODERATE' if strike <= current_price * 1.02 else 'AGGRESSIVE',
                    'description': f"{'ITM' if strike < current_price else 'OTM'} Call",
                    'premium_estimate': self.estimate_premium(current_price, strike, 
                                                             expiration_date, is_call=True)
                })
                
        elif direction == "PUT":
            # For puts, choose strikes below current price
            strikes = [
                current_price * 0.99,  # 1% OTM
                current_price * 0.98,  # 2% OTM
                current_price * 0.95,  # 5% OTM (higher risk/reward)
            ]
            
            for strike in strikes:
                strike = round(strike, 2)
                delta = self.calculate_option_delta(current_price, strike, expiration_date,
                                                   is_call=False, iv_rank=iv_rank)
                theta = self.calculate_option_theta(current_price, strike, expiration_date,
                                                   is_call=False, iv_rank=iv_rank)
                
                options.append({
                    'type': 'PUT',
                    'strike': strike,
                    'delta': delta,
                    'theta': theta,
                    'risk_level': 'MODERATE' if strike >= current_price * 0.98 else 'AGGRESSIVE',
                    'description': f"{'ITM' if strike > current_price else 'OTM'} Put",
                    'premium_estimate': self.estimate_premium(current_price, strike,
                                                             expiration_date, is_call=False)
                })
        
        # Sort by risk/reward ratio
        options.sort(key=lambda x: abs(x['delta']), reverse=True)
        return options[:3]  # Return top 3 options
    
    def calculate_option_delta(self, spot: float, strike: float, expiration: str, 
                             is_call: bool, iv_rank: float) -> float:
        """Calculate approximate option delta"""
        time_to_expiry = self._days_to_expiry(expiration)
        moneyness = spot / strike
        
        if is_call:
            # Simplified delta calculation for calls
            if moneyness > 1.05:  # Deep ITM
                delta = 0.85
            elif moneyness > 1.02:  # Slightly ITM
                delta = 0.65
            elif moneyness > 0.98:  # Near ATM
                delta = 0.50
            elif moneyness > 0.95:  # Slightly OTM
                delta = 0.35
            else:  # Deep OTM
                delta = 0.20
        else:
            # Simplified delta calculation for puts
            if moneyness < 0.95:  # Deep ITM
                delta = -0.85
            elif moneyness < 0.98:  # Slightly ITM
                delta = -0.65
            elif moneyness < 1.02:  # Near ATM
                delta = -0.50
            elif moneyness < 1.05:  # Slightly OTM
                delta = -0.35
            else:  # Deep OTM
                delta = -0.20
        
        # Adjust for IV
        delta *= (1 + (iv_rank - 50) / 200)
        return round(delta, 2)
    
    def calculate_option_theta(self, spot: float, strike: float, expiration: str,
                             is_call: bool, iv_rank: float) -> float:
        """Calculate approximate option theta (daily time decay)"""
        time_to_expiry = self._days_to_expiry(expiration)
        
        # Base theta based on time to expiry
        if time_to_expiry < 7:
            theta = -0.05  # High decay for weekly options
        elif time_to_expiry < 14:
            theta = -0.03  # Moderate decay
        else:
            theta = -0.02  # Lower decay for monthly options
        
        # Adjust for IV
        theta *= (1 + (iv_rank - 50) / 100)
        return round(theta, 3)
    
    def estimate_premium(self, spot: float, strike: float, expiration: str,
                        is_call: bool) -> float:
        """Estimate option premium"""
        time_to_expiry = self._days_to_expiry(expiration)
        intrinsic = max(spot - strike, 0) if is_call else max(strike - spot, 0)
        
        # Simplified extrinsic value estimation
        extrinsic = spot * 0.02 * (time_to_expiry / 30) ** 0.5
        
        return round(intrinsic + extrinsic, 2)
    
    def _days_to_expiry(self, expiration: str) -> int:
        """Calculate days to expiration"""
        expiry_date = datetime.strptime(expiration, '%Y-%m-%d')
        return max((expiry_date - datetime.now()).days, 1)
    
    def calculate_tp_sl(self, current_price: float, direction: str, 
                       atr: float, confidence: float, option_type: str = None) -> Dict:
        """
        Calculate Take Profit and Stop Loss with option-specific adjustments
        """
        risk_multiplier = confidence / 100
        
        if direction == "CALL" or direction == "BULLISH":
            # For calls/long positions
            stop_loss_pct = 0.03 - (0.01 * risk_multiplier)
            take_profit_pct = 0.06 + (0.02 * risk_multiplier)
            
            if option_type == "CALL":
                # More aggressive SL for options due to theta decay
                stop_loss_pct *= 1.5
                take_profit_pct *= 1.2
            
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
            
        elif direction == "PUT" or direction == "BEARISH":
            # For puts/short positions
            stop_loss_pct = 0.03 - (0.01 * risk_multiplier)
            take_profit_pct = 0.06 + (0.02 * risk_multiplier)
            
            if option_type == "PUT":
                # More aggressive SL for options due to theta decay
                stop_loss_pct *= 1.5
                take_profit_pct *= 1.2
            
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)
        
        else:
            # Neutral/default
            stop_loss = current_price * 0.97
            take_profit = current_price * 1.03
        
        # Ensure TP/SL are reasonable
        stop_loss = round(max(stop_loss, 0.01), 2)
        take_profit = round(take_profit, 2)
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': abs((take_profit - current_price) / (current_price - stop_loss))
        }

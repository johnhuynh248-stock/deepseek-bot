import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.io as pio

from config import Config
from indicator_analyzer import SessionRangeAnalyzer
from tradier_api import TradierAPI

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.analyzer = SessionRangeAnalyzer()
        self.tradier = TradierAPI()
        self.emoji = Config.EMOJI
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        welcome_text = f"""
{self.emoji['rocket']} *Welcome to Session Range Trading Bot* {self.emoji['rocket']}

*Available Commands:*
/status [TICKER] - Get trading signal for a ticker
/analyze [TICKER] - Detailed analysis with options
/trade [TICKER] [CALL/PUT] - Place an options trade
/positions - View current positions
/settings - Configure bot settings
/help - Show this help message

*Example:* `/status SPY` or `/trade AAPL CALL`
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            if not context.args:
                await update.message.reply_text(
                    f"{self.emoji['warning']} Please provide a ticker. Example: `/status SPY`",
                    parse_mode='Markdown'
                )
                return
            
            ticker = context.args[0].upper()
            
            # Show loading message
            loading_msg = await update.message.reply_text(
                f"{self.emoji['chart']} Analyzing {ticker}..."
            )
            
            # Get historical data
            stock = yf.Ticker(ticker)
            hist = stock.history(period='5d', interval='15m')
            
            if hist.empty:
                await loading_msg.edit_text(f"{self.emoji['cross']} No data found for {ticker}")
                return
            
            current_price = stock.info.get('regularMarketPrice', hist['Close'].iloc[-1])
            
            # Analyze sessions
            session_data = self.analyzer.calculate_session_ranges(hist, ticker)
            analysis = self.analyzer.analyze_breakouts(current_price, session_data)
            
            # Calculate ATR for TP/SL
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            
            tp_sl = self.analyzer.calculate_tp_sl(current_price, analysis['direction'], atr, analysis['confidence'])
            
            # Prepare response
            direction_emoji = {
                'BULLISH': f"{self.emoji['bull']} {self.emoji['up']}",
                'BEARISH': f"{self.emoji['bear']} {self.emoji['down']}",
                'NEUTRAL': self.emoji['neutral']
            }
            
            response = f"""
*{ticker} Analysis* {self.emoji['chart']}

*Current Price:* ${current_price:.2f}
*Direction:* {direction_emoji[analysis['direction']]} {analysis['direction']}
*Confidence Score:* {analysis['confidence']:.0f}/100 {self.emoji['fire'] if analysis['confidence'] > 70 else ''}

*Session Ranges:*
• Asian: ${session_data['sessions'].get('asian', {}).get('range', 0):.2f}
• London: ${session_data['sessions'].get('london', {}).get('range', 0):.2f}
• NY: ${session_data['sessions'].get('ny', {}).get('range', 0):.2f}

*Key Levels:*
• Support: ${analysis['levels'].get('support', 0):.2f}
• Resistance: ${analysis['levels'].get('resistance', 0):.2f}
• Mid: ${analysis['levels'].get('mid', 0):.2f}

*Trade Setup:*
• Stop Loss: ${tp_sl['stop_loss']:.2f}
• Take Profit: ${tp_sl['take_profit']:.2f}
• Risk/Reward: {tp_sl['risk_reward']:.2f}:1

*Breakouts:* {len(analysis['breakouts'])}
            """
            
            # Add breakout details
            if analysis['breakouts']:
                response += "\n\n*Recent Breakouts:*"
                for breakout in analysis['breakouts'][-3:]:
                    response += f"\n• {breakout['session'].title()}: {breakout['type']} by ${breakout['distance']:.2f}"
            
            # Create inline keyboard for actions
            keyboard = [
                [
                    InlineKeyboardButton(f"{self.emoji['money']} Trade Call", callback_data=f"trade_{ticker}_call"),
                    InlineKeyboardButton(f"{self.emoji['money']} Trade Put", callback_data=f"trade_{ticker}_put")
                ],
                [
                    InlineKeyboardButton(f"{self.emoji['chart']} Detailed Analysis", callback_data=f"analyze_{ticker}"),
                    InlineKeyboardButton(f"{self.emoji['calendar']} Options Chain", callback_data=f"options_{ticker}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text(
                f"{self.emoji['cross']} Error analyzing {ticker}. Please try again."
            )
    
    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command with detailed analysis"""
        try:
            if not context.args:
                await update.message.reply_text("Please provide a ticker. Example: /analyze SPY")
                return
            
            ticker = context.args[0].upper()
            
            # Get detailed analysis
            stock = yf.Ticker(ticker)
            hist = stock.history(period='10d', interval='1h')
            
            # Create visualization
            fig = go.Figure()
            
            # Add candlestick
            fig.add_trace(go.Candlestick(
                x=hist.index,
                open=hist['Open'],
                high=hist['High'],
                low=hist['Low'],
                close=hist['Close'],
                name='Price'
            ))
            
            # Add session ranges
            analyzer = SessionRangeAnalyzer()
            session_data = analyzer.calculate_session_ranges(hist, ticker)
            
            for session, data in session_data['sessions'].items():
                fig.add_hline(y=data['high'], line_dash="dash", 
                            annotation_text=f"{session.upper()} High",
                            line_color="red")
                fig.add_hline(y=data['low'], line_dash="dash",
                            annotation_text=f"{session.upper()} Low",
                            line_color="green")
                fig.add_hline(y=data['mid'], line_dash="dot",
                            line_color="orange")
            
            fig.update_layout(
                title=f"{ticker} Session Range Analysis",
                yaxis_title="Price",
                xaxis_title="Date",
                template="plotly_dark"
            )
            
            # Save chart
            chart_path = f"{ticker}_analysis.png"
            pio.write_image(fig, chart_path, width=1200, height=800)
            
            # Send chart
            with open(chart_path, 'rb') as chart:
                await update.message.reply_photo(
                    photo=chart,
                    caption=f"{self.emoji['chart']} *{ticker} Detailed Analysis*\n\n"
                           f"Asian Range: ${session_data['sessions'].get('asian', {}).get('range', 0):.2f}\n"
                           f"London Range: ${session_data['sessions'].get('london', {}).get('range', 0):.2f}\n"
                           f"NY Range: ${session_data['sessions'].get('ny', {}).get('range', 0):.2f}",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"Error in analyze command: {e}")
            await update.message.reply_text(f"Error analyzing {ticker}")
    
    async def trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trade command"""
        try:
            if len(context.args) < 2:
                await update.message.reply_text(
                    "Usage: /trade [TICKER] [CALL/PUT] [STRIKE] [EXPIRATION]\n"
                    "Example: /trade AAPL CALL 180 2024-01-19"
                )
                return
            
            ticker = context.args[0].upper()
            option_type = context.args[1].upper()
            strike = float(context.args[2]) if len(context.args) > 2 else None
            expiration = context.args[3] if len(context.args) > 3 else None
            
            # Get options chain
            if expiration is None:
                # Get next Friday
                today = datetime.now()
                days_ahead = (4 - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                expiration = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            
            # Show options selection
            response = f"""
{self.emoji['money']} *Options Trade Setup*

*Ticker:* {ticker}
*Type:* {option_type}
*Expiration:* {expiration}

Select a strike price:
            """
            
            # Get options chain
            chain_data = self.tradier.get_options_chain(ticker, expiration)
            
            keyboard = []
            if 'options' in chain_data:
                options = chain_data['options']['option']
                # Filter by type and show nearest strikes
                current_price = yf.Ticker(ticker).info['regularMarketPrice']
                filtered_options = []
                
                for opt in options:
                    if opt['option_type'].lower() == option_type.lower():
                        filtered_options.append(opt)
                
                # Sort by proximity to current price
                filtered_options.sort(key=lambda x: abs(float(x['strike']) - current_price))
                
                # Create buttons for nearest strikes
                for opt in filtered_options[:5]:
                    strike_price = float(opt['strike'])
                    keyboard.append([
                        InlineKeyboardButton(
                            f"${strike_price} (${opt.get('bid', 0)})",
                            callback_data=f"confirm_{ticker}_{option_type}_{strike_price}_{expiration}"
                        )
                    ])
            
            keyboard.append([InlineKeyboardButton(f"{self.emoji['cross']} Cancel", callback_data="cancel_trade")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in trade command: {e}")
            await update.message.reply_text(f"Error setting up trade: {str(e)}")
    
    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        try:
            positions = self.tradier.get_account_positions()
            
            if 'positions' not in positions or not positions['positions']:
                await update.message.reply_text(f"{self.emoji['money']} No open positions")
                return
            
            response = f"{self.emoji['money']} *Current Positions*\n\n"
            total_pnl = 0
            
            for pos in positions['positions']['position']:
                symbol = pos.get('symbol', 'N/A')
                quantity = pos.get('quantity', 0)
                cost_basis = float(pos.get('cost_basis', 0))
                current_price = float(pos.get('last_price', 0))
                pnl = (current_price - cost_basis) * quantity
                total_pnl += pnl
                
                response += f"*{symbol}*\n"
                response += f"Qty: {quantity} | Avg: ${cost_basis:.2f}\n"
                response += f"Current: ${current_price:.2f} | P&L: ${pnl:.2f}\n"
                response += f"{'---'}\n"
            
            response += f"\n*Total P&L:* ${total_pnl:.2f}"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in positions command: {e}")
            await update.message.reply_text(f"Error fetching positions: {str(e)}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith('trade_'):
            # Handle trade button
            _, ticker, option_type = data.split('_')
            await query.edit_message_text(
                f"{self.emoji['money']} Preparing {option_type.upper()} trade for {ticker}..."
            )
            # Continue with trade setup...
            
        elif data.startswith('analyze_'):
            ticker = data.split('_')[1]
            await self.analyze_command(update, context)
            
        elif data.startswith('confirm_'):
            # Confirm and place trade
            _, ticker, option_type, strike, expiration = data.split('_')
            
            # Place order
            result = self.tradier.place_order(
                symbol=ticker,
                quantity=1,
                option_type=option_type.lower(),
                strike=float(strike),
                expiration=expiration
            )
            
            if 'order' in result:
                await query.edit_message_text(
                    f"{self.emoji['check']} *Order Placed Successfully!*\n\n"
                    f"*Symbol:* {ticker}\n"
                    f"*Type:* {option_type.upper()}\n"
                    f"*Strike:* ${strike}\n"
                    f"*Expiration:* {expiration}\n"
                    f"*Order ID:* {result['order']['id']}",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"{self.emoji['cross']} *Order Failed*\n\n"
                    f"Error: {result.get('errors', {}).get('error', 'Unknown error')}",
                    parse_mode='Markdown'
                )
            
        elif data == 'cancel_trade':
            await query.edit_message_text(f"{self.emoji['cross']} Trade cancelled")

def main():
    """Start the bot"""
    bot = TradingBot()
    
    # Create Application
    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(CommandHandler("analyze", bot.analyze_command))
    application.add_handler(CommandHandler("trade", bot.trade_command))
    application.add_handler(CommandHandler("positions", bot.positions_command))
    application.add_handler(CommandHandler("help", bot.start))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

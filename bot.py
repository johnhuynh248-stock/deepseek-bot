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
from typing import List

from config import Config
from indicator_analyzer import EnhancedSessionRangeAnalyzer
from tradier_api import TradierAPI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class EnhancedTradingBot:
    def __init__(self):
        self.analyzer = EnhancedSessionRangeAnalyzer()
        self.tradier = TradierAPI()
        self.emoji = Config.EMOJI
        
    def format_option_analysis(self, ticker: str, direction: str, confidence: float, 
                              options: List[Dict], reasoning: List[str]) -> str:
        """Format option analysis for display"""
        direction_emoji = {
            'CALL': f"{self.emoji['bull']} {self.emoji['up']}",
            'PUT': f"{self.emoji['bear']} {self.emoji['down']}",
            'NEUTRAL': self.emoji['neutral']
        }
        
        analysis = f"""
*{ticker} OPTION ANALYSIS* {self.emoji['money']}

*Direction:* {direction_emoji[direction]} *{direction}*
*Confidence:* {confidence:.0f}/100 {self.emoji['fire'] if confidence > 70 else ''}

*Recommended Options:*
"""
        
        for i, option in enumerate(options[:3], 1):
            premium = option.get('premium_estimate', 'N/A')
            analysis += f"""
{i}. *{option['type']}* ${option['strike']:.2f}
   • Delta: {option['delta']:.2f}
   • Theta: {option['theta']:.3f}
   • Risk: {option['risk_level']}
   • Est. Premium: ${premium}
   • {option['description']}
"""
        
        analysis += f"\n*Analysis Factors:*\n"
        for i, reason in enumerate(reasoning[:5], 1):
            analysis += f"{i}. {reason}\n"
        
        return analysis
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /status command with option recommendations"""
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
                f"{self.emoji['chart']} Analyzing {ticker} for option opportunities..."
            )
            
            # Get historical data
            stock = yf.Ticker(ticker)
            hist = stock.history(period='5d', interval='15m')
            
            if hist.empty:
                await loading_msg.edit_text(f"{self.emoji['cross']} No data found for {ticker}")
                return
            
            current_price = stock.info.get('regularMarketPrice', hist['Close'].iloc[-1])
            
            # Enhanced analysis
            session_data = self.analyzer.calculate_session_ranges(hist, ticker)
            direction, confidence, trade_type, reasoning = self.analyzer.determine_direction(
                current_price, session_data, session_data['momentum']
            )
            
            # Get next expiration
            expirations = self.get_option_expirations(ticker)
            next_expiry = expirations[0] if expirations else self.get_next_friday()
            
            # Pick optimal options
            options = self.analyzer.option_picker(
                ticker, direction, current_price, next_expiry
            )
            
            # Calculate TP/SL
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            
            tp_sl = self.analyzer.calculate_tp_sl(
                current_price, direction, atr, confidence,
                option_type=direction if direction != 'NEUTRAL' else None
            )
            
            # Format response
            response = f"""
*{ticker} TRADING SIGNAL* {self.emoji['rocket']}

*Current Price:* ${current_price:.2f}
*Signal:* {direction_emoji[direction]} *{direction}*
*Confidence Score:* {confidence:.0f}/100 {self.emoji['fire'] if confidence > 70 else ''}
*Expiration:* {next_expiry}

*Session Analysis:*
• Asian Range: ${session_data['sessions'].get('asian', {}).get('range', 0):.2f}
• London Range: ${session_data['sessions'].get('london', {}).get('range', 0):.2f}
• NY Range: ${session_data['sessions'].get('ny', {}).get('range', 0):.2f}

*Technical Indicators:*
• RSI: {session_data['momentum']['rsi']:.1f}
• MACD: {'Bullish' if session_data['momentum']['macd_hist'] > 0 else 'Bearish'}
• Trend: {session_data['momentum']['trend']}

*Risk Management:*
• Stop Loss: ${tp_sl['stop_loss']:.2f}
• Take Profit: ${tp_sl['take_profit']:.2f}
• Risk/Reward: {tp_sl['risk_reward']:.2f}:1
"""
            
            # Add option recommendations
            if direction != 'NEUTRAL' and options:
                response += f"\n*Recommended Options:*\n"
                for i, opt in enumerate(options[:2], 1):
                    premium = opt.get('premium_estimate', 'N/A')
                    response += f"{i}. *{opt['type']}* ${opt['strike']:.2f}"
                    response += f" (Delta: {opt['delta']:.2f}, Est: ${premium})\n"
            
            # Add reasoning
            if reasoning:
                response += f"\n*Key Factors:*\n"
                for i, reason in enumerate(reasoning[:3], 1):
                    response += f"{i}. {reason}\n"
            
            # Create interactive keyboard
            keyboard = []
            
            if direction == 'CALL':
                keyboard.append([
                    InlineKeyboardButton(f"{self.emoji['money']} Buy CALL", 
                                       callback_data=f"buy_{ticker}_call"),
                    InlineKeyboardButton(f"{self.emoji['chart']} View CALLs", 
                                       callback_data=f"view_{ticker}_calls")
                ])
            elif direction == 'PUT':
                keyboard.append([
                    InlineKeyboardButton(f"{self.emoji['money']} Buy PUT", 
                                       callback_data=f"buy_{ticker}_put"),
                    InlineKeyboardButton(f"{self.emoji['chart']} View PUTs", 
                                       callback_data=f"view_{ticker}_puts")
                ])
            
            keyboard.extend([
                [
                    InlineKeyboardButton(f"{self.emoji['chart']} Detailed Analysis", 
                                       callback_data=f"analyze_{ticker}"),
                    InlineKeyboardButton(f"{self.emoji['calendar']} Option Chain", 
                                       callback_data=f"chain_{ticker}")
                ],
                [
                    InlineKeyboardButton(f"{self.emoji['clock']} Set Alert", 
                                       callback_data=f"alert_{ticker}"),
                    InlineKeyboardButton(f"{self.emoji['warning']} Risk Check", 
                                       callback_data=f"risk_{ticker}")
                ]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text(
                f"{self.emoji['cross']} Error analyzing {ticker}: {str(e)}"
            )
    
    async def options_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /options command to show option chain"""
        try:
            if not context.args:
                await update.message.reply_text(
                    f"{self.emoji['warning']} Usage: `/options TICKER`\nExample: `/options SPY`",
                    parse_mode='Markdown'
                )
                return
            
            ticker = context.args[0].upper()
            
            loading_msg = await update.message.reply_text(
                f"{self.emoji['calendar']} Fetching option chain for {ticker}..."
            )
            
            # Get option chain from Tradier
            expirations = self.get_option_expirations(ticker)
            if not expirations:
                await loading_msg.edit_text(f"No options available for {ticker}")
                return
            
            next_expiry = expirations[0]
            chain_data = self.tradier.get_options_chain(ticker, next_expiry)
            
            if 'options' not in chain_data:
                await loading_msg.edit_text(f"No option data for {ticker}")
                return
            
            # Get current price
            stock = yf.Ticker(ticker)
            current_price = stock.info.get('regularMarketPrice', 0)
            
            # Format option chain
            response = f"""
*{ticker} OPTION CHAIN* {self.emoji['money']}
*Expiration:* {next_expiry}
*Current Price:* ${current_price:.2f}

*CALLS (Bullish)* {self.emoji['bull']}
"""
            
            options = chain_data['options']['option']
            calls = [opt for opt in options if opt['option_type'] == 'call']
            puts = [opt for opt in options if opt['option_type'] == 'put']
            
            # Show nearest strikes for calls
            calls.sort(key=lambda x: abs(float(x['strike']) - current_price))
            for call in calls[:5]:
                strike = float(call['strike'])
                bid = call.get('bid', 0)
                ask = call.get('ask', 0)
                mid = (float(bid) + float(ask)) / 2 if bid and ask else 0
                
                response += f"""
• ${strike:.2f}: Bid ${bid} | Ask ${ask}
  Mid: ${mid:.2f} | {'ITM' if strike < current_price else 'OTM'}
"""
            
            response += f"\n*PUTS (Bearish)* {self.emoji['bear']}\n"
            
            # Show nearest strikes for puts
            puts.sort(key=lambda x: abs(float(x['strike']) - current_price))
            for put in puts[:5]:
                strike = float(put['strike'])
                bid = put.get('bid', 0)
                ask = put.get('ask', 0)
                mid = (float(bid) + float(ask)) / 2 if bid and ask else 0
                
                response += f"""
• ${strike:.2f}: Bid ${bid} | Ask ${ask}
  Mid: ${mid:.2f} | {'ITM' if strike > current_price else 'OTM'}
"""
            
            # Create selection keyboard
            keyboard = []
            for call in calls[:3]:
                strike = float(call['strike'])
                keyboard.append([
                    InlineKeyboardButton(
                        f"CALL ${strike:.2f}",
                        callback_data=f"select_{ticker}_call_{strike}_{next_expiry}"
                    )
                ])
            
            for put in puts[:3]:
                strike = float(put['strike'])
                keyboard.append([
                    InlineKeyboardButton(
                        f"PUT ${strike:.2f}",
                        callback_data=f"select_{ticker}_put_{strike}_{next_expiry}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(f"{self.emoji['cross']} Close", callback_data="close_chain")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in options command: {e}")
            await update.message.reply_text(f"Error fetching options: {str(e)}")
    
    async def pick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pick command for automated option selection"""
        try:
            if not context.args:
                await update.message.reply_text(
                    f"{self.emoji['warning']} Usage: `/pick TICKER [EXPIRATION]`\n"
                    f"Example: `/pick AAPL` or `/pick SPY 2024-01-19`",
                    parse_mode='Markdown'
                )
                return
            
            ticker = context.args[0].upper()
            expiration = context.args[1] if len(context.args) > 1 else self.get_next_friday()
            
            loading_msg = await update.message.reply_text(
                f"{self.emoji['chart']} Picking best option for {ticker}..."
            )
            
            # Get data and analysis
            stock = yf.Ticker(ticker)
            hist = stock.history(period='5d', interval='15m')
            current_price = stock.info.get('regularMarketPrice', hist['Close'].iloc[-1])
            
            session_data = self.analyzer.calculate_session_ranges(hist, ticker)
            direction, confidence, trade_type, reasoning = self.analyzer.determine_direction(
                current_price, session_data, session_data['momentum']
            )
            
            # Get option recommendations
            options = self.analyzer.option_picker(
                ticker, direction, current_price, expiration
            )
            
            if not options:
                await loading_msg.edit_text(f"No suitable options found for {ticker}")
                return
            
            # Format best option
            best_option = options[0]
            tp_sl = self.analyzer.calculate_tp_sl(
                current_price, direction, 
                session_data['sessions']['asian']['range'] if 'asian' in session_data['sessions'] else 1,
                confidence,
                option_type=direction
            )
            
            response = f"""
*{self.emoji['fire']} BEST OPTION PICK {self.emoji['fire']}

*Ticker:* {ticker}
*Current Price:* ${current_price:.2f}
*Expiration:* {expiration}

*Recommended Trade:*
• *{best_option['type']}* ${best_option['strike']:.2f}
• Delta: {best_option['delta']:.2f}
• Theta: {best_option['theta']:.3f}
• Risk Level: {best_option['risk_level']}
• Est. Premium: ${best_option.get('premium_estimate', 'N/A')}

*Trade Rationale:*
• Direction Signal: {direction} ({confidence:.0f}/100 confidence)
• {best_option['description']}
• Max Profit: Unlimited
• Max Loss: Premium Paid

*Risk Management:*
• Stop Loss: ${tp_sl['stop_loss']:.2f} (Underlying)
• Take Profit: ${tp_sl['take_profit']:.2f} (Underlying)
• Risk/Reward: {tp_sl['risk_reward']:.2f}:1

*Key Factors:*
"""
            
            for i, reason in enumerate(reasoning[:3], 1):
                response += f"{i}. {reason}\n"
            
            # Action buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{self.emoji['money']} Place This Trade",
                        callback_data=f"trade_{ticker}_{best_option['type'].lower()}_{best_option['strike']}_{expiration}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{self.emoji['chart']} See Alternatives",
                        callback_data=f"alternatives_{ticker}_{direction}"
                    ),
                    InlineKeyboardButton(
                        f"{self.emoji['warning']} Risk Analysis",
                        callback_data=f"risk_{ticker}_{best_option['type']}_{best_option['strike']}"
                    )
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in pick command: {e}")
            await update.message.reply_text(f"Error picking option: {str(e)}")
    
    def get_option_expirations(self, ticker: str) -> List[str]:
        """Get available option expiration dates"""
        try:
            # Get options from yfinance
            stock = yf.Ticker(ticker)
            options = stock.options
            
            if not options:
                # Generate standard expirations if none available
                today = datetime.now()
                expirations = []
                for i in range(4):
                    expiry = today + timedelta(days=7 * (i + 1))
                    # Find Friday
                    days_to_friday = (4 - expiry.weekday()) % 7
                    if days_to_friday == 0:
                        days_to_friday = 7
                    expiry += timedelta(days=days_to_friday)
                    expirations.append(expiry.strftime('%Y-%m-%d'))
                return expirations
            
            return list(options)[:4]  # Return next 4 expirations
            
        except Exception as e:
            logger.error(f"Error getting expirations: {e}")
            return []
    
    def get_next_friday(self) -> str:
        """Get next Friday's date as string"""
        today = datetime.now()
        days_ahead = (4 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        next_friday = today + timedelta(days=days_ahead)
        return next_friday.strftime('%Y-%m-%d')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith('buy_'):
            # Handle buy button
            _, ticker, option_type = data.split('_')
            await self.show_buy_options(query, ticker, option_type.upper())
            
        elif data.startswith('view_'):
            _, ticker, option_type = data.split('_')
            await self.show_option_details(query, ticker, option_type.upper())
            
        elif data.startswith('select_'):
            _, ticker, option_type, strike, expiration = data.split('_')
            await self.confirm_trade(query, ticker, option_type.upper(), float(strike), expiration)
            
        elif data.startswith('trade_'):
            _, ticker, option_type, strike, expiration = data.split('_')
            await self.place_trade(query, ticker, option_type.upper(), float(strike), expiration)
            
        elif data.startswith('pick_'):
            _, ticker, direction = data.split('_')
            await self.pick_command(update, context)
            
        elif data == 'close_chain':
            await query.delete_message()
    
    async def show_buy_options(self, query, ticker, option_type):
        """Show buy options interface"""
        stock = yf.Ticker(ticker)
        current_price = stock.info.get('regularMarketPrice', 0)
        
        if option_type == 'CALL':
            strikes = [
                current_price * 0.98,  # Slightly ITM
                current_price,         # ATM
                current_price * 1.02,  # Slightly OTM
            ]
        else:  # PUT
            strikes = [
                current_price * 1.02,  # Slightly ITM
                current_price,         # ATM
                current_price * 0.98,  # Slightly OTM
            ]
        
        keyboard = []
        for strike in strikes:
            strike = round(strike, 2)
            keyboard.append([
                InlineKeyboardButton(
                    f"${strike} {option_type}",
                    callback_data=f"select_{ticker}_{option_type.lower()}_{strike}_{self.get_next_friday()}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(f"{self.emoji['cross']} Cancel", callback_data="cancel_buy")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*Select Strike Price for {ticker} {option_type}*\n"
            f"Current Price: ${current_price:.2f}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def confirm_trade(self, query, ticker, option_type, strike, expiration):
        """Show trade confirmation"""
        response = f"""
{self.emoji['money']} *TRADE CONFIRMATION*

*Ticker:* {ticker}
*Option Type:* {option_type}
*Strike Price:* ${strike:.2f}
*Expiration:* {expiration}
*Quantity:* 1 contract

*Risk Warning:*
• Options trading involves significant risk
• You can lose your entire investment
• Time decay (theta) will affect position
• IV changes can impact premium

*Do you want to proceed?*
"""
        
        keyboard = [
            [
                InlineKeyboardButton(f"{self.emoji['check']} Confirm Buy", 
                                   callback_data=f"trade_{ticker}_{option_type.lower()}_{strike}_{expiration}"),
                InlineKeyboardButton(f"{self.emoji['cross']} Cancel", 
                                   callback_data="cancel_trade")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(response, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def place_trade(self, query, ticker, option_type, strike, expiration):
        """Place the actual trade"""
        try:
            # Place order through Tradier
            result = self.tradier.place_order(
                symbol=ticker,
                quantity=1,
                option_type=option_type.lower(),
                strike=strike,
                expiration=expiration
            )
            
            if 'order' in result:
                order_id = result['order']['id']
                await query.edit_message_text(
                    f"{self.emoji['check']} *ORDER EXECUTED!* {self.emoji['rocket']}\n\n"
                    f"*Symbol:* {ticker}\n"
                    f"*Type:* {option_type}\n"
                    f"*Strike:* ${strike:.2f}\n"
                    f"*Expiration:* {expiration}\n"
                    f"*Quantity:* 1 contract\n"
                    f"*Order ID:* {order_id}\n\n"
                    f"*Next Steps:*\n"
                    f"1. Set stop loss alert\n"
                    f"2. Monitor theta decay\n"
                    f"3. Consider profit targets",
                    parse_mode='Markdown'
                )
            else:
                error = result.get('errors', {}).get('error', 'Unknown error')
                await query.edit_message_text(
                    f"{self.emoji['cross']} *ORDER FAILED*\n\n"
                    f"Error: {error}\n\n"
                    f"Please try again or contact support.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Trade error: {e}")
            await query.edit_message_text(
                f"{self.emoji['cross']} *TRADE ERROR*\n\n"
                f"An error occurred: {str(e)}\n"
                f"Please try again later.",
                parse_mode='Markdown'
            )

def main():
    """Start the enhanced bot"""
    bot = EnhancedTradingBot()
    
    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(CommandHandler("options", bot.options_command))
    application.add_handler(CommandHandler("pick", bot.pick_command))
    application.add_handler(CommandHandler("trade", bot.trade_command))
    application.add_handler(CommandHandler("positions", bot.positions_command))
    application.add_handler(CommandHandler("analyze", bot.analyze_command))
    application.add_handler(CommandHandler("help", bot.start))
    
    # Add callback handler
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Start bot
    logger.info("Starting Enhanced Trading Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

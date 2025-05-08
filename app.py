# 评分逻辑比较
# 1. 当前系统评分逻辑(calculate_stock_score):
#   - 涨跌幅评分 (30分): 依据涨跌百分比多档位评分
#   - 换手率评分 (20分): 3-8%的换手率评分最高，过低或过高均减分
#   - 成交量评分 (20分): 成交量越大评分越高，分档给分
#   - 价格区间评分 (15分): 中等价格区间(15-100元)给分最高
#   - 市值评分 (15分): 中型市值公司评分最高(如有市值数据)
# 
# 2. @StockAnalysis的评分逻辑:
#   - 趋势评分 (30分): 基于移动均线判断趋势，上升趋势才得分
#   - RSI评分 (20分): 只在RSI为30-70区间(非超买超卖)才得分
#   - MACD评分 (20分): 只有MACD信号为"买入"才得分
#   - 成交量评分 (15分): 只有"放量"才得分
#   - 波动率评分 (15分): 只有波动率小于30%才得分
# 
# 主要差异:
# 1. 评分方式: 当前系统为多档线性评分，@StockAnalysis为二元评分(有/无)
# 2. 指标选择: 当前系统更注重市场数据(价格/成交量/换手率)，@StockAnalysis更注重技术指标
# 3. 评分阈值: 当前系统有更多的阈值档位，@StockAnalysis只有单一阈值

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import requests
import time
import akshare as ak
import json
from models import db, User, LoginLog, UserPortfolio, get_beijing_time
from forms import LoginForm, RegistrationForm, UserSettingsForm
import asyncio
import concurrent.futures
import logging
from functools import wraps
import pytz

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-please-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化扩展
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 创建数据库表
with app.app_context():
    db.create_all()

# 公网IP缓存
public_ip_cache = {
    'ip': None,
    'timestamp': 0,
    'expires': 3600  # 缓存有效期1小时
}

# 辅助函数获取客户端真实IP
def get_client_ip(try_public_ip=False):
    """获取客户端真实IP地址，不再费力获取公网IP
    
    Args:
        try_public_ip: 是否尝试获取公网IP（该参数已被忽略）
    
    Returns:
        str: 客户端IP地址
    """
    # 优先使用X-Forwarded-For头
    if 'X-Forwarded-For' in request.headers:
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        return forwarded_for.split(',')[0].strip()
    
    # 其次使用X-Real-IP头
    if 'X-Real-IP' in request.headers:
        return request.headers.get('X-Real-IP', '').strip()
    
    # 再次使用环境变量
    if 'HTTP_X_FORWARDED_FOR' in request.environ:
        return request.environ.get('HTTP_X_FORWARDED_FOR', '').strip()
    
    # 最后使用remote_addr
    return request.remote_addr or '0.0.0.0'

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # GET请求，直接返回登录表单，不进行任何耗时操作
    if request.method == 'GET':
        form = LoginForm()
        return render_template('login.html', form=form)
    
    # 处理POST请求（表单提交）
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            # 记录用户登录IP - 仅在登录成功时获取
            client_ip = get_client_ip(try_public_ip=True)
            user_agent = request.headers.get('User-Agent', '')
            
            # 创建登录日志
            login_log = LoginLog(
                user_id=user.id,
                ip_address=client_ip,
                user_agent=user_agent,
                status='success',
                login_time=get_beijing_time()  # 明确指定使用北京时间
            )
            db.session.add(login_log)
            
            # 更新用户最后登录信息
            user.last_login_at = get_beijing_time()
            user.last_login_ip = client_ip
            db.session.commit()
            
            next_page = request.args.get('next')
            flash('登录成功！', 'success')
            return redirect(next_page or url_for('dashboard'))
        
        # 记录失败的登录尝试
        if user:
            # 登录失败时使用简化的IP获取方式，不尝试获取公网IP
            client_ip = request.remote_addr
            if 'X-Forwarded-For' in request.headers:
                forwarded_for = request.headers.get('X-Forwarded-For', '')
                client_ip = forwarded_for.split(',')[0].strip()
            elif 'X-Real-IP' in request.headers:
                client_ip = request.headers.get('X-Real-IP', '').strip()
            
            login_log = LoginLog(
                user_id=user.id,
                ip_address=client_ip,
                user_agent=request.headers.get('User-Agent', ''),
                status='failed',
                login_time=get_beijing_time()  # 明确指定使用北京时间
            )
            db.session.add(login_log)
            db.session.commit()
            
        flash('用户名或密码错误', 'danger')
    return render_template('login.html', form=form)

# 注册路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('注册成功！请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

# 用户设置路由
@app.route('/user/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    form = UserSettingsForm(original_email=current_user.email)
    
    if form.validate_on_submit():
        # 检查邮箱是否修改
        if form.email.data != current_user.email:
            current_user.email = form.email.data
        
        # 检查是否修改密码
        if form.current_password.data and form.new_password.data:
            if current_user.check_password(form.current_password.data):
                current_user.set_password(form.new_password.data)
                flash('密码已成功更新', 'success')
            else:
                flash('当前密码不正确', 'danger')
                return render_template('user_settings.html', form=form)
        
        db.session.commit()
        flash('设置已保存', 'success')
        return redirect(url_for('user_settings'))
    
    # 表单初始化
    if request.method == 'GET':
        form.email.data = current_user.email
    
    return render_template('user_settings.html', form=form)

# 设置请求超时和重试
# os.environ['http_proxy'] = 'http://127.0.0.1:10808'
# os.environ['https_proxy'] = 'http://127.0.0.1:10808'

# 设置缓存
CACHE_EXPIRATION = 60 * 10  # 缓存10分钟过期
market_data_cache = {
    'data': None,
    'timestamp': 0
}

# 首页数据缓存
dashboard_cache = {
    'data': None,
    'timestamp': 0
}

def load_portfolio(user_id):
    """加载用户投资组合
    
    Args:
        user_id: 用户ID
        
    Returns:
        list: 用户的股票列表
    """
    portfolio_items = UserPortfolio.query.filter_by(user_id=user_id).all()
    portfolio = []
    
    for item in portfolio_items:
        stock_data = item.get_stock_data()
        # 确保基本信息存在
        if not stock_data:
            stock_data = {
                "symbol": item.symbol,
                "name": item.name
            }
        # 确保股票代码和名称是最新的
        stock_data["symbol"] = item.symbol
        stock_data["name"] = item.name
        portfolio.append(stock_data)
    
    return portfolio

def save_portfolio(user_id, portfolio):
    """保存用户投资组合
    
    Args:
        user_id: 用户ID
        portfolio: 用户的股票列表
    """
    # 获取用户当前的投资组合
    current_items = UserPortfolio.query.filter_by(user_id=user_id).all()
    current_symbols = {item.symbol: item for item in current_items}
    
    # 处理新的投资组合
    for stock in portfolio:
        symbol = stock.get("symbol")
        if not symbol:
            continue
            
        # 检查是否已存在
        if symbol in current_symbols:
            # 更新现有记录
            item = current_symbols[symbol]
            item.name = stock.get("name", "")
            item.set_stock_data(stock)
            del current_symbols[symbol]  # 从待处理列表中移除
        else:
            # 添加新记录
            item = UserPortfolio(
                user_id=user_id,
                symbol=symbol,
                name=stock.get("name", "")
            )
            item.set_stock_data(stock)
            db.session.add(item)
    
    # 删除不再存在的股票
    for item in current_symbols.values():
        db.session.delete(item)
    
    # 保存更改
    db.session.commit()

def add_stock_to_portfolio(user_id, stock_data):
    """添加股票到用户投资组合
    
    Args:
        user_id: 用户ID
        stock_data: 股票数据
    """
    symbol = stock_data.get("symbol")
    if not symbol:
        return False
        
    # 检查是否已存在
    existing = UserPortfolio.query.filter_by(user_id=user_id, symbol=symbol).first()
    if existing:
        # 更新现有记录
        existing.name = stock_data.get("name", "")
        existing.set_stock_data(stock_data)
    else:
        # 添加新记录
        item = UserPortfolio(
            user_id=user_id,
            symbol=symbol,
            name=stock_data.get("name", "")
        )
        item.set_stock_data(stock_data)
        db.session.add(item)
    
    # 保存更改
    db.session.commit()
    return True

def remove_stock_from_portfolio(user_id, symbol):
    """从用户投资组合中删除股票
    
    Args:
        user_id: 用户ID
        symbol: 股票代码
    """
    item = UserPortfolio.query.filter_by(user_id=user_id, symbol=symbol).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        return True
    return False

def get_market_data():
    """获取市场数据，带缓存"""
    global market_data_cache
    
    current_time = time.time()
    if (market_data_cache['data'] is None or 
        current_time - market_data_cache['timestamp'] > CACHE_EXPIRATION):
        try:
            # 获取所有A股行情
            market_data_cache['data'] = ak.stock_zh_a_spot_em()
            market_data_cache['timestamp'] = current_time
            print("更新市场数据缓存")
        except Exception as e:
            print(f"获取市场数据失败: {str(e)}")
            # 如果获取失败但有缓存，继续使用缓存
            if market_data_cache['data'] is not None:
                print("使用过期缓存数据")
                
    return market_data_cache['data']

def calculate_stock_score(stock_data):
    """计算股票评分和投资建议（采用@StockAnalysis的评分逻辑）"""
    try:
        # 基本判断，如果数据不足则返回默认值
        if not all(key in stock_data for key in ['current_price', 'change_pct', 'volume', 'turnover']):
            return {
                "score": 50,
                "recommendation": "数据不足",
                "trend": "未知",
                "rsi_signal": "未知",
                "macd_signal": "未知",
                "volume_trend": "未知",
            }
        
        # 根据最新价格和变化率做简单趋势判断
        # 在没有技术指标的情况下，只能做简单判断
        price = stock_data.get('current_price', 0)
        change_pct = stock_data.get('change_pct', 0)
        
        # 使用涨跌幅判断趋势
        trend = "上升" if change_pct > 0 else "下降"
        
        # 成交量分析
        # 将固定阈值判断改为根据股票的历史交易量确定
        # 因为不同股票的成交量基数不同，所以不能用统一的固定阈值
        volume = stock_data.get('volume', 0)
        
        # 获取股票代码，添加对飞沃科技的调试输出
        symbol = stock_data.get('symbol', '')
        
        # 如果之前有交易数据，则与平均值比较；否则用固定阈值
        avg_volume = stock_data.get('avg_volume', 0)
        if avg_volume > 0:
            volume_trend = "放量" if volume > avg_volume else "缩量"
        else:
            # 使用相对固定阈值作为后备方案
            volume_trend = "放量" if volume > 500000 else "缩量"
            
            # 对于飞沃科技等重点关注的股票，记录更详细的信息
            if symbol == "301232":
                print(f"飞沃科技: 没有历史平均成交量数据，使用固定阈值判断，当前成交量: {volume}")
        
        # 根据涨跌幅和成交量简单模拟RSI和MACD信号
        # 这是极度简化的逻辑，实际上需要历史数据计算
        rsi_signal = "中性"
        if change_pct > 5:
            rsi_signal = "超买"
        elif change_pct < -5:
            rsi_signal = "超卖"
            
        macd_signal = "买入" if change_pct > 0 and volume_trend == "放量" else "卖出"
        
        # 使用@StockAnalysis的评分逻辑
        score = 0
        score += 30 if trend == "上升" else 0
        
        # 由于没有真正的RSI值，我们用涨跌幅代替
        # 假设涨跌幅在-2%到+3%之间是"健康的"（相当于RSI 30-70区间）
        rsi_range = -2 <= change_pct <= 3
        score += 20 if rsi_range else 0
        
        score += 20 if macd_signal == "买入" else 0
        score += 15 if volume_trend == "放量" else 0
        
        # 波动率没有，简单假设如果涨跌幅绝对值小于3%，波动率较低
        volatility_low = abs(change_pct) < 3
        score += 15 if volatility_low else 0
        
        # 调试输出
        print(f"DEBUG - 股票列表页面评分计算 ({stock_data['name']}):")
        print(f"  趋势(30分): {trend} -> {30 if trend == '上升' else 0}分")
        print(f"  RSI估计(20分): 使用涨跌幅{change_pct}% -> {20 if rsi_range else 0}分")
        print(f"  MACD估计(20分): {macd_signal} -> {20 if macd_signal == '买入' else 0}分")
        print(f"  成交量(15分): {volume_trend}(成交量:{volume}) -> {15 if volume_trend == '放量' else 0}分")
        print(f"  波动率估计(15分): 使用涨跌幅{abs(change_pct)}% -> {15 if volatility_low else 0}分")
        print(f"  总分: {score}分")
        
        # 根据总分生成投资建议
        if score >= 80:
            recommendation = "强烈推荐买入"
        elif score >= 60:
            recommendation = "建议买入"
        elif score >= 40:
            recommendation = "建议观望"
        elif score >= 20:
            recommendation = "建议减持"
        else:
            recommendation = "建议卖出"
        
        return {
            "score": score,
            "recommendation": recommendation,
            "trend": trend,
            "rsi_signal": rsi_signal,
            "macd_signal": macd_signal,
            "volume_trend": volume_trend,
        }
    except Exception as e:
        print(f"计算评分失败: {str(e)}")
        return {
            "score": 50,
            "recommendation": "数据不足",
            "trend": "未知",
            "rsi_signal": "未知",
            "macd_signal": "未知",
            "volume_trend": "未知",
        }

@app.route('/')
def index():
    """首页路由，显示公开的信息页面"""
    try:
        # 尝试获取市场数据
        # 使用与仪表盘相同的数据获取函数，但不要求登录
        data = get_dashboard_data(force_refresh=False)
        
        # 从缓存中获取指数、行业、涨跌幅数据
        indices = data.get('indices', {})
        industries = data.get('industries', [])
        gainers = data.get('gainers', [])
        losers = data.get('losers', [])
        
        return render_template('index.html', 
                              indices=indices,
                              industries=industries, 
                              gainers=gainers, 
                              losers=losers,
                              last_updated=data.get('last_updated', ''))
    except Exception as e:
        # 如果获取数据失败，仍然显示首页，但不包含动态数据
        logger.error(f"首页获取数据失败: {str(e)}")
        return render_template('index.html')

def get_dashboard_data(force_refresh=False):
    """获取首页数据，带缓存
    
    Args:
        force_refresh (bool): 是否强制刷新缓存
    """
    global dashboard_cache
    
    current_time = time.time()
    
    # 只有在以下情况才刷新缓存:
    # 1. 缓存为空
    # 2. 缓存过期
    # 3. 强制刷新
    if (dashboard_cache['data'] is None or 
        current_time - dashboard_cache['timestamp'] > CACHE_EXPIRATION or
        force_refresh):
        
        print(f"刷新缓存原因: 缓存为空={dashboard_cache['data'] is None}, 缓存过期={(current_time - dashboard_cache['timestamp'] > CACHE_EXPIRATION)}, 强制刷新={force_refresh}")
        
        try:
            # 获取指数数据
            index_map = {
                'sh': ['000001', 'sh000001', 'sh.000001', '上证指数'],
                'sz': ['399001', 'sz399001', 'sz.399001', '深证成指'],
                'cyb': ['399006', 'sz399006', 'sz.399006', '创业板指']
            }
            
            indices = {}
            
            # 使用新浪接口获取指数数据
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(ak.stock_zh_index_spot_sina).result()
                
                # 确保代码列是字符串类型
                df['代码'] = df['代码'].astype(str)
                
                # 遍历每个指数
                for name, code_list in index_map.items():
                    found = False
                    for code in code_list:
                        try:
                            # 尝试通过代码或名称匹配
                            row = df[(df['代码'] == code) | (df['名称'] == code)]
                            if not row.empty:
                                row = row.iloc[0]
                                indices[name] = {
                                    'current': float(row['最新价']),
                                    'change_pct': float(row['涨跌幅']),
                                    'change': float(row['涨跌额'])
                                }
                                found = True
                                break
                        except Exception as e:
                            logger.error(f"处理{name}指数数据失败: {str(e)}")
                    
                    if not found:
                        logger.error(f"未找到{name}指数数据")
                        indices[name] = {
                            'current': 0,
                            'change_pct': 0,
                            'change': 0
                        }
            except Exception as e:
                logger.error(f"获取指数数据失败: {str(e)}")
                for name in index_map.keys():
                    indices[name] = {
                        'current': 0,
                        'change_pct': 0,
                        'change': 0
                    }
        
            # 获取行业板块数据
            industries = []
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(ak.stock_board_industry_name_em).result()
                
                for _, row in df.head(5).iterrows():
                    industries.append({
                        'name': row['板块名称'],
                        'change_pct': float(row['涨跌幅'])
                    })
            except Exception as e:
                logger.error(f"获取行业板块数据失败: {str(e)}")
                industries = []
        
            # 获取涨幅榜数据
            gainers = []
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(ak.stock_zh_a_spot_em).result()
                
                for _, row in df.nlargest(5, '涨跌幅').iterrows():
                    gainers.append({
                        'name': row['名称'],
                        'price': float(row['最新价']),
                        'change_pct': float(row['涨跌幅'])
                    })
            except Exception as e:
                logger.error(f"获取涨幅榜数据失败: {str(e)}")
                gainers = []
            
            # 获取跌幅榜数据
            losers = []
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(ak.stock_zh_a_spot_em).result()
                
                for _, row in df.nsmallest(5, '涨跌幅').iterrows():
                    losers.append({
                        'name': row['名称'],
                        'price': float(row['最新价']),
                        'change_pct': float(row['涨跌幅'])
                    })
            except Exception as e:
                logger.error(f"获取跌幅榜数据失败: {str(e)}")
                losers = []
        
            # 获取趋势数据
            trend_data = {
                'dates': [],
                'sh': [],
                'sz': [],
                'cyb': []
            }
            
            try:
                # 获取最近30天的数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                for name, code_list in index_map.items():
                    try:
                        code = code_list[0]  # 使用第一个代码
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            df = pool.submit(ak.stock_zh_index_daily_em, symbol=code).result()
                        if not df.empty:
                            df = df[(df['date'] >= start_date.strftime('%Y-%m-%d')) & 
                                   (df['date'] <= end_date.strftime('%Y-%m-%d'))]
                            
                            if name == 'sh':
                                trend_data['dates'] = df['date'].tolist()
                            trend_data[name] = df['close'].tolist()
                    except Exception as e:
                        logger.error(f"获取{name}趋势数据失败: {str(e)}")
                        trend_data[name] = []
            except Exception as e:
                logger.error(f"获取趋势数据失败: {str(e)}")

            # 更新缓存
            dashboard_cache['data'] = {
                'indices': indices,
                'industries': industries,
                'gainers': gainers,
                'losers': losers,
                'trend_data': trend_data,
                'last_updated': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')  # 添加最后更新时间（北京时间）
            }
            dashboard_cache['timestamp'] = current_time
            print("更新首页数据缓存")
            
        except Exception as e:
            logger.error(f"获取首页数据失败: {str(e)}")
            if dashboard_cache['data'] is not None:
                print("使用过期缓存数据")
    else:
        print("使用有效的缓存数据，跳过更新")
                
    return dashboard_cache['data']

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        # 检查是否从管理后台返回前台
        from_admin = session.pop('from_admin', False)
        
        # 如果是从管理后台返回，确保使用现有缓存不刷新
        force_refresh = False
        if from_admin:
            print("从管理后台返回前台，使用现有缓存")
        
        data = get_dashboard_data(force_refresh=force_refresh)
        
        # 已经登录的用户，每次进入dashboard时记录当前时间
        # 这样可以跟踪用户活跃状态，但不用每次都刷新数据
        if current_user.is_authenticated:
            # 仅更新用户会话，不刷新数据
            session['last_dashboard_visit'] = int(time.time())
        
        if data is None:
            flash('获取数据失败，请稍后重试', 'error')
            # 返回默认的空数据结构
            return render_template('dashboard.html', 
                                 indices={
                                     'sh': {'current': 0, 'change_pct': 0, 'change': 0},
                                     'sz': {'current': 0, 'change_pct': 0, 'change': 0},
                                     'cyb': {'current': 0, 'change_pct': 0, 'change': 0}
                                 },
                                 industries=[],
                                 gainers=[],
                                 losers=[],
                                 trend_data={'dates': [], 'sh': [], 'sz': [], 'cyb': []},
                                 last_updated="未知")
        
        # 正常返回数据
        return render_template('dashboard.html',
                             indices=data['indices'],
                             industries=data['industries'],
                             gainers=data['gainers'],
                             losers=data['losers'],
                             trend_data=data['trend_data'],
                             last_updated=data.get('last_updated', '未知'))
    except Exception as e:
        logger.error(f"获取首页数据失败: {str(e)}")
        flash('获取数据失败，请稍后重试', 'error')
        # 返回默认的空数据结构
        return render_template('dashboard.html',
                             indices={
                                 'sh': {'current': 0, 'change_pct': 0, 'change': 0},
                                 'sz': {'current': 0, 'change_pct': 0, 'change': 0},
                                 'cyb': {'current': 0, 'change_pct': 0, 'change': 0}
                             },
                             industries=[],
                             gainers=[],
                             losers=[],
                             trend_data={'dates': [], 'sh': [], 'sz': [], 'cyb': []},
                             last_updated="未知")

@app.route('/refresh_dashboard')
@login_required
def refresh_dashboard():
    """强制刷新首页数据"""
    try:
        get_dashboard_data(force_refresh=True)
        flash('数据已刷新', 'success')
    except Exception as e:
        logger.error(f"刷新首页数据失败: {str(e)}")
        flash('刷新数据失败，请稍后重试', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/stocks')
@login_required
def stocks():
    """显示用户添加的股票列表"""
    portfolio = load_portfolio(current_user.id)
    
    # 获取最新行情数据
    if portfolio:
        market_data = get_market_data()
        
        if market_data is not None:
            # 更新组合中的股票行情
            for stock in portfolio:
                stock_code = stock['symbol']
                # 查找对应的行情数据
                match = market_data[market_data['代码'] == stock_code]
                if not match.empty:
                    # 获取历史数据来计算平均成交量和技术指标
                    try:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=180)  # 使用更多历史数据以计算技术指标
                        
                        # 获取历史数据以计算技术指标
                        daily_data = ak.stock_zh_a_hist(
                            symbol=stock_code,
                            period="daily",
                            start_date=start_date.strftime('%Y%m%d'),
                            end_date=end_date.strftime('%Y%m%d'),
                            adjust="qfq"
                        )
                        
                        if daily_data is not None and not daily_data.empty and len(daily_data) >= 20:
                            # 重命名列，确保与模板兼容
                            column_map = {
                                '日期': 'trade_date',
                                '开盘': 'open',
                                '收盘': 'close',
                                '最高': 'high',
                                '最低': 'low',
                                '成交量': 'vol',
                                '成交额': 'amount'
                            }
                            daily_data = daily_data.rename(columns=column_map)
                            
                            # 计算平均成交量，用于判断放量/缩量
                            vol_col = '成交量' if '成交量' in daily_data.columns else 'vol'
                            if vol_col in daily_data.columns:
                                avg_volume = daily_data[vol_col].mean()
                                stock['avg_volume'] = float(avg_volume)
                                
                                if stock_code == "301232":  # 飞沃科技特殊调试
                                    print(f"刷新时飞沃科技历史平均成交量: {avg_volume}, 当前成交量: {float(match.iloc[0]['成交量'])}")
                            
                            # 计算技术指标
                            daily_data = calculate_indicators(daily_data)
                            
                            # 使用与详细分析页面相同的评分逻辑
                            analysis_result = analyze_indicators(daily_data)
                            
                            # 保存详细分析结果
                            stock['analysis_result'] = analysis_result
                            stock['score'] = analysis_result['score']
                            stock['recommendation'] = analysis_result['recommendation']
                            stock['trend'] = analysis_result['trend']
                            stock['rsi'] = analysis_result['rsi']
                            stock['rsi_signal'] = analysis_result['rsi_signal']
                            stock['macd_signal'] = analysis_result['macd_signal']
                            stock['volume_trend'] = analysis_result['volume_trend']
                            
                            # 更新当前行情数据
                            stock['current_price'] = float(match.iloc[0]['最新价'])
                            stock['change_pct'] = float(match.iloc[0]['涨跌幅'])
                            stock['change_amount'] = float(match.iloc[0]['涨跌额'])
                            stock['volume'] = float(match.iloc[0]['成交量'])
                            stock['turnover'] = float(match.iloc[0]['换手率']) if '换手率' in match.iloc[0] else 0
                            stock['last_update'] = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                            
                            print(f"刷新时使用技术指标计算评分: {stock_code}, 评分: {analysis_result['score']}")
                            
                            # 特殊股票调试代码
                            if stock_code == "301011":
                                print(f"刷新时华立科技的技术指标评分: {analysis_result['score']}")
                                print(f"华立科技的数据: {stock}")
                            elif stock_code == "300750":
                                print(f"刷新时宁德时代的技术指标评分: {analysis_result['score']}")
                                print(f"宁德时代的数据: {stock}")
                            elif stock_code == "301232":
                                print(f"刷新时飞沃科技的技术指标评分: {analysis_result['score']}")
                                print(f"飞沃科技的数据: {stock}")
                            
                            continue
                            
                    except Exception as e:
                        print(f"计算技术指标失败: {stock_code}, {str(e)}")
                    
                    # 如果无法计算技术指标，回退到简化评分
                    stock['current_price'] = float(match.iloc[0]['最新价'])
                    stock['change_pct'] = float(match.iloc[0]['涨跌幅'])
                    stock['change_amount'] = float(match.iloc[0]['涨跌额'])
                    stock['volume'] = float(match.iloc[0]['成交量'])
                    stock['turnover'] = float(match.iloc[0]['换手率']) if '换手率' in match.iloc[0] else 0
                    stock['last_update'] = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 计算评分与投资建议（使用简化方法）
                    result = calculate_stock_score(stock)
                    stock['score'] = result['score']
                    stock['recommendation'] = result['recommendation']
                    stock['trend'] = result['trend']
                    stock['rsi_signal'] = result['rsi_signal']
                    stock['macd_signal'] = result['macd_signal']
                    stock['volume_trend'] = result['volume_trend']
                    
                    # 特殊股票调试代码
                    if stock_code == "301011":
                        print(f"刷新时华立科技的简化评分: {result['score']}")
                        print(f"华立科技的数据: {stock}")
                    elif stock_code == "300750":
                        print(f"刷新时宁德时代的简化评分: {result['score']}")
                        print(f"宁德时代的数据: {stock}")
                    elif stock_code == "301232":
                        print(f"刷新时飞沃科技的简化评分: {result['score']}")
                        print(f"飞沃科技的数据: {stock}")
            
            save_portfolio(current_user.id, portfolio)
    
    return render_template('stocks.html', stocks=portfolio)

@app.route('/add_stock', methods=['GET', 'POST'])
@login_required
def add_stock():
    """添加股票到投资组合"""
    if request.method == 'POST':
        stock_code = request.form.get('stock_code', '').strip()
        if not stock_code:
            return render_template('add_stock.html', error='股票代码不能为空')
        
        try:
            # 获取股票信息
            stock_info_df = get_market_data()
            
            if stock_info_df is None:
                return render_template('add_stock.html', error='无法获取市场数据，请稍后重试')
            
            # 找到对应的股票信息
            stock_match = stock_info_df[stock_info_df['代码'] == stock_code]
            if stock_match.empty:
                return render_template('add_stock.html', error=f'未找到股票代码 {stock_code}')
            
            # 创建股票信息
            stock_info = {
                "ts_code": f"{stock_code}.{stock_code[0:1]}H" if stock_code.startswith('6') else f"{stock_code}.SZ",
                "symbol": stock_code,
                "name": stock_match.iloc[0]['名称'],
                "area": "中国",
                "industry": stock_match.iloc[0]['所属行业'] if '所属行业' in stock_match.iloc[0] else "",
                "current_price": float(stock_match.iloc[0]['最新价']),
                "change_pct": float(stock_match.iloc[0]['涨跌幅']),
                "change_amount": float(stock_match.iloc[0]['涨跌额']),
                "volume": float(stock_match.iloc[0]['成交量']),
                "turnover": float(stock_match.iloc[0]['换手率']) if '换手率' in stock_match.iloc[0] else 0,
                "last_update": get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 计算股票评分和投资建议
            try:
                # 获取历史数据来计算技术指标
                end_date = datetime.now()
                start_date = end_date - timedelta(days=180)
                
                daily_data = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust="qfq"
                )
                
                if daily_data is not None and not daily_data.empty and len(daily_data) >= 20:
                    # 重命名列，确保与模板兼容
                    column_map = {
                        '日期': 'trade_date',
                        '开盘': 'open',
                        '收盘': 'close',
                        '最高': 'high',
                        '最低': 'low',
                        '成交量': 'vol',
                        '成交额': 'amount'
                    }
                    daily_data = daily_data.rename(columns=column_map)
                    
                    # 计算技术指标
                    daily_data = calculate_indicators(daily_data)
                    
                    # 使用与详细分析页面相同的评分逻辑
                    analysis_result = analyze_indicators(daily_data)
                    
                    # 保存详细分析结果
                    stock_info['score'] = analysis_result['score']
                    stock_info['recommendation'] = analysis_result['recommendation']
                    stock_info['trend'] = analysis_result['trend']
                    stock_info['rsi'] = analysis_result['rsi']
                    stock_info['rsi_signal'] = analysis_result['rsi_signal']
                    stock_info['macd_signal'] = analysis_result['macd_signal']
                    stock_info['volume_trend'] = analysis_result['volume_trend']
                    
                    print(f"添加股票时使用技术指标计算评分: {stock_code}, 评分: {analysis_result['score']}")
                else:
                    # 如果无法获取足够的历史数据，回退到简化评分
                    result = calculate_stock_score(stock_info)
                    stock_info['score'] = result['score']
                    stock_info['recommendation'] = result['recommendation']
                    stock_info['trend'] = result['trend']
                    stock_info['rsi_signal'] = result['rsi_signal'] 
                    stock_info['macd_signal'] = result['macd_signal']
                    stock_info['volume_trend'] = result['volume_trend']
                    print(f"添加股票时使用简化评分: {stock_code}, 评分: {result['score']}")
            except Exception as e:
                print(f"添加股票时计算技术指标失败: {stock_code}, {str(e)}")
                # 如果计算技术指标失败，回退到简化评分
                result = calculate_stock_score(stock_info)
                stock_info['score'] = result['score']
                stock_info['recommendation'] = result['recommendation']
                stock_info['trend'] = result['trend']
                stock_info['rsi_signal'] = result['rsi_signal']
                stock_info['macd_signal'] = result['macd_signal']
                stock_info['volume_trend'] = result['volume_trend']
            
            # 检查股票是否已存在于投资组合中
            existing = UserPortfolio.query.filter_by(user_id=current_user.id, symbol=stock_code).first()
            if existing:
                return render_template('add_stock.html', error=f'股票 {stock_code} 已在投资组合中')
            
            # 添加到用户投资组合
            success = add_stock_to_portfolio(current_user.id, stock_info)
            if success:
                flash(f'已添加股票 {stock_info["name"]}', 'success')
                return redirect(url_for('stocks'))
            else:
                return render_template('add_stock.html', error=f'添加股票失败')
                
        except Exception as e:
            return render_template('add_stock.html', error=f'添加股票失败: {str(e)}')
    
    return render_template('add_stock.html')

@app.route('/remove_stock/<symbol>')
@login_required
def remove_stock(symbol):
    """从投资组合中删除股票"""
    if remove_stock_from_portfolio(current_user.id, symbol):
        flash(f'已删除股票 {symbol}', 'success')
    else:
        flash(f'股票 {symbol} 不存在', 'danger')
    return redirect(url_for('stocks'))

@app.route('/refresh_stocks')
@login_required
def refresh_stocks():
    """刷新股票数据"""
    portfolio = load_portfolio(current_user.id)
    
    if portfolio:
        # 清除缓存，强制重新获取最新数据
        global market_data_cache
        market_data_cache['data'] = None
        market_data_cache['timestamp'] = 0
        
        market_data = get_market_data()
        
        if market_data is not None:
            # 更新组合中的股票行情
            for stock in portfolio:
                stock_code = stock['symbol']
                # 查找对应的行情数据
                match = market_data[market_data['代码'] == stock_code]
                if not match.empty:
                    # 获取历史数据来计算平均成交量和技术指标
                    try:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=180)  # 使用更多历史数据以计算技术指标
                        
                        # 获取历史数据以计算技术指标
                        daily_data = ak.stock_zh_a_hist(
                            symbol=stock_code,
                            period="daily",
                            start_date=start_date.strftime('%Y%m%d'),
                            end_date=end_date.strftime('%Y%m%d'),
                            adjust="qfq"
                        )
                        
                        if daily_data is not None and not daily_data.empty and len(daily_data) >= 20:
                            # 重命名列，确保与模板兼容
                            column_map = {
                                '日期': 'trade_date',
                                '开盘': 'open',
                                '收盘': 'close',
                                '最高': 'high',
                                '最低': 'low',
                                '成交量': 'vol',
                                '成交额': 'amount'
                            }
                            daily_data = daily_data.rename(columns=column_map)
                            
                            # 计算平均成交量，用于判断放量/缩量
                            vol_col = '成交量' if '成交量' in daily_data.columns else 'vol'
                            if vol_col in daily_data.columns:
                                avg_volume = daily_data[vol_col].mean()
                                stock['avg_volume'] = float(avg_volume)
                                
                                if stock_code == "301232":  # 飞沃科技特殊调试
                                    print(f"刷新时飞沃科技历史平均成交量: {avg_volume}, 当前成交量: {float(match.iloc[0]['成交量'])}")
                            
                            # 计算技术指标
                            daily_data = calculate_indicators(daily_data)
                            
                            # 使用与详细分析页面相同的评分逻辑
                            analysis_result = analyze_indicators(daily_data)
                            
                            # 保存详细分析结果
                            stock['analysis_result'] = analysis_result
                            stock['score'] = analysis_result['score']
                            stock['recommendation'] = analysis_result['recommendation']
                            stock['trend'] = analysis_result['trend']
                            stock['rsi'] = analysis_result['rsi']
                            stock['rsi_signal'] = analysis_result['rsi_signal']
                            stock['macd_signal'] = analysis_result['macd_signal']
                            stock['volume_trend'] = analysis_result['volume_trend']
                            
                            # 更新当前行情数据
                            stock['current_price'] = float(match.iloc[0]['最新价'])
                            stock['change_pct'] = float(match.iloc[0]['涨跌幅'])
                            stock['change_amount'] = float(match.iloc[0]['涨跌额'])
                            stock['volume'] = float(match.iloc[0]['成交量'])
                            stock['turnover'] = float(match.iloc[0]['换手率']) if '换手率' in match.iloc[0] else 0
                            stock['last_update'] = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                            
                            print(f"刷新时使用技术指标计算评分: {stock_code}, 评分: {analysis_result['score']}")
                            
                            # 特殊股票调试代码
                            if stock_code == "301011":
                                print(f"刷新时华立科技的技术指标评分: {analysis_result['score']}")
                                print(f"华立科技的数据: {stock}")
                            elif stock_code == "300750":
                                print(f"刷新时宁德时代的技术指标评分: {analysis_result['score']}")
                                print(f"宁德时代的数据: {stock}")
                            elif stock_code == "301232":
                                print(f"刷新时飞沃科技的技术指标评分: {analysis_result['score']}")
                                print(f"飞沃科技的数据: {stock}")
                            
                            continue
                            
                    except Exception as e:
                        print(f"计算技术指标失败: {stock_code}, {str(e)}")
                    
                    # 如果无法计算技术指标，回退到简化评分
                    stock['current_price'] = float(match.iloc[0]['最新价'])
                    stock['change_pct'] = float(match.iloc[0]['涨跌幅'])
                    stock['change_amount'] = float(match.iloc[0]['涨跌额'])
                    stock['volume'] = float(match.iloc[0]['成交量'])
                    stock['turnover'] = float(match.iloc[0]['换手率']) if '换手率' in match.iloc[0] else 0
                    stock['last_update'] = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 计算评分与投资建议（使用简化方法）
                    result = calculate_stock_score(stock)
                    stock['score'] = result['score']
                    stock['recommendation'] = result['recommendation']
                    stock['trend'] = result['trend']
                    stock['rsi_signal'] = result['rsi_signal']
                    stock['macd_signal'] = result['macd_signal']
                    stock['volume_trend'] = result['volume_trend']
                    
                    # 特殊股票调试代码
                    if stock_code == "301011":
                        print(f"刷新时华立科技的简化评分: {result['score']}")
                        print(f"华立科技的数据: {stock}")
                    elif stock_code == "300750":
                        print(f"刷新时宁德时代的简化评分: {result['score']}")
                        print(f"宁德时代的数据: {stock}")
                    elif stock_code == "301232":
                        print(f"刷新时飞沃科技的简化评分: {result['score']}")
                        print(f"飞沃科技的数据: {stock}")
            
            # 保存更新后的投资组合
            save_portfolio(current_user.id, portfolio)
            flash('股票数据已刷新', 'success')
    
    return redirect(url_for('stocks'))

@app.route('/analysis/<symbol>')
@login_required
def analysis(symbol):
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            print(f"开始第 {attempt + 1} 次尝试获取股票 {symbol} 的数据...")
            
            # 从symbol中提取实际的股票代码
            stock_code = symbol.split('.')[0]
            print(f"提取的股票代码：{stock_code}")
            
            # 获取所有A股数据
            stock_info_df = ak.stock_zh_a_spot_em()
            
            # 找到对应的股票信息
            stock_match = stock_info_df[stock_info_df['代码'] == stock_code]
            if stock_match.empty:
                raise Exception(f"未找到股票代码 {stock_code}")
                
            # 提取股票基本信息
            stock_info = {
                "ts_code": symbol,
                "symbol": stock_code,
                "name": stock_match.iloc[0]['名称'],
                "area": "中国",
                "industry": stock_match.iloc[0]['所属行业'] if '所属行业' in stock_match.iloc[0] else "",
                "list_date": "",
                "current_price": float(stock_match.iloc[0]['最新价']),
                "change_pct": float(stock_match.iloc[0]['涨跌幅']),
                "change_amount": float(stock_match.iloc[0]['涨跌额']),
                "volume": float(stock_match.iloc[0]['成交量']),
                "turnover": float(stock_match.iloc[0]['换手率']) if '换手率' in stock_match.iloc[0] else 0
            }
            
            # 华立科技特殊调试代码
            if stock_code == "301011":
                print("检测到华立科技，进行特殊调试输出...")
                simple_score_result = calculate_stock_score(stock_info)
                print(f"简单评分结果: {simple_score_result}")
                # 保存简化评分结果供后续比较
                stock_info['simple_score'] = simple_score_result['score']
            elif stock_code == "300750":
                print("检测到宁德时代，进行特殊调试输出...")
                simple_score_result = calculate_stock_score(stock_info)
                print(f"简单评分结果: {simple_score_result}")
                # 保存简化评分结果供后续比较
                stock_info['simple_score'] = simple_score_result['score']
            elif stock_code == "301232":
                print("检测到飞沃科技，进行特殊调试输出...")
                
                # 计算飞沃科技的历史平均成交量用于简化评分
                try:
                    hist_start_date = end_date - timedelta(days=30)
                    hist_data = ak.stock_zh_a_hist(
                        symbol=stock_code,
                        period="daily",
                        start_date=hist_start_date.strftime('%Y%m%d'),
                        end_date=end_date.strftime('%Y%m%d'),
                        adjust="qfq"
                    )
                    
                    if hist_data is not None and not hist_data.empty:
                        vol_col = '成交量' if '成交量' in hist_data.columns else 'vol'
                        if vol_col in hist_data.columns:
                            avg_volume = hist_data[vol_col].mean()
                            stock_info['avg_volume'] = float(avg_volume)
                            print(f"飞沃科技历史平均成交量: {avg_volume}, 当前成交量: {stock_info['volume']}")
                except Exception as e:
                    print(f"获取飞沃科技历史成交量失败: {str(e)}")
                    
                simple_score_result = calculate_stock_score(stock_info)
                print(f"简单评分结果: {simple_score_result}")
                # 保存简化评分结果供后续比较
                stock_info['simple_score'] = simple_score_result['score']
            
            print("股票基本信息:", stock_info)
            
            # 获取最近180天的日线数据以计算技术指标
            end_date = get_beijing_time()
            start_date = end_date - timedelta(days=180)
            
            daily_data = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust="qfq"
            )
            
            print(f"获取到日线数据: {len(daily_data)} 条")
            
            if daily_data is None or daily_data.empty:
                print("日线数据为空，使用示例数据")
                daily_data = pd.DataFrame({
                    'trade_date': [end_date.strftime('%Y%m%d')],
                    'open': [10.0],
                    'high': [11.0],
                    'low': [9.0],
                    'close': [10.5],
                    'vol': [1000000],
                    'amount': [10500000]
                })
            else:
                # 重命名列，确保与模板兼容
                column_map = {
                    '日期': 'trade_date',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'vol',
                    '成交额': 'amount'
                }
                daily_data = daily_data.rename(columns=column_map)
                
                # 计算技术指标
                daily_data = calculate_indicators(daily_data)
                
                # 获取最新指标评分
                analysis_result = analyze_indicators(daily_data)
                if stock_code == "301011":
                    print(f"详细分析页面华立科技的评分计算过程:")
                    print(f"  趋势: {analysis_result['trend']}")
                    print(f"  RSI: {analysis_result['rsi']:.2f} -> 信号: {analysis_result['rsi_signal']}")
                    print(f"  MACD信号: {analysis_result['macd_signal']}")
                    print(f"  成交量趋势: {analysis_result['volume_trend']}")
                    print(f"  波动率: {analysis_result['volatility']:.2f}%")
                    print(f"  最终评分: {analysis_result['score']}")
                elif stock_code == "300750":
                    print(f"详细分析页面宁德时代的评分计算过程:")
                    print(f"  趋势: {analysis_result['trend']}")
                    print(f"  RSI: {analysis_result['rsi']:.2f} -> 信号: {analysis_result['rsi_signal']}")
                    print(f"  MACD信号: {analysis_result['macd_signal']}")
                    print(f"  成交量趋势: {analysis_result['volume_trend']}")
                    print(f"  波动率: {analysis_result['volatility']:.2f}%")
                    print(f"  最终评分: {analysis_result['score']}")
                elif stock_code == "301232":
                    print(f"详细分析页面飞沃科技的评分计算过程:")
                    print(f"  趋势: {analysis_result['trend']}")
                    print(f"  RSI: {analysis_result['rsi']:.2f} -> 信号: {analysis_result['rsi_signal']}")
                    print(f"  MACD信号: {analysis_result['macd_signal']}")
                    print(f"  成交量趋势: {analysis_result['volume_trend']}")
                    print(f"  波动率: {analysis_result['volatility']:.2f}%")
                    print(f"  最终评分: {analysis_result['score']}")
                    
                    # 对比简化评分与详细评分差异
                    try:
                        simple_score = stock_info.get('simple_score', None)
                        if simple_score:
                            print(f"评分差异对比 - 飞沃科技:")
                            print(f"  详细评分: {analysis_result['score']}")
                            print(f"  简化评分: {simple_score}")
                            print(f"  差异: {analysis_result['score'] - simple_score}")
                    except Exception as e:
                        print(f"评分对比出错: {str(e)}")
                    
                stock_info.update(analysis_result)
            
            # 获取财务指标
            try:
                fina_indicator = ak.stock_financial_abstract(stock=stock_code)
                print(f"获取到财务指标: {len(fina_indicator)} 条")
                
                # 处理财务指标数据以适应模板
                fina_processed = []
                for _, row in fina_indicator.iterrows():
                    indicator = {
                        'end_date': row['截止日期'] if '截止日期' in row else "",
                        'basic_eps': row['基本每股收益'] if '基本每股收益' in row else 0,
                        'bps': row['每股净资产'] if '每股净资产' in row else 0,
                        'roe': row['净资产收益率'] if '净资产收益率' in row else 0,
                        'roa': 0,  # 暂无ROA数据
                        'net_profit_margin': row['销售净利率'] if '销售净利率' in row else 0
                    }
                    fina_processed.append(indicator)
            except Exception as e:
                print(f"获取财务指标失败: {str(e)}")
                fina_processed = [{
                    'end_date': end_date.strftime('%Y%m%d'),
                    'basic_eps': 0.5,
                    'bps': 5.0,
                    'roe': 10.0,
                    'roa': 5.0,
                    'net_profit_margin': 20.0
                }]
            
            return render_template('analysis.html', 
                                 stock_info=stock_info,
                                 daily_data=daily_data.to_dict('records'),
                                 fina_indicator=fina_processed)
        except Exception as e:
            print(f"错误信息：{str(e)}")
            if attempt < max_retries - 1:
                print(f"尝试 {attempt + 1} 失败，{retry_delay}秒后重试...")
                time.sleep(retry_delay)
            else:
                print("所有重试都失败，返回示例数据")
                example_data = {
                    "stock_info": {
                        "ts_code": symbol,
                        "symbol": symbol.split('.')[0],
                        "name": "示例股票",
                        "area": "示例地区",
                        "industry": "示例行业",
                        "list_date": "20200101",
                        "current_price": 10.5,
                        "change_pct": 2.5,
                        "change_amount": 0.25,
                        "score": 65,
                        "trend": "上升",
                        "rsi_signal": "中性",
                        "macd_signal": "买入",
                        "recommendation": "建议买入"
                    },
                    "daily_data": [{
                        "trade_date": get_beijing_time().strftime('%Y%m%d'),
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.5,
                        "vol": 1000000,
                        "amount": 10500000
                    }],
                    "fina_indicator": [{
                        "end_date": get_beijing_time().strftime('%Y%m%d'),
                        "basic_eps": 0.5,
                        "bps": 5.0,
                        "roe": 10.0,
                        "roa": 5.0,
                        "net_profit_margin": 20.0
                    }]
                }
                return render_template('analysis.html', 
                                     stock_info=example_data["stock_info"],
                                     daily_data=example_data["daily_data"],
                                     fina_indicator=example_data["fina_indicator"])

def calculate_indicators(df):
    """计算技术指标"""
    try:
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # 计算MA
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        
        # 计算波动率
        df['Volatility'] = df['close'].pct_change().rolling(window=20).std() * np.sqrt(252) * 100
        
        # 计算布林带
        df['BBand_middle'] = df['close'].rolling(window=20).mean()
        std = df['close'].rolling(window=20).std()
        df['BBand_upper'] = df['BBand_middle'] + (2 * std)
        df['BBand_lower'] = df['BBand_middle'] - (2 * std)
        
        # 计算相对强度
        df['Strength'] = (df['close'] - df['close'].rolling(window=60).min()) / (df['close'].rolling(window=60).max() - df['close'].rolling(window=60).min()) * 100
        
        return df
        
    except Exception as e:
        print(f"计算技术指标失败: {str(e)}")
        return df

def analyze_indicators(df):
    """分析技术指标生成报告和评分，使用@StockAnalysis的评分逻辑"""
    try:
        if len(df) < 20:
            return {
                "trend": "数据不足",
                "volatility": 0,
                "rsi": 0,
                "rsi_signal": "数据不足",
                "macd_signal": "数据不足",
                "volume_trend": "数据不足",
                "score": 50,
                "recommendation": "数据不足"
            }
            
        latest = df.iloc[-1]
        
        # 趋势分析
        trend = "上升" if latest['MA5'] > latest['MA20'] else "下降"
        
        # 波动性分析
        volatility = float(latest['Volatility'])
        
        # RSI分析
        rsi = float(latest['RSI'])
        rsi_signal = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
        
        # MACD分析
        macd_signal = "买入" if latest['MACD'] > latest['Signal'] else "卖出"
        
        # 成交量分析 - 使用近5日平均与近20日平均比较
        recent_vol_avg = df['vol'].iloc[-5:].mean()
        long_vol_avg = df['vol'].iloc[-20:].mean()
        volume_trend = "放量" if recent_vol_avg > long_vol_avg else "缩量"
        
        # 记录计算过程，便于调试
        recent_vol = recent_vol_avg
        last_vol = float(latest['vol'])
        
        # 计算布林带位置
        bband_position = (latest['close'] - latest['BBand_lower']) / (latest['BBand_upper'] - latest['BBand_lower']) * 100
        bband_signal = "超卖区" if bband_position < 20 else "超买区" if bband_position > 80 else "中性"
        
        # 使用@StockAnalysis的评分逻辑
        score = 0
        score += 30 if trend == "上升" else 0
        score += 20 if 30 < rsi < 70 else 0
        score += 20 if macd_signal == "买入" else 0
        score += 15 if volume_trend == "放量" else 0
        score += 15 if volatility < 30 else 0
        
        print(f"DEBUG - 详细分析页面评分计算:")
        print(f"  趋势(30分): {trend} -> {30 if trend == '上升' else 0}分")
        print(f"  RSI(20分): {rsi:.2f} -> {20 if 30 < rsi < 70 else 0}分")
        print(f"  MACD(20分): {macd_signal} -> {20 if macd_signal == '买入' else 0}分")
        print(f"  成交量(15分): {volume_trend}(最新:{last_vol:.0f}, 近5日均:{recent_vol:.0f}) -> {15 if volume_trend == '放量' else 0}分")
        print(f"  波动率(15分): {volatility:.2f}% -> {15 if volatility < 30 else 0}分")
        print(f"  总分: {score}分")
        
        # 根据总分生成投资建议
        if score >= 80:
            recommendation = "强烈推荐买入"
        elif score >= 60:
            recommendation = "建议买入"
        elif score >= 40:
            recommendation = "建议观望"
        elif score >= 20:
            recommendation = "建议减持"
        else:
            recommendation = "建议卖出"
            
        return {
            "trend": trend,
            "volatility": volatility,
            "rsi": rsi,
            "rsi_signal": rsi_signal,
            "macd_signal": macd_signal,
            "volume_trend": volume_trend,
            "recent_vol": recent_vol,
            "long_vol_avg": long_vol_avg,
            "bband_signal": bband_signal,
            "bband_position": bband_position,
            "score": int(score),
            "recommendation": recommendation
        }
            
    except Exception as e:
        print(f"分析技术指标失败: {str(e)}")
        return {
            "trend": "分析失败",
            "volatility": 0,
            "rsi": 0,
            "rsi_signal": "未知",
            "macd_signal": "未知",
            "volume_trend": "未知",
            "score": 50,
            "recommendation": "数据不足"
        }

# 确保管理员用户存在
def ensure_admin_user():
    """确保系统中有一个admin管理员用户"""
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if admin:
            # 如果admin用户存在但不是管理员，则升级为管理员
            if not admin.is_admin:
                admin.is_admin = True
                db.session.commit()
                print("已将admin用户设置为管理员")
        else:
            # 如果admin用户不存在，则创建一个
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')  # 设置默认密码
            db.session.add(admin)
            db.session.commit()
            print("已创建admin管理员用户，默认密码：admin123")

# 在应用启动时调用
with app.app_context():
    db.create_all()
    ensure_admin_user()

# 管理员路由
@app.route('/admin')
@login_required
def admin_dashboard():
    """管理员控制台首页"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    # 获取统计数据
    stats = {
        'users_count': User.query.count(),
        'active_users_count': User.query.filter_by(is_active=True).count(),
        'admins_count': User.query.filter_by(is_admin=True).count(),
        'login_count': LoginLog.query.filter_by(status='success').count(),
        'failed_login_count': LoginLog.query.filter_by(status='failed').count()
    }
    
    # 获取最近登录记录
    recent_logins = LoginLog.query.order_by(LoginLog.login_time.desc()).limit(10).all()
    
    # 标记用户在管理后台
    session['from_admin'] = True
    
    return render_template('admin/dashboard.html', stats=stats, recent_logins=recent_logins)

@app.route('/admin/users')
@login_required
def admin_users():
    """用户管理页面"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    # 标记用户在管理后台
    session['from_admin'] = True
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit_user(id):
    """编辑用户信息"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    # 标记用户在管理后台
    session['from_admin'] = True
    
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        
        # 如果提供了新密码
        new_password = request.form.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        user.is_active = 'is_active' in request.form
        user.is_admin = 'is_admin' in request.form
        
        db.session.commit()
        flash('用户信息已更新', 'success')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/edit_user.html', user=user, LoginLog=LoginLog)

@app.route('/admin/users/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_user(id):
    """删除用户"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    if id == current_user.id:
        flash('不能删除当前登录的用户', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    
    flash(f'用户 {user.username} 已删除', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/login-logs')
@login_required
def admin_login_logs():
    """登录日志页面"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    # 标记用户在管理后台
    session['from_admin'] = True
    
    page = request.args.get('page', 1, type=int)
    logs = LoginLog.query.order_by(LoginLog.login_time.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/login_logs.html', logs=logs)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    """管理员添加新用户"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('dashboard'))
    
    # 标记用户在管理后台
    session['from_admin'] = True
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_active = 'is_active' in request.form
        is_admin = 'is_admin' in request.form
        
        # 检查用户名和邮箱是否已存在
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return render_template('admin/add_user.html')
        
        if User.query.filter_by(email=email).first():
            flash('邮箱已存在', 'danger')
            return render_template('admin/add_user.html')
        
        # 创建新用户
        user = User(
            username=username,
            email=email,
            is_active=is_active,
            is_admin=is_admin
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'用户 {username} 已创建成功', 'success')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/add_user.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 
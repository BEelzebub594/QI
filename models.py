from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import json
import pytz

db = SQLAlchemy()

# 定义获取北京时间的函数
def get_beijing_time():
    """获取北京时间（UTC+8）"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(beijing_tz)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=get_beijing_time)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(100), nullable=True)
    
    # 一对多关系：一个用户有多个登录记录
    login_logs = db.relationship('LoginLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    # 一对多关系：一个用户有多个股票
    portfolios = db.relationship('UserPortfolio', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def record_login(self, ip_address):
        """记录用户登录信息"""
        self.last_login_at = get_beijing_time()
        self.last_login_ip = ip_address
        
        # 创建新的登录日志
        log = LoginLog(user_id=self.id, ip_address=ip_address)
        db.session.add(log)
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'

class LoginLog(db.Model):
    """用户登录日志模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=get_beijing_time)
    ip_address = db.Column(db.String(100))
    user_agent = db.Column(db.String(255))
    status = db.Column(db.String(20), default='success')  # success, failed
    
    def __repr__(self):
        return f'<LoginLog {self.user_id} {self.login_time}>'

class UserPortfolio(db.Model):
    """用户股票投资组合模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)  # 股票代码
    name = db.Column(db.String(100))  # 股票名称
    added_at = db.Column(db.DateTime, default=get_beijing_time)
    stock_data = db.Column(db.Text)  # 存储股票相关数据的JSON
    
    def get_stock_data(self):
        """获取股票数据"""
        if self.stock_data:
            return json.loads(self.stock_data)
        return {}
    
    def set_stock_data(self, data):
        """设置股票数据"""
        self.stock_data = json.dumps(data, ensure_ascii=False)
    
    def __repr__(self):
        return f'<UserPortfolio {self.user_id} {self.symbol}>' 
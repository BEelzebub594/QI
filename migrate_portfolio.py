import os
import json
from app import app, db
from models import User, UserPortfolio

def migrate_portfolio_data():
    """将现有的portfolio.json文件数据迁移到UserPortfolio表中"""
    portfolio_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio.json')
    
    if not os.path.exists(portfolio_file):
        print(f"portfolio.json文件不存在: {portfolio_file}")
        return
    
    try:
        # 读取现有投资组合数据
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            portfolio_data = json.load(f)
        
        if not portfolio_data:
            print("没有股票数据需要迁移")
            return
        
        # 查找管理员用户
        with app.app_context():
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                print("未找到admin用户，请先确保admin用户存在")
                return
            
            # 迁移每只股票
            for stock in portfolio_data:
                symbol = stock.get('symbol')
                if not symbol:
                    continue
                
                # 检查是否已存在
                existing = UserPortfolio.query.filter_by(user_id=admin_user.id, symbol=symbol).first()
                if existing:
                    print(f"股票 {symbol} 已存在于用户 {admin_user.username} 的投资组合中")
                    # 更新数据
                    existing.name = stock.get('name', '')
                    existing.set_stock_data(stock)
                else:
                    # 创建新记录
                    new_stock = UserPortfolio(
                        user_id=admin_user.id,
                        symbol=symbol,
                        name=stock.get('name', '')
                    )
                    new_stock.set_stock_data(stock)
                    db.session.add(new_stock)
                    print(f"添加股票 {symbol} 到用户 {admin_user.username} 的投资组合中")
            
            # 保存更改
            db.session.commit()
            print(f"成功将 {len(portfolio_data)} 只股票迁移到用户 {admin_user.username} 的投资组合中")
            
            # 备份原始文件
            backup_file = portfolio_file + '.bak'
            os.rename(portfolio_file, backup_file)
            print(f"原始文件已备份为 {backup_file}")
            
    except Exception as e:
        print(f"迁移股票数据失败: {str(e)}")

if __name__ == "__main__":
    migrate_portfolio_data() 
import os
from app import app, db
from models import User, LoginLog

def update_db():
    # 应用上下文中执行所有操作
    with app.app_context():
        # 先删除现有数据库文件
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.db')
        if os.path.exists(db_path):
            print(f"删除旧数据库文件: {db_path}")
            os.remove(db_path)
        
        # 创建新的数据库结构
        db.create_all()
        
        # 创建一个管理员用户
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin', 
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('已创建管理员用户: admin/admin123')
        
        print('数据库迁移完成!')

if __name__ == '__main__':
    update_db() 
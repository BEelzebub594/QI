from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
from models import User

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[
        DataRequired(),
        Length(min=3, max=20, message='用户名长度必须在3-20个字符之间')
    ])
    email = StringField('邮箱', validators=[
        DataRequired(),
        Email(message='请输入有效的邮箱地址')
    ])
    password = PasswordField('密码', validators=[
        DataRequired(),
        Length(min=6, message='密码长度至少为6个字符')
    ])
    password2 = PasswordField('确认密码', validators=[
        DataRequired(),
        EqualTo('password', message='两次输入的密码不一致')
    ])
    submit = SubmitField('注册')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('该用户名已被使用')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('该邮箱已被注册')

class UserSettingsForm(FlaskForm):
    email = StringField('邮箱', validators=[
        DataRequired(),
        Email(message='请输入有效的邮箱地址')
    ])
    current_password = PasswordField('当前密码', validators=[Optional()])
    new_password = PasswordField('新密码', validators=[
        Optional(),
        Length(min=6, message='密码长度至少为6个字符')
    ])
    confirm_password = PasswordField('确认新密码', validators=[
        Optional(),
        EqualTo('new_password', message='两次输入的密码不一致')
    ])
    submit = SubmitField('保存设置')
    
    def __init__(self, original_email, *args, **kwargs):
        super(UserSettingsForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
        
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('该邮箱已被注册') 
import itchat
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

# 配置区（不要修改，通过环境变量配置）
GROUP_NAME = os.getenv('GROUP_NAME', '家庭群')
ADMIN_USER = os.getenv('ADMIN_USER', 'filehelper')
MAX_MEMBERS = 8  # 参与排班的最大人数

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect('duty.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members
                 (userid TEXT PRIMARY KEY,
                  nickname TEXT,
                  jointime INTEGER,
                  active INTEGER DEFAULT 1,
                  on_leave INTEGER DEFAULT 0,
                  sort_order INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedule
                 (date DATE PRIMARY KEY,
                  userid TEXT,
                  notified INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def update_members():
    """更新群成员信息"""
    print("正在更新群成员...")
    group = itchat.search_chatrooms(name=GROUP_NAME)
    if group:
        members = itchat.update_chatroom(group[0]['UserName'])['MemberList'][1:]  # 跳过自己
        conn = sqlite3.connect('duty.db')
        
        # 更新成员信息
        for idx, member in enumerate(members[:MAX_MEMBERS]):
            conn.execute('''INSERT OR IGNORE INTO members 
                            VALUES (?,?,?,1,0,?)''',
                         (member['UserName'], member['NickName'], 
                          int(datetime.now().timestamp()), idx + 1))
        
        # 标记超出的成员为不活跃
        if len(members) > MAX_MEMBERS:
            for member in members[MAX_MEMBERS:]:
                conn.execute('UPDATE members SET active=0 WHERE userid=?', (member['UserName'],))
        
        conn.commit()
        conn.close()

def generate_schedule():
    """生成排班表"""
    print("生成排班表...")
    conn = sqlite3.connect('duty.db')
    active_members = conn.execute('''SELECT userid FROM members 
                                   WHERE active=1 AND on_leave=0
                                   ORDER BY sort_order''').fetchall()
    
    if not active_members:
        print("无有效成员，跳过排班生成")
        return
    
    start_date = datetime.now() + timedelta(days=(7 - datetime.now().weekday()))
    schedule = []
    
    for i in range(7):
        duty_date = start_date + timedelta(days=i)
        user_index = i % len(active_members)
        schedule.append((duty_date.strftime("%Y-%m-%d"), active_members[user_index][0]))
    
    conn.executemany('INSERT OR IGNORE INTO schedule VALUES (?,?,0)', schedule)
    conn.commit()
    conn.close()

def send_reminder():
    """发送提醒"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = sqlite3.connect('duty.db')
    duty = conn.execute('''SELECT m.nickname FROM schedule s
                         JOIN members m ON s.userid = m.userid
                         WHERE s.date=?''', (tomorrow,)).fetchone()
    
    if duty:
        group = itchat.search_chatrooms(name=GROUP_NAME)
        if group:
            msg = f"🗑️ 明日值日提醒：\n@{duty[0]} 同学，请记得倒垃圾！\n（自动提醒，无需回复）"
            itchat.send(msg, group[0]['UserName'])
            print(f"已发送：{msg}")
    
    conn.close()

def send_schedule():
    """发送排班表"""
    conn = sqlite3.connect('duty.db')
    schedule = conn.execute('''SELECT s.date, m.nickname 
                             FROM schedule s
                             JOIN members m ON s.userid = m.userid
                             WHERE s.date BETWEEN date('now', 'weekday 0') 
                             AND date('now', 'weekday 6')''').fetchall()
    
    msg = "📅 下周值日安排：\n" + "\n".join([f"{item[0]}: {item[1]}" for item in schedule])
    itchat.send(msg, toUserName=ADMIN_USER)
    print("排班表已发送到文件传输助手")
    conn.close()

if __name__ == '__main__':
    init_database()
    itchat.auto_login(hotReload=True)
    update_members()
    
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    # 每天19:55提醒
    scheduler.add_job(send_reminder, 'cron', hour=19, minute=55)
    # 每周日19:50生成排班
    scheduler.add_job(generate_schedule, 'cron', day_of_week='sun', hour=19, minute=50)
    # 每周日19:55发排班表
    scheduler.add_job(send_schedule, 'cron', day_of_week='sun', hour=19, minute=55)
    
    print("程序已启动，保持窗口开启！")
    scheduler.start()
    itchat.run()

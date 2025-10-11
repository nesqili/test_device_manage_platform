
# network_device_monitor/frontend/backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import threading
import time
from datetime import datetime
import paramiko
import json
import os

app = Flask(__name__)
CORS(app)

# API路由前缀
API_PREFIX = '/api'

# 数据库初始化配置说明
# DATABASE = 'network_monitor.db'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'network_monitor.db')

def init_db():
    """初始化数据库表结构"""
    with app.app_context():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # 创建设备表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            ip TEXT PRIMARY KEY,
            status TEXT,
            version TEXT,
            uptime TEXT,
            disk_usage REAL,
            cpu_usage REAL,
            user TEXT,
            group_name TEXT,
            last_check TEXT
        )
        ''')
        
        # 创建配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_refresh_enabled INTEGER,
            refresh_interval INTEGER,
            cmd_version TEXT,
            cmd_uptime TEXT,
            cmd_disk TEXT,
            cmd_cpu TEXT,
            device_groups TEXT
        )
        ''')
        
        # 初始化默认配置
        cursor.execute('SELECT COUNT(*) FROM config')
        if cursor.fetchone()[0] == 0:
            default_groups = [
                {"name": "NB2", "devices": [], "sshConfig": {
                    "username": "leapfive",
                    "password": "leapfive",
                    "port": 22,
                    "timeout": 5,
                    "keyAuth": False
                }},
                {"name": "服务器", "devices": [], "sshConfig": {}},
                {"name": "网络设备", "devices": [], "sshConfig": {}},
                {"name": "存储设备", "devices": [], "sshConfig": {}}
            ]
            
            cursor.execute('''
            INSERT INTO config (
                auto_refresh_enabled, 
                refresh_interval, 
                cmd_version, 
                cmd_uptime, 
                cmd_disk, 
                cmd_cpu,
                device_groups
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                1, 
                5,
                'sed -n \'/^PRETTY_NAME=/{s/^PRETTY_NAME=\\"\\([^\\"]*\\).*/\\1/p;q}\' /etc/os-release',
                'uptime | perl -pe \'s/.*up\\s+(?:(\\d+)\\s+days?,\\s+)?(\\d+):.*/($1?$1:0)."天$2小时"/e\'',
                'df -h / | awk \'NR==2{print $5}\'',
                'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\'',
                json.dumps(default_groups)
            ))
        
        conn.commit()
        conn.close()

init_db()

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_ssh_config_for_group(group_name):
    """获取指定分组的SSH配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT device_groups FROM config WHERE id = 1')
    config = cursor.fetchone()
    
    if not config:
        conn.close()
        return None
    
    try:
        groups = json.loads(config['device_groups'])
        for group in groups:
            if group['name'] == group_name:
                ssh_config = group.get('sshConfig', {})
                # 确保返回的配置包含所有必要字段
                return {
                    'username': ssh_config.get('username', 'leapfive'),
                    'password': ssh_config.get('password', 'leapfive'),
                    'port': int(ssh_config.get('port', 22)),
                    'timeout': int(ssh_config.get('timeout', 5)),
                    'keyAuth': bool(ssh_config.get('keyAuth', False)),
                    'keyPath': ssh_config.get('keyPath', ''),
                    'keyPassphrase': ssh_config.get('keyPassphrase', '')
                }
        return None
    except json.JSONDecodeError:
        return None
    finally:
        conn.close()

def check_device_status(ip, group_name=None):
    print(f"开始检查设备状态: IP={ip}, 分组={group_name}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取分组SSH配置
        ssh_config = get_ssh_config_for_group(group_name or 'NB2')
        if not ssh_config:
            print("错误: 无法获取设备分组配置")
            return False
            
        print(f"使用的SSH配置: {ssh_config}")
        
        # 连接SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if ssh_config.get('keyAuth', False):
                print("尝试使用SSH密钥认证")
                private_key = paramiko.RSAKey.from_private_key_file(
                    ssh_config.get('keyPath', ''),
                    password=ssh_config.get('keyPassphrase', None)
                )
                ssh.connect(
                    ip,
                    port=ssh_config['port'],
                    username=ssh_config['username'],
                    pkey=private_key,
                    timeout=ssh_config['timeout']
                )
            else:
                print("尝试使用密码认证")
                ssh.connect(
                    ip,
                    port=ssh_config['port'],
                    username=ssh_config['username'],
                    password=ssh_config['password'],
                    timeout=ssh_config['timeout']
                )
            
            print("SSH连接成功，开始执行命令获取设备信息")
            
            # 获取系统配置中的命令
            cursor.execute('SELECT cmd_version, cmd_uptime, cmd_disk, cmd_cpu FROM config WHERE id = 1')
            config = dict(cursor.fetchone())
            
            # 执行命令获取系统信息
            version = '-'
            uptime = '-'
            disk_usage = '0'
            cpu_usage = '0'
            
            try:
                stdin, stdout, stderr = ssh.exec_command(config['cmd_version'])
                version = stdout.read().decode().strip() or '-'
                print(f"系统版本: {version}")
            except Exception as e:
                print(f"获取版本信息失败: {str(e)}")
            
            try:
                stdin, stdout, stderr = ssh.exec_command(config['cmd_uptime'])
                uptime = stdout.read().decode().strip() or '-'
                print(f"在线时长: {uptime}")
            except Exception as e:
                print(f"获取在线时长失败: {str(e)}")
            
            try:
                stdin, stdout, stderr = ssh.exec_command(config['cmd_disk'])
                disk_usage = stdout.read().decode().strip().replace('%', '') or '0'
                print(f"磁盘占用: {disk_usage}%")
            except Exception as e:
                print(f"获取磁盘占用失败: {str(e)}")
            
            try:
                stdin, stdout, stderr = ssh.exec_command(config['cmd_cpu'])
                cpu_usage = stdout.read().decode().strip() or '0'
                print(f"CPU占用: {cpu_usage}%")
            except Exception as e:
                print(f"获取CPU占用失败: {str(e)}")
            
            ssh.close()
            
            # 更新设备状态
            cursor.execute('''
            UPDATE devices SET 
                status = ?,
                version = ?,
                uptime = ?,
                disk_usage = ?,
                cpu_usage = ?,
                last_check = ?
            WHERE ip = ?
            ''', (
                'online',
                version,
                uptime,
                float(disk_usage),
                float(cpu_usage),
                datetime.now().isoformat(),
                ip
            ))
            
            conn.commit()
            print("设备状态更新成功")
            return True
        except Exception as e:
            print(f"SSH连接或命令执行失败: {str(e)}")
            raise
    except Exception as e:
        print(f'检查设备 {ip} 状态失败: {str(e)}')
        # 更新为离线状态
        cursor.execute('''
        UPDATE devices SET 
            status = ?,
            last_check = ?
        WHERE ip = ?
        ''', (
            'offline',
            datetime.now().isoformat(),
            ip
        ))
        conn.commit()
        return False
    finally:
        conn.close()

# 定时检查所有设备状态
def periodic_check_devices():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 检查是否有设备
            cursor.execute('SELECT COUNT(*) FROM devices')
            device_count = cursor.fetchone()[0]
            
            if device_count > 0:
                cursor.execute('SELECT * FROM config WHERE id = 1')
                config = dict(cursor.fetchone())
                
                if config and config.get('auto_refresh_enabled', True):
                    interval = config.get('refresh_interval', 5) * 60
                    print(f"开始自动刷新设备状态，共 {device_count} 台设备")
                    cursor.execute('SELECT ip, group_name FROM devices')
                    devices = cursor.fetchall()
                    
                    for device in devices:
                        check_device_status(device['ip'], device['group_name'])
                    
                    # 等待配置的间隔时间
                    sleep_time = config.get('refresh_interval', 5) * 60
                    print(f"自动刷新完成，等待 {sleep_time} 秒后再次刷新")
                    time.sleep(sleep_time)
                else:
                    # 自动刷新未启用，等待1分钟后重试
                    print("自动刷新未启用，等待60秒")
                    time.sleep(60)
            else:
                # 没有设备，等待1分钟后重试
                print("没有设备需要监控，等待60秒")
                time.sleep(60)
                
            conn.close()
        except Exception as e:
            print(f'定时任务出错: {str(e)}')
            time.sleep(60)

# 启动后台定时任务
threading.Thread(target=periodic_check_devices, daemon=True).start()

# API路由
@app.route(f'{API_PREFIX}/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM config WHERE id = 1')
        config = dict(cursor.fetchone())
        
        conn.close()
        return jsonify({
            'autoRefreshEnabled': bool(config['auto_refresh_enabled']),
            'refreshInterval': config['refresh_interval'],
            'cmdVersion': config['cmd_version'],
            'cmdUptime': config['cmd_uptime'],
            'cmdDisk': config['cmd_disk'],
            'cmdCpu': config['cmd_cpu'],
            'deviceGroups': json.loads(config['device_groups'])
        })
    else:
        try:
            data = request.json
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE config SET
                auto_refresh_enabled = ?,
                refresh_interval = ?,
                cmd_version = ?,
                cmd_uptime = ?,
                cmd_disk = ?,
                cmd_cpu = ?,
                device_groups = ?
            WHERE id = 1
            ''', (
                int(data.get('autoRefreshEnabled', True)),
                data.get('refreshInterval', 5),
                data.get('cmdVersion', 'sed -n \'/^PRETTY_NAME=/{s/^PRETTY_NAME=\\"\\([^\\"]*\\).*/\\1/p;q}\' /etc/os-release'),
                data.get('cmdUptime', 'uptime | perl -pe \'s/.*up\\s+(?:(\\d+)\\s+days?,\\s+)?(\\d+):.*/($1?$1:0)."天$2小时"/e\''),
                data.get('cmdDisk', 'df -h / | awk \'NR==2{print $5}\''),
                data.get('cmdCpu', 'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\''),
                json.dumps(data.get('deviceGroups', []))
            ))
            
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()

@app.route(f'{API_PREFIX}/devices', methods=['GET', 'POST'])
def handle_devices():
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM devices')
        devices = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(devices)
    else:
        try:
            data = request.json
            if not data or 'ip' not in data:
                return jsonify({'success': False, 'error': 'Missing required fields'}), 400
                
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO devices (
                ip, status, version, uptime, disk_usage, cpu_usage, user, group_name, last_check
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['ip'],
                'offline',
                '-',
                '-',
                0,
                0,
                data.get('user', '未分配'),
                data.get('group', 'NB2'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            
            # 立即检查新设备状态
            threading.Thread(target=check_device_status, args=(data['ip'], data.get('group', 'NB2'))).start()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()

@app.route(f'{API_PREFIX}/devices/<ip>', methods=['GET', 'PATCH', 'DELETE'])
def handle_device(ip):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM devices WHERE ip = ?', (ip,))
        device = cursor.fetchone()
        
        conn.close()
        return jsonify(dict(device)) if device else ('', 404)
    elif request.method == 'PATCH':
        try:
            data = request.json
            conn = get_db_connection()
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if 'user' in data:
                updates.append('user = ?')
                params.append(data['user'])
            
            if 'group' in data:
                updates.append('group_name = ?')
                params.append(data['group'])
            
            if updates:
                query = 'UPDATE devices SET ' + ', '.join(updates) + ' WHERE ip = ?'
                params.append(ip)
                cursor.execute(query, params)
                conn.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()
    elif request.method == 'DELETE':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM devices WHERE ip = ?', (ip,))
            conn.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()

@app.route(f'{API_PREFIX}/devices/check-all', methods=['POST'])
def check_all_devices():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT ip, group_name FROM devices')
        devices = cursor.fetchall()
        
        for device in devices:
            check_device_status(device['ip'], device['group_name'])
        
        cursor.execute('SELECT * FROM devices')
        updated_devices = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(updated_devices)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route(f'{API_PREFIX}/devices/<ip>/check', methods=['POST'])
def check_single_device(ip):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT group_name FROM devices WHERE ip = ?', (ip,))
        device = cursor.fetchone()
        
        if device:
            check_device_status(ip, device['group_name'])
            cursor.execute('SELECT * FROM devices WHERE ip = ?', (ip,))
            updated_device = dict(cursor.fetchone())
            return jsonify(updated_device)
        else:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='192.168.1.79', port=5005)

# network_device_monitor/frontend/backend/app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import threading
import time
from datetime import datetime
import paramiko
import json
import os
import socket

app = Flask(__name__, static_folder='../')
CORS(app)

# API路由前缀
API_PREFIX = '/api'

# 数据库初始化配置说明
# DATABASE = 'network_monitor.db'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'network_monitor.db')

DEFAULT_CMD_UPTIME = "awk '{t=int($1);d=int(t/86400);h=int((t%86400)/3600);printf \"%d天%02d小时\",d,h}' /proc/uptime"
OLD_DEFAULT_CMD_UPTIME_PERL = 'uptime | perl -pe \'s/.*up\\s+(?:(\\d+)\\s+days?,\\s+)?(\\d+):.*/($1?$1:0)."天$2小时"/e\''
OLD_DEFAULT_CMD_UPTIME_AWK = 'uptime | awk -F\'up\\\\s*|,\\\\\\\\s*\' \'{d=$2;sub(/ days?/,"",d);h=$3;sub(/:.*/,"",h);print d" 天 "h" 小时"}\''

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
                'grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d \'"\'',
                DEFAULT_CMD_UPTIME,
                'df -h / | awk \'NR==2{print $5}\'',
                'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\'',
                json.dumps(default_groups)
            ))

        cursor.execute('SELECT cmd_uptime FROM config WHERE id = 1')
        row = cursor.fetchone()
        # 仅当检测到已知的旧版或无效命令时才强制更新，允许用户自定义其他命令
        if row and row[0] in (OLD_DEFAULT_CMD_UPTIME_PERL, OLD_DEFAULT_CMD_UPTIME_AWK, 'uptime'):
            print(f"检测到旧的 uptime 命令: {row[0]}，正在更新为默认推荐命令")
            cursor.execute('UPDATE config SET cmd_uptime = ? WHERE id = 1', (DEFAULT_CMD_UPTIME,))
        
        # Check if refresh_status column exists
        cursor.execute("PRAGMA table_info(devices)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'refresh_status' not in columns:
            cursor.execute('ALTER TABLE devices ADD COLUMN refresh_status TEXT DEFAULT "-"')

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
        
        # Set status to refreshing
        cursor.execute("UPDATE devices SET refresh_status = 'refreshing' WHERE ip = ?", (ip,))
        conn.commit()
        
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
                print(f"执行版本命令: {config['cmd_version']}")
                stdin, stdout, stderr = ssh.exec_command(config['cmd_version'])
                version = stdout.read().decode().strip() or '-'
                print(f"系统版本: {version}")
            except Exception as e:
                print(f"获取版本信息失败: {str(e)}")
            
            try:
                print(f"执行uptime命令: {config['cmd_uptime']}")
                stdin, stdout, stderr = ssh.exec_command(config['cmd_uptime'])
                uptime = stdout.read().decode().strip() or '-'
                print(f"在线时长: {uptime}")
            except Exception as e:
                print(f"获取在线时长失败: {str(e)}")
            
            try:
                print(f"执行磁盘命令: {config['cmd_disk']}")
                stdin, stdout, stderr = ssh.exec_command(config['cmd_disk'])
                disk_usage = stdout.read().decode().strip().replace('%', '') or '0'
                print(f"磁盘占用: {disk_usage}%")
            except Exception as e:
                print(f"获取磁盘占用失败: {str(e)}")
            
            try:
                print(f"执行CPU命令: {config['cmd_cpu']}")
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
                last_check = ?,
                refresh_status = 'success'
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
            last_check = ?,
            refresh_status = 'failed'
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
                data.get('cmdVersion', 'grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d \'"\''),
                data.get('cmdUptime', DEFAULT_CMD_UPTIME),
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
            
            group = data.get('group') or data.get('group_name') or 'NB2'
            user = data.get('user', '未分配')

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
                user,
                group,
                datetime.now().isoformat()
            ))
            
            conn.commit()

            cursor.execute('SELECT * FROM devices WHERE ip = ?', (data['ip'],))
            device = cursor.fetchone()
            
            # 立即检查新设备状态
            threading.Thread(target=check_device_status, args=(data['ip'], group)).start()
            
            if device:
                return jsonify(dict(device))

            return jsonify({
                'ip': data['ip'],
                'status': 'offline',
                'version': '-',
                'uptime': '-',
                'disk_usage': 0,
                'cpu_usage': 0,
                'user': user,
                'group_name': group,
                'last_check': datetime.now().isoformat()
            })
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

def run_check_all_devices():
    """Execute check all devices with priority"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Set all to refreshing initially
        cursor.execute("UPDATE devices SET refresh_status = 'refreshing'")
        conn.commit()
        
        cursor.execute('SELECT * FROM devices')
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Priority sorting
        def priority_key(d):
            # 1. Online Non-Server
            # 2. Online Server
            # 3. Offline Server
            # 4. Offline Device
            is_online = d.get('status') == 'online'
            is_server = d.get('group_name') == '服务器'
            
            if is_online and not is_server: return 0
            if is_online and is_server: return 1
            if not is_online and is_server: return 2
            return 3
            
        devices.sort(key=priority_key)
        
        for device in devices:
            check_device_status(device['ip'], device['group_name'])
            
    except Exception as e:
        print(f"Error in run_check_all_devices: {e}")

@app.route(f'{API_PREFIX}/devices/check-all', methods=['POST'])
def check_all_devices():
    threading.Thread(target=run_check_all_devices).start()
    return jsonify({'success': True, 'message': 'Refresh started'})

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

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/config')
def serve_config():
    return send_from_directory(app.static_folder, 'config.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

if __name__ == '__main__':
    host = os.environ.get('HOST') or '0.0.0.0'
    port = int(os.environ.get('PORT') or 5005)
    print(f"API服务启动: http://{get_local_ip()}:{port}")
    app.run(debug=True, host=host, port=port)
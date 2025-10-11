
# network_device_monitor/frontend/backend/db.py
import sqlite3
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path='network_monitor.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables if they don't exist"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create devices table
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
            
            # Create config table
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
            
            # Initialize default config if not exists
            cursor.execute('SELECT COUNT(*) FROM config')
            if cursor.fetchone()[0] == 0:
                default_groups = [
                    {
                        "name": "NB2", 
                        "devices": [], 
                        "sshConfig": {
                            "username": "leapfive",
                            "password": "leapfive",
                            "port": 22,
                            "timeout": 5,
                            "keyAuth": False,
                            "keyPath": "",
                            "keyPassphrase": ""
                        }
                    },
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
                    'sed -n \'/^PRETTY_NAME=/{s/^PRETTY_NAME=\\"\\([^"]*\\).*/\\1/p;q}\' /etc/os-release',
                    'uptime | awk -F\'up\\\\s*|,\\\\\\\\s*\' \'{d=$2;sub(/ days?/,"",d);h=$3;sub(/:.*/,"",h);print d" 天 "h" 小时"}\'',
                    'df -h / | awk \'NR==2{print $5}\'',
                    'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\'',
                    json.dumps(default_groups, ensure_ascii=False)
                ))
            
            conn.commit()
    
    def _get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_all_devices(self):
        """Get all devices from database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_device(self, ip):
        """Get a single device by IP"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE ip = ?', (ip,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def add_device(self, device_data):
        """
        Add or update a device
        Args:
            device_data: {
                'ip': str,
                'status': str (optional),
                'version': str (optional),
                'uptime': str (optional),
                'disk_usage': float (optional),
                'cpu_usage': float (optional),
                'user': str (optional),
                'group': str (optional)
            }
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO devices (
                ip, status, version, uptime, disk_usage, cpu_usage, user, group_name, last_check
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_data['ip'],
                device_data.get('status', 'offline'),
                device_data.get('version', '-'),
                device_data.get('uptime', '-'),
                device_data.get('disk_usage', 0),
                device_data.get('cpu_usage', 0),
                device_data.get('user', '未分配'),
                device_data.get('group', 'NB2'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
    
    def update_device(self, ip, update_data):
        """
        Update device fields
        Args:
            ip: str - device IP
            update_data: dict - fields to update
        """
        if not update_data:
            return
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            set_clauses = []
            params = []
            
            if 'user' in update_data:
                set_clauses.append('user = ?')
                params.append(update_data['user'])
            
            if 'group' in update_data:
                set_clauses.append('group_name = ?')
                params.append(update_data['group'])
            
            if set_clauses:
                query = 'UPDATE devices SET ' + ', '.join(set_clauses) + ' WHERE ip = ?'
                params.append(ip)
                cursor.execute(query, params)
                conn.commit()
    
    def delete_device(self, ip):
        """Delete a device by IP"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM devices WHERE ip = ?', (ip,))
            conn.commit()
    
    def get_config(self):
        """Get system configuration"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM config WHERE id = 1')
            config = cursor.fetchone()
            
            if config:
                return {
                    'autoRefreshEnabled': bool(config['auto_refresh_enabled']),
                    'refreshInterval': config['refresh_interval'],
                    'cmdVersion': config['cmd_version'],
                    'cmdUptime': config['cmd_uptime'],
                    'cmdDisk': config['cmd_disk'],
                    'cmdCpu': config['cmd_cpu'],
                    'deviceGroups': json.loads(config['device_groups'])
                }
            return None
    
    def update_config(self, config_data):
        """
        Update system configuration
        Args:
            config_data: {
                'autoRefreshEnabled': bool,
                'refreshInterval': int,
                'cmdVersion': str,
                'cmdUptime': str,
                'cmdDisk': str,
                'cmdCpu': str,
                'deviceGroups': list
            }
        """
        with self._get_connection() as conn:
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
                int(config_data.get('autoRefreshEnabled', True)),
                config_data.get('refreshInterval', 5),
                config_data.get('cmdVersion', 'sed -n \'/^PRETTY_NAME=/{s/^PRETTY_NAME=\\"\\([^"]*\\).*/\\1/p;q}\' /etc/os-release'),
                config_data.get('cmdUptime', 'uptime | awk -F\'up\\\\s*|,\\\\\\\\s*\' \'{d=$2;sub(/ days?/,"",d);h=$3;sub(/:.*/,"",h);print d" 天 "h" 小时"}\''),
                config_data.get('cmdDisk', 'df -h / | awk \'NR==2{print $5}\''),
                config_data.get('cmdCpu', 'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\''),
                json.dumps(config_data.get('deviceGroups', []), ensure_ascii=False)
            ))
            
            conn.commit()
    
    def get_group_ssh_config(self, group_name):
        """
        Get SSH config for a specific group with default values
        Args:
            group_name: str - group name to get config for
        Returns:
            dict - SSH configuration with default values
        """
        config = self.get_config()
        if not config:
            return {
                'username': 'leapfive',
                'password': 'leapfive',
                'port': 22,
                'timeout': 5,
                'keyAuth': False,
                'keyPath': '',
                'keyPassphrase': ''
            }
            
        for group in config['deviceGroups']:
            if group['name'] == group_name:
                ssh_config = group.get('sshConfig', {})
                return {
                    'username': ssh_config.get('username', 'leapfive'),
                    'password': ssh_config.get('password', 'leapfive'),
                    'port': ssh_config.get('port', 22),
                    'timeout': ssh_config.get('timeout', 5),
                    'keyAuth': ssh_config.get('keyAuth', False),
                    'keyPath': ssh_config.get('keyPath', ''),
                    'keyPassphrase': ssh_config.get('keyPassphrase', '')
                }
                
        return {
            'username': 'leapfive',
            'password': 'leapfive',
            'port': 22,
            'timeout': 5,
            'keyAuth': False,
            'keyPath': '',
            'keyPassphrase': ''
        }

# network_device_monitor/frontend/backend/tasks.py
import time
import threading
from datetime import datetime
import paramiko
from .db import DatabaseManager

class DeviceMonitor:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.running = False
        self.thread = None

    def start(self):
        """启动定时监控任务"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """停止定时监控任务"""
        self.running = False
        if self.thread:
            self.thread.join()

    def _monitor_loop(self):
        """定时监控循环"""
        while self.running:
            try:
                devices = self.db_manager.get_all_devices()
                if not devices:
                    print("没有设备需要监控，等待60秒")
                    time.sleep(60)
                    continue
                    
                config = self.db_manager.get_config()
                if config and config.get('autoRefreshEnabled', True):
                    interval = config.get('refreshInterval', 5) * 60
                    print(f"开始自动刷新设备状态，共 {len(devices)} 台设备")
                    self.check_all_devices()
                    print(f"自动刷新完成，等待 {interval} 秒后再次刷新")
                    time.sleep(interval)
                else:
                    print("自动刷新未启用，等待60秒")
                    time.sleep(60)
            except Exception as e:
                print(f'定时任务出错: {str(e)}')
                time.sleep(60)

    def check_all_devices(self):
        """检查所有设备状态"""
        devices = self.db_manager.get_all_devices()
        for device in devices:
            self.check_device_status(device['ip'], device.get('group_name'))

    def check_device_status(self, ip, group_name=None):
        """
        检查单个设备状态
        Args:
            ip: 设备IP
            group_name: 设备所属分组
        """
        print(f"开始检查设备状态: IP={ip}, 分组={group_name}")
        try:
            config = self.db_manager.get_config()
            if not config:
                print("无法获取系统配置")
                return False
                
            groups = config.get('deviceGroups', [])
            group = next((g for g in groups if g['name'] == group_name), None)
            ssh_config = group.get('sshConfig', {}) if group else {}

            if not ssh_config:
                print(f"未找到分组 {group_name} 的SSH配置，使用默认配置")
                ssh_config = {
                    'username': 'leapfive',
                    'password': 'leapfive',
                    'port': 22,
                    'timeout': 5,
                    'keyAuth': False
                }

            print(f"使用SSH配置: {ssh_config}")

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
                        port=int(ssh_config.get('port', 22)),
                        username=ssh_config.get('username', 'leapfive'),
                        pkey=private_key,
                        timeout=int(ssh_config.get('timeout', 5))
                    )
                else:
                    print("尝试使用密码认证")
                    ssh.connect(
                        ip,
                        port=int(ssh_config.get('port', 22)),
                        username=ssh_config.get('username', 'leapfive'),
                        password=ssh_config.get('password', 'leapfive'),
                        timeout=int(ssh_config.get('timeout', 5))
                    )

                print("SSH连接成功，开始执行命令获取设备信息")

                # 执行命令获取系统信息
                stdin, stdout, stderr = ssh.exec_command(config['cmdVersion'])
                version = stdout.read().decode().strip() or '-'
                print(f"系统版本: {version}")
                
                stdin, stdout, stderr = ssh.exec_command(config['cmdUptime'])
                uptime = stdout.read().decode().strip() or '-'
                print(f"在线时长: {uptime}")
                
                stdin, stdout, stderr = ssh.exec_command(config['cmdDisk'])
                disk_usage_str = stdout.read().decode().strip().replace('%', '') or '0'
                disk_usage = float(disk_usage_str) if disk_usage_str.replace('.', '').isdigit() else 0
                print(f"磁盘占用: {disk_usage}%")
                
                stdin, stdout, stderr = ssh.exec_command(config['cmdCpu'])
                cpu_usage_str = stdout.read().decode().strip() or '0'
                cpu_usage = float(cpu_usage_str) if cpu_usage_str.replace('.', '').isdigit() else 0
                print(f"CPU占用: {cpu_usage}%")
                
                ssh.close()

                self.db_manager.add_device({
                    'ip': ip,
                    'status': 'online',
                    'version': version,
                    'uptime': uptime,
                    'disk_usage': disk_usage,
                    'cpu_usage': cpu_usage,
                    'group': group_name,
                    'last_check': datetime.now().isoformat()
                })
                
                print(f"设备 {ip} 状态更新成功")
                return True
            except paramiko.AuthenticationException as e:
                print(f"SSH认证失败: {str(e)}")
                raise
            except paramiko.SSHException as e:
                print(f"SSH连接错误: {str(e)}")
                raise
            except Exception as e:
                print(f"命令执行错误: {str(e)}")
                raise
        except Exception as e:
            print(f'检查设备 {ip} 状态失败: {str(e)}')
            self.db_manager.add_device({
                'ip': ip,
                'status': 'offline',
                'last_check': datetime.now().isoformat(),
                'group': group_name
            })
            return False

def start_monitor(db_manager):
    """启动设备监控服务"""
    monitor = DeviceMonitor(db_manager)
    monitor.start()
    return monitor
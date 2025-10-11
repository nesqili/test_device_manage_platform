
# network_device_monitor/backend/api.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import json
from .db import DatabaseManager
from .tasks import DeviceMonitor

api_bp = Blueprint('api', __name__, url_prefix='/api')
db_manager = DatabaseManager()
monitor = DeviceMonitor(db_manager)

@api_bp.route('/devices', methods=['GET', 'POST'])
def handle_devices():
    if request.method == 'GET':
        try:
            devices = db_manager.get_all_devices()
            return jsonify(devices)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    else:
        try:
            data = request.json
            if not data or 'ip' not in data:
                return jsonify({'success': False, 'error': 'Missing required fields'}), 400
            
            device_data = {
                'ip': data['ip'],
                'status': 'offline',
                'version': '-',
                'uptime': '-',
                'disk_usage': 0,
                'cpu_usage': 0,
                'user': data.get('user', '未分配'),
                'group': data.get('group', '默认分组'),
                'last_check': datetime.now().isoformat()
            }
            
            db_manager.add_device(device_data)
            
            # 启动异步状态检查
            monitor.check_device_status(data['ip'], data.get('group', '默认分组'))
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/devices/<ip>', methods=['GET', 'PATCH', 'DELETE'])
def handle_device(ip):
    if request.method == 'GET':
        try:
            device = db_manager.get_device(ip)
            if device:
                return jsonify(device)
            else:
                return jsonify({'success': False, 'error': 'Device not found'}), 404
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    elif request.method == 'PATCH':
        try:
            data = request.json
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
                
            update_data = {}
            if 'user' in data:
                update_data['user'] = data['user']
            if 'group' in data:
                update_data['group'] = data['group']
                
            if update_data:
                db_manager.update_device(ip, update_data)
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'No valid fields to update'}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    elif request.method == 'DELETE':
        try:
            db_manager.delete_device(ip)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/devices/check-all', methods=['POST'])
def check_all_devices():
    try:
        devices = db_manager.get_all_devices()
        for device in devices:
            monitor.check_device_status(device['ip'], device.get('group_name'))
        
        updated_devices = db_manager.get_all_devices()
        return jsonify(updated_devices)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/devices/<ip>/check', methods=['POST'])
def check_single_device(ip):
    try:
        device = db_manager.get_device(ip)
        if device:
            monitor.check_device_status(ip, device.get('group_name'))
            updated_device = db_manager.get_device(ip)
            return jsonify(updated_device)
        else:
            return jsonify({'success': False, 'error': 'Device not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        try:
            config = db_manager.get_config()
            return jsonify(config)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    else:
        try:
            data = request.json
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
                
            config_data = {
                'autoRefreshEnabled': data.get('autoRefreshEnabled', True),
                'refreshInterval': data.get('refreshInterval', 5),
                'cmdVersion': data.get('cmdVersion', 'cat /etc/os-release'),
                'cmdUptime': data.get('cmdUptime', 'uptime'),
                'cmdDisk': data.get('cmdDisk', 'df -h / | awk \'NR==2{print $5}\''),
                'cmdCpu': data.get('cmdCpu', 'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\([0-9.]*\\)%* id.*/\\1/\' | awk \'{print 100 - $1}\''),
                'deviceGroups': data.get('deviceGroups', [])
            }
            
            db_manager.update_config(config_data)
            
            # 重启监控任务以应用新的刷新间隔
            monitor.stop()
            monitor.start()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/config/group-ssh/<group_name>', methods=['GET', 'POST'])
def handle_group_ssh_config(group_name):
    if request.method == 'GET':
        try:
            ssh_config = db_manager.get_group_ssh_config(group_name)
            return jsonify(ssh_config)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    else:
        try:
            data = request.json
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
                
            config = db_manager.get_config()
            if not config:
                return jsonify({'success': False, 'error': 'Config not found'}), 404
                
            # 更新指定分组的SSH配置
            updated = False
            for group in config['deviceGroups']:
                if group['name'] == group_name:
                    group['sshConfig'] = {
                        'username': data.get('username', ''),
                        'password': data.get('password', ''),
                        'port': data.get('port', 22),
                        'timeout': data.get('timeout', 5),
                        'keyAuth': data.get('keyAuth', False),
                        'keyPath': data.get('keyPath', ''),
                        'keyPassphrase': data.get('keyPassphrase', '')
                    }
                    updated = True
                    break
                    
            if updated:
                db_manager.update_config(config)
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Group not found'}), 404
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

# 启动监控服务
monitor.start()

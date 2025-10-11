
<!-- network_device_monitor/frontend/monitor.js -->
document.addEventListener('DOMContentLoaded', function() {
    // API基础URL - 修改为192.168.1.79:5005
    const API_BASE_URL = 'http://192.168.1.79:5005/api';
    
    // 设备数据存储
    let devices = [];
    let config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
    let autoRefreshInterval = null;
    
    // 格式化版本信息，保留换行
    function formatVersionInfo(version) {
        if (!version) return '-';
        // 替换常见的换行符为HTML换行标签
        return version.replace(/\r\n|\n|\r/g, '<br>');
    }
    
    // 获取分组SSH配置
    function getGroupSSHConfig(groupName) {
        if (!config.deviceGroups) {
            console.error('未找到设备分组配置');
            return {
                username: 'leapfive',
                password: 'leapfive',
                port: 22,
                timeout: 5,
                keyAuth: false
            };
        }
        
        const group = config.deviceGroups.find(g => g.name === groupName);
        if (!group || !group.sshConfig) {
            console.warn(`未找到分组 ${groupName} 的SSH配置，使用默认配置`);
            return {
                username: 'leapfive',
                password: 'leapfive',
                port: 22,
                timeout: 5,
                keyAuth: false
            };
        }
        
        return group.sshConfig;
    }
    
    // 按分组和状态排序设备
    function sortDevicesByGroupAndStatus(devices) {
        return devices.sort((a, b) => {
            // 先按分组排序
            const groupCompare = (a.group_name || 'NB2').localeCompare(b.group_name || 'NB2');
            if (groupCompare !== 0) return groupCompare;
            
            // 同分组内按状态排序（在线在前）
            if (a.status === 'online' && b.status !== 'online') return -1;
            if (a.status !== 'online' && b.status === 'online') return 1;
            
            return 0;
        });
    }
    
    // 渲染设备表格
    function renderDeviceTable() {
        const tbody = document.getElementById('device-table-body');
        tbody.innerHTML = '';
        
        if (devices.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center py-8 text-gray-400">
                        <i class="fas fa-server fa-2x mb-2"></i>
                        <p>暂无设备数据</p>
                    </td>
                </tr>
            `;
            return;
        }
        
        // 按分组和状态排序设备
        const sortedDevices = sortDevicesByGroupAndStatus(devices);
        
        let currentGroup = null;
        sortedDevices.forEach(device => {
            const deviceGroup = device.group_name || 'NB2';
            
            // 如果是新分组，添加分组标题行
            if (deviceGroup !== currentGroup) {
                currentGroup = deviceGroup;
                
                const groupHeader = document.createElement('tr');
                groupHeader.className = `group-header group-${deviceGroup.replace(/\s+/g, '-')}`;
                groupHeader.innerHTML = `
                    <td colspan="9" class="px-6 py-3 font-semibold text-gray-200">
                        <i class="fas fa-folder-open mr-2"></i>${deviceGroup}
                    </td>
                `;
                tbody.appendChild(groupHeader);
            }
            
            const tr = document.createElement('tr');
            tr.className = `status-${device.status} hover:bg-gray-750 transition-all duration-200 group-${deviceGroup.replace(/\s+/g, '-')}`;
            
            // 确保diskUsage和cpuUsage是数字类型
            const diskUsage = parseFloat(device.disk_usage) || 0;
            const cpuUsage = parseFloat(device.cpu_usage) || 0;
            
            tr.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap">${device.ip}</td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${device.status === 'online' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                        ${device.status === 'online' ? '在线' : '离线'}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-pre-wrap">${formatVersionInfo(device.version)}</td>
                <td class="px-6 py-4 whitespace-nowrap">${device.uptime || '-'}</td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <div class="w-full bg-gray-700 rounded-full h-2.5">
                        <div class="bg-blue-500 h-2.5 rounded-full" style="width: ${diskUsage}%"></div>
                    </div>
                    <span class="text-xs text-gray-400">${device.status === 'online' ? diskUsage + '%' : '-'}</span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <div class="w-full bg-gray-700 rounded-full h-2.5">
                        <div class="bg-purple-500 h-2.5 rounded-full" style="width: ${cpuUsage}%"></div>
                    </div>
                    <span class="text-xs text-gray-400">${device.status === 'online' ? cpuUsage + '%' : '-'}</span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <input type="text" value="${device.user || '未分配'}" class="user-input bg-gray-700 border-0 rounded px-2 py-1 text-white w-24 focus:ring-2 focus:ring-blue-500" data-ip="${device.ip}">
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <select class="bg-gray-700 border-0 rounded px-2 py-1 text-white focus:ring-2 focus:ring-blue-500" data-ip="${device.ip}">
                        ${getGroupOptions(deviceGroup)}
                    </select>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button class="text-red-400 hover:text-red-600 delete-device-btn" data-ip="${device.ip}"><i class="fas fa-trash-alt"></i></button>
                </td>
            `;
            
            tbody.appendChild(tr);
        });
        
        // 绑定用户输入事件
        document.querySelectorAll('tbody input[type="text"]').forEach(input => {
            input.addEventListener('change', function() {
                const ip = this.dataset.ip;
                const user = this.value;
                updateDeviceUser(ip, user);
            });
        });
        
        // 绑定分组选择事件
        document.querySelectorAll('tbody select').forEach(select => {
            select.addEventListener('change', function() {
                const ip = this.dataset.ip;
                const group = this.value;
                updateDeviceGroup(ip, group);
            });
        });
        
        // 绑定删除按钮事件
        document.querySelectorAll('.delete-device-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const ip = this.dataset.ip;
                deleteDevice(ip);
            });
        });
    }
    
    // 获取分组选项
    function getGroupOptions(selectedGroup) {
        console.log('加载分组选项...');
        const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
        const groups = config.deviceGroups || [
            { name: 'NB2', devices: [], sshConfig: {
                username: 'leapfive',
                password: 'leapfive',
                port: 22,
                timeout: 5,
                keyAuth: false
            }},
            { name: '服务器', devices: [], sshConfig: {} },
            { name: '网络设备', devices: [], sshConfig: {} },
            { name: '存储设备', devices: [], sshConfig: {} }
        ];
        
        console.log('当前分组数据:', groups);
        return groups.map(group => 
            `<option value="${group.name}" ${group.name === selectedGroup ? 'selected' : ''}>${group.name}</option>`
        ).join('');
    }
    
    // 更新设备用户
    async function updateDeviceUser(ip, user) {
        try {
            console.log(`更新设备 ${ip} 的用户为: ${user}`);
            const response = await fetch(`${API_BASE_URL}/devices/${ip}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ user })
            });
            
            if (response.ok) {
                const device = devices.find(d => d.ip === ip);
                if (device) {
                    device.user = user;
                }
            } else {
                console.error('更新设备用户失败:', response.statusText);
            }
        } catch (error) {
            console.error('更新设备用户时出错:', error);
        }
    }
    
    // 更新设备分组
    async function updateDeviceGroup(ip, group) {
        try {
            console.log(`更新设备 ${ip} 的分组为: ${group}`);
            const response = await fetch(`${API_BASE_URL}/devices/${ip}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ group })
            });
            
            if (response.ok) {
                const device = devices.find(d => d.ip === ip);
                if (device) {
                    device.group_name = group;
                }
                
                // 立即检查新设备状态
                console.log(`立即检查设备 ${ip} 状态...`);
                checkDeviceStatus({ip, group_name: group});
            } else {
                console.error('更新设备分组失败:', response.statusText);
            }
        } catch (error) {
            console.error('更新设备分组时出错:', error);
        }
    }
    
    // 删除设备
    async function deleteDevice(ip) {
        if (confirm(`确定要删除设备 ${ip} 吗？`)) {
            try {
                console.log(`删除设备 ${ip}...`);
                const response = await fetch(`${API_BASE_URL}/devices/${ip}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    devices = devices.filter(d => d.ip !== ip);
                    renderDeviceTable();
                    setupAutoRefresh();
                } else {
                    console.error('删除设备失败:', response.statusText);
                }
            } catch (error) {
                console.error('删除设备时出错:', error);
            }
        }
    }
    
    // 添加新设备
    async function addDevice(ip, group) {
        if (!ip) {
            console.error('设备IP不能为空');
            return;
        }
        
        // 检查是否已存在
        if (devices.some(d => d.ip === ip)) {
            console.error('该设备IP已存在');
            return;
        }
        
        // 显示加载状态
        const tbody = document.getElementById('device-table-body');
        const loadingRow = document.createElement('tr');
        loadingRow.innerHTML = `
            <td colspan="9" class="text-center py-4">
                <div class="inline-flex items-center">
                    <i class="fas fa-circle-notch fa-spin mr-2"></i>
                    正在添加设备 ${ip}...
                </div>
            </td>
        `;
        tbody.appendChild(loadingRow);
        
        const newDevice = {
            ip,
            status: 'offline',
            version: '-',
            uptime: '-',
            disk_usage: 0,
            cpu_usage: 0,
            user: '未分配',
            group_name: group || 'NB2'
        };
        
        try {
            console.log('添加新设备:', newDevice);
            const response = await fetch(`${API_BASE_URL}/devices`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(newDevice)
            });
            
            if (response.ok) {
                const savedDevice = await response.json();
                devices.push(savedDevice);
                console.log('设备添加成功:', savedDevice);
                renderDeviceTable();
                setupAutoRefresh();
                
                // 立即检查新设备状态
                console.log('立即检查新设备状态...');
                checkDeviceStatus(savedDevice);
            } else {
                console.error('添加设备失败:', response.statusText);
                renderDeviceTable();
            }
        } catch (error) {
            console.error('添加设备时出错:', error);
            renderDeviceTable();
        }
    }
    
    // 检查设备状态
    async function checkDeviceStatus(device) {
        try {
            console.log(`检查设备 ${device.ip} 状态...`);
            const response = await fetch(`${API_BASE_URL}/devices/${device.ip}/check`, {
                method: 'POST'
            });
            
            if (response.ok) {
                const updatedDevice = await response.json();
                console.log(`设备 ${device.ip} 状态更新:`, updatedDevice);
                
                // 更新本地设备列表
                const index = devices.findIndex(d => d.ip === device.ip);
                if (index !== -1) {
                    devices[index] = updatedDevice;
                    renderDeviceTable();
                }
            } else {
                console.error('检查设备状态失败:', response.statusText);
            }
        } catch (error) {
            console.error(`检查设备 ${device.ip} 状态时出错:`, error);
        }
    }
    
    // 检查所有设备状态
    async function checkAllDevicesStatus() {
        try {
            console.log('刷新所有设备状态...');
            const response = await fetch(`${API_BASE_URL}/devices/check-all`, {
                method: 'POST'
            });
            
            if (response.ok) {
                devices = await response.json();
                console.log('所有设备状态更新:', devices);
                renderDeviceTable();
                document.getElementById('last-update').textContent = new Date().toLocaleString();
            } else {
                console.error('刷新所有设备状态失败:', response.statusText);
            }
        } catch (error) {
            console.error('刷新所有设备状态时出错:', error);
        }
    }
    
    // 设置自动刷新
    function setupAutoRefresh() {
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
        }
        
        // 没有设备时不启动定时任务
        if (devices.length === 0) {
            document.getElementById('refresh-status').textContent = '关闭';
            return;
        }
        
        const refreshEnabled = config.autoRefreshEnabled !== false;
        const refreshInterval = (config.refreshInterval || 5) * 60 * 1000;
        
        document.getElementById('refresh-status').textContent = refreshEnabled ? '开启' : '关闭';
        
        if (refreshEnabled) {
            console.log(`设置自动刷新间隔: ${refreshInterval/1000}秒`);
            autoRefreshInterval = setInterval(() => {
                checkAllDevicesStatus();
            }, refreshInterval);
        }
    }
    
    // 加载配置
    async function loadConfig() {
        try {
            console.log('加载配置...');
            const response = await fetch(`${API_BASE_URL}/config`);
            if (response.ok) {
                config = await response.json();
                localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
                console.log('配置加载成功:', config);
                
                // 初始化添加设备模态框的分组下拉框
                const groupSelect = document.getElementById('device-group');
                if (groupSelect) {
                    const groups = config.deviceGroups || [
                        { name: 'NB2', devices: [], sshConfig: {
                            username: 'leapfive',
                            password: 'leapfive',
                            port: 22,
                            timeout: 5,
                            keyAuth: false
                        }},
                        { name: '服务器', devices: [], sshConfig: {} },
                        { name: '网络设备', devices: [], sshConfig: {} },
                        { name: '存储设备', devices: [], sshConfig: {} }
                    ];
                    
                    groupSelect.innerHTML = groups.map(group => 
                        `<option value="${group.name}">${group.name}</option>`
                    ).join('');
                }
            }
        } catch (error) {
            console.error('加载配置时出错:', error);
        }
    }
    
    // 初始化设备列表
    async function initDeviceList() {
        try {
            console.log('初始化设备列表...');
            const response = await fetch(`${API_BASE_URL}/devices`);
            if (response.ok) {
                devices = await response.json();
                console.log('设备列表加载成功:', devices);
                renderDeviceTable();
                setupAutoRefresh();
            } else {
                console.error('加载设备列表失败:', response.statusText);
            }
        } catch (error) {
            console.error('加载设备列表时出错:', error);
        }
    }
    
    // 初始化
    initDeviceList();
    loadConfig();
    
    // 绑定刷新按钮
    document.getElementById('refresh-btn').addEventListener('click', checkAllDevicesStatus);
    
    // 绑定添加设备按钮
    document.getElementById('add-device-btn').addEventListener('click', function() {
        document.getElementById('add-device-modal').classList.remove('hidden');
        document.getElementById('device-ip').value = '';
        document.getElementById('device-group').value = 'NB2';
    });
    
    // 绑定取消添加设备按钮
    document.getElementById('cancel-add-device').addEventListener('click', function() {
        document.getElementById('add-device-modal').classList.add('hidden');
    });
    
    // 绑定确认添加设备按钮
    document.getElementById('confirm-add-device').addEventListener('click', function() {
        const ip = document.getElementById('device-ip').value.trim();
        const group = document.getElementById('device-group').value;
        
        if (ip) {
            document.getElementById('confirm-text').classList.add('hidden');
            document.getElementById('loading-spinner').classList.remove('hidden');
            
            addDevice(ip, group).finally(() => {
                document.getElementById('confirm-text').classList.remove('hidden');
                document.getElementById('loading-spinner').classList.add('hidden');
                document.getElementById('add-device-modal').classList.add('hidden');
            });
        }
    });
});

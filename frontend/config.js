
// network_device_monitor/frontend/config.js
document.addEventListener('DOMContentLoaded', function() {
    // API基础URL - 修改为192.168.1.79:5005
    const API_BASE_URL = 'http://192.168.1.79:5005/api';
    
    // 当前选中的分组
    let currentGroup = '';
    
    // 加载保存的配置
    async function loadConfig() {
        try {
            const response = await fetch(`${API_BASE_URL}/config`);
            if (response.ok) {
                const config = await response.json();
                localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
                
                // 更新UI配置
                updateUIConfig(config);
                
                // 加载分组
                const groups = config.deviceGroups || getDefaultGroups();
                renderGroups(groups);
                loadGroupOptions(groups);
                
                // 默认选中NB2分组
                if (groups.length > 0) {
                    currentGroup = 'NB2';
                    loadGroupSSHConfig(currentGroup, groups);
                }
            }
        } catch (error) {
            console.error('加载配置时出错:', error);
            showToast('加载配置失败', 'error');
        }
    }

    function getDefaultGroups() {
        return [
            { 
                name: 'NB2', 
                devices: [], 
                sshConfig: {
                    username: 'leapfive',
                    password: 'leapfive',
                    port: 22,
                    timeout: 5,
                    keyAuth: false,
                    keyPath: '',
                    keyPassphrase: ''
                }
            },
            { name: '服务器', devices: [], sshConfig: {} },
            { name: '网络设备', devices: [], sshConfig: {} },
            { name: '存储设备', devices: [], sshConfig: {} }
        ];
    }

    function updateUIConfig(config) {
        // 监控命令
        document.getElementById('cmd-version').value = config.cmdVersion || 'sed -n \'/^PRETTY_NAME=/{s/^PRETTY_NAME=\\"\\\\([^\\"]*\\\\).*/\\\\1/p;q}\' /etc/os-release';
        document.getElementById('cmd-uptime').value = config.cmdUptime || 'uptime | perl -pe \'s/.*up\\s+(?:(\\d+)\\s+days?,\\s+)?(\\d+):.*/($1?$1:0)."天$2小时"/e\'';
        document.getElementById('cmd-disk').value = config.cmdDisk || 'df -h / | awk \'NR==2{print $5}\'';
        document.getElementById('cmd-cpu').value = config.cmdCpu || 'top -bn1 | grep \'Cpu(s)\' | sed \'s/.*, *\\\\([0-9.]*\\\\)%* id.*/\\\\1/\' | awk \'{print 100 - $1}\'';
        
        // 自动刷新配置
        document.getElementById('auto-refresh-toggle').checked = config.autoRefreshEnabled !== false;
        document.getElementById('refresh-interval').value = config.refreshInterval || 5;
    }
    
    // 渲染分组表格
    function renderGroups(groups) {
        const tbody = document.getElementById('group-table-body');
        tbody.innerHTML = '';
        
        groups.forEach(group => {
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-750 transition-all duration-200';
            
            tr.innerHTML = `
                <td class="px-4 py-3 whitespace-nowrap">${group.name}</td>
                <td class="px-4 py-3 whitespace-nowrap">${group.devices ? group.devices.length : 0}</td>
                <td class="px-4 py-3 whitespace-nowrap text-right">
                    <button class="text-blue-400 hover:text-blue-600 mr-2 edit-group-btn" data-group="${group.name}">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="text-red-400 hover:text-red-600 delete-group-btn" data-group="${group.name}">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </td>
            `;
            
            tbody.appendChild(tr);
        });
    }
    
    // 加载分组选项
    function loadGroupOptions(groups) {
        const select = document.getElementById('ssh-group-select');
        select.innerHTML = '';
        
        groups.forEach(group => {
            const option = document.createElement('option');
            option.value = group.name;
            option.textContent = group.name;
            select.appendChild(option);
        });
    }
    
    // 加载分组SSH配置
    function loadGroupSSHConfig(groupName, groups) {
        const group = groups.find(g => g.name === groupName);
        if (group && group.sshConfig) {
            const sshConfig = group.sshConfig;
            document.getElementById('ssh-username').value = sshConfig.username || 'leapfive';
            document.getElementById('ssh-password').value = sshConfig.password || 'leapfive';
            document.getElementById('ssh-port').value = sshConfig.port || '22';
            document.getElementById('ssh-timeout').value = sshConfig.timeout || '5';
            document.getElementById('ssh-key-auth').checked = sshConfig.keyAuth || false;
            document.getElementById('ssh-key-path').value = sshConfig.keyPath || '';
            document.getElementById('ssh-key-passphrase').value = sshConfig.keyPassphrase || '';
            
            // 更新密钥认证字段显示
            const keyFields = document.getElementById('ssh-key-fields');
            if (sshConfig.keyAuth) {
                keyFields.classList.remove('hidden');
            } else {
                keyFields.classList.add('hidden');
            }
        }
    }
    
    // 保存分组SSH配置
    function saveGroupSSHConfig(groupName) {
        const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
        const groups = config.deviceGroups || getDefaultGroups();
        
        const groupIndex = groups.findIndex(g => g.name === groupName);
        if (groupIndex !== -1) {
            groups[groupIndex].sshConfig = {
                username: document.getElementById('ssh-username').value,
                password: document.getElementById('ssh-password').value,
                port: document.getElementById('ssh-port').value,
                timeout: document.getElementById('ssh-timeout').value,
                keyAuth: document.getElementById('ssh-key-auth').checked,
                keyPath: document.getElementById('ssh-key-path').value,
                keyPassphrase: document.getElementById('ssh-key-passphrase').value
            };
            
            config.deviceGroups = groups;
            localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
        }
    }

    // 保存配置到后端
    async function saveConfigToBackend() {
        try {
            const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
            
            // 更新自动刷新配置
            config.autoRefreshEnabled = document.getElementById('auto-refresh-toggle').checked;
            config.refreshInterval = parseInt(document.getElementById('refresh-interval').value) || 5;
            
            // 更新监控命令配置
            config.cmdVersion = document.getElementById('cmd-version').value;
            config.cmdUptime = document.getElementById('cmd-uptime').value;
            config.cmdDisk = document.getElementById('cmd-disk').value;
            config.cmdCpu = document.getElementById('cmd-cpu').value;
            
            const response = await fetch(`${API_BASE_URL}/config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
            
            if (response.ok) {
                return true;
            } else {
                const errorData = await response.json();
                console.error('保存配置失败:', errorData.error || response.statusText);
                return false;
            }
        } catch (error) {
            console.error('保存配置时出错:', error);
            return false;
        }
    }

    // 保存配置按钮事件
    document.getElementById('save-config-btn').addEventListener('click', async function() {
        // 先保存当前分组的SSH配置
        if (currentGroup) {
            saveGroupSSHConfig(currentGroup);
        }
        
        // 保存到后端
        const success = await saveConfigToBackend();
        
        // 显示保存状态
        const btn = this;
        const originalText = btn.innerHTML;
        
        if (success) {
            btn.innerHTML = '<i class="fas fa-check mr-2"></i>保存成功';
            btn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
            btn.classList.add('bg-green-600', 'hover:bg-green-700');
            
            // 立即刷新配置
            await loadConfig();
        } else {
            btn.innerHTML = '<i class="fas fa-times mr-2"></i>保存失败';
            btn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
            btn.classList.add('bg-red-600', 'hover:bg-red-700');
        }
        
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.classList.remove(success ? 'bg-green-600' : 'bg-red-600');
            btn.classList.remove(success ? 'hover:bg-green-700' : 'hover:bg-red-700');
            btn.classList.add('bg-blue-600', 'hover:bg-blue-700');
        }, 2000);
    });

    // 恢复默认配置
    document.getElementById('reset-config-btn').addEventListener('click', function() {
        if(confirm('确定要恢复默认配置吗？所有自定义设置将被重置。')) {
            localStorage.removeItem('networkMonitorConfig');
            loadConfig();
            
            // 显示重置成功的提示
            const btn = this;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check mr-2"></i>已重置';
            btn.classList.remove('bg-gray-600', 'hover:bg-gray-700');
            btn.classList.add('bg-green-600', 'hover:bg-green-700');
            
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.classList.remove('bg-green-600', 'hover:bg-green-700');
                btn.classList.add('bg-gray-600', 'hover:bg-gray-700');
            }, 2000);
        }
    });

    // 添加新分组
    document.getElementById('add-group-btn').addEventListener('click', async function() {
        const groupName = document.getElementById('new-group-name').value.trim();
        if(!groupName) {
            showToast('请输入分组名称', 'error');
            return;
        }
        
        const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
        const groups = config.deviceGroups || getDefaultGroups();
        
        // 检查是否已存在同名分组
        if(groups.some(g => g.name === groupName)) {
            showToast('该分组名称已存在', 'error');
            return;
        }
        
        groups.push({ 
            name: groupName, 
            devices: [], 
            sshConfig: {
                username: 'leapfive',
                password: 'leapfive',
                port: 22,
                timeout: 5,
                keyAuth: false,
                keyPath: '',
                keyPassphrase: ''
            }
        });
        
        config.deviceGroups = groups;
        localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
        
        // 保存到后端
        const success = await saveConfigToBackend();
        
        if (success) {
            document.getElementById('new-group-name').value = '';
            renderGroups(groups);
            loadGroupOptions(groups);
            showToast('分组添加成功', 'success');
        } else {
            showToast('分组添加失败', 'error');
        }
    });

    // 分组选择变化事件
    document.getElementById('ssh-group-select').addEventListener('change', function() {
        const groupName = this.value;
        if (groupName) {
            // 保存当前分组的SSH配置
            if (currentGroup) {
                saveGroupSSHConfig(currentGroup);
            }
            
            // 加载新分组的SSH配置
            const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
            const groups = config.deviceGroups || getDefaultGroups();
            loadGroupSSHConfig(groupName, groups);
            
            currentGroup = groupName;
        }
    });

    // 委托事件处理分组操作
    document.getElementById('group-table-body').addEventListener('click', async function(e) {
        const config = JSON.parse(localStorage.getItem('networkMonitorConfig')) || {};
        let groups = config.deviceGroups || getDefaultGroups();
        
        // 删除分组
        if(e.target.closest('.delete-group-btn')) {
            const groupName = e.target.closest('.delete-group-btn').dataset.group;
            if(confirm(`确定要删除分组 "${groupName}" 吗？`)) {
                groups = groups.filter(g => g.name !== groupName);
                config.deviceGroups = groups;
                localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
                
                // 保存到后端
                const success = await saveConfigToBackend();
                
                if (success) {
                    renderGroups(groups);
                    loadGroupOptions(groups);
                    
                    // 如果删除的是当前选中的分组，重置当前分组
                    if (currentGroup === groupName) {
                        currentGroup = '';
                        if (groups.length > 0) {
                            document.getElementById('ssh-group-select').value = groups[0].name;
                            loadGroupSSHConfig(groups[0].name, groups);
                            currentGroup = groups[0].name;
                        }
                    }
                    showToast('分组删除成功', 'success');
                } else {
                    showToast('分组删除失败', 'error');
                }
            }
        }
        
        // 编辑分组
        if(e.target.closest('.edit-group-btn')) {
            const groupName = e.target.closest('.edit-group-btn').dataset.group;
            const newName = prompt('请输入新的分组名称', groupName);
            
            if(newName && newName !== groupName) {
                const group = groups.find(g => g.name === groupName);
                if(group) {
                    group.name = newName;
                    config.deviceGroups = groups;
                    localStorage.setItem('networkMonitorConfig', JSON.stringify(config));
                    
                    // 保存到后端
                    const success = await saveConfigToBackend();
                    
                    if (success) {
                        renderGroups(groups);
                        loadGroupOptions(groups);
                        
                        // 如果编辑的是当前选中的分组，更新当前分组
                        if (currentGroup === groupName) {
                            currentGroup = newName;
                            document.getElementById('ssh-group-select').value = newName;
                        }
                        showToast('分组修改成功', 'success');
                    } else {
                        showToast('分组修改失败', 'error');
                    }
                }
            }
        }
    });

    // SSH密钥认证切换
    document.getElementById('ssh-key-auth').addEventListener('change', function() {
        const keyFields = document.getElementById('ssh-key-fields');
        if(this.checked) {
            keyFields.classList.remove('hidden');
        } else {
            keyFields.classList.add('hidden');
        }
    });

    // 显示Toast通知
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg text-white ${
            type === 'success' ? 'bg-green-500' : 
            type === 'error' ? 'bg-red-500' : 
            'bg-blue-500'
        }`;
        toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas ${
                    type === 'success' ? 'fa-check-circle' : 
                    type === 'error' ? 'fa-exclamation-circle' : 
                    'fa-info-circle'
                } mr-2"></i>
                ${message}
            </div>
        `;
        
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('opacity-0', 'transition-opacity', 'duration-300');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // 初始化加载配置
    loadConfig();
});

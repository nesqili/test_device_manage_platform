

# 启动 
    登录到192.168.34.60服务器，账号密码 ：qli/1q2w3e
$ cd /home/qli/Data/leapfive/tools/test_device_manage_platform
$ python3 ./frontend/backend/app.py  

# 访问
http://localhost:5005

## 端口配置 
```
在monitor.js和config.js中修改
    const API_BASE_URL = 'http://192.168.34.60:5005/api';
frontend/backend/app.py :  
if __name__ == '__main__':
    app.run(debug=True, host='192.168.34.60', port=5005)  
```
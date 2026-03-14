## Twitter账号抓取逻辑

### 生成db文件
```
import asyncio
from twscrape import API

async def main():
    api = API('.twscrape_accounts.db')
    
    # 先删掉旧账号
    await api.pool.delete_accounts('colorsnil')
    
    # 重新添加
    await api.pool.add_account(
        username='colorsnil',
        password='你的Twitter密码',
        email='szqsunny@163.com',
        email_password='',
        cookies='auth_token=44b690d38b7de543a39406d759760ddf3df38230; ct0=2d61d2607ecaff34c77e63768d4b3af8a7973e1c36e723c5c735de13fb149d1ec71eb8ef6fd61bc527b48d4d3052089eba31067fb63c5eb9990d85445ce6b39d4b9dbacaaf9337e36032d2dc0aba15c4'
    )
    
    stats = await api.pool.stats()
    print('账号状态:', stats)

asyncio.run(main())
```

### 获取db编码内容
```
# 确认文件存在
ls -la .twscrape_accounts.db

# 转成 base64 复制到剪贴板
base64 -i .twscrape_accounts.db | pbcopy

echo "已复制到剪贴板"
```

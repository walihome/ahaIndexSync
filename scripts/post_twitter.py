"""
管线跑完后自动发 Twitter
在 pipeline deploy job 之后运行
"""
import os
import json
import tweepy

def main():
    # 1. 从 OSS 或本地读取当天数据
    # (在 export_oss.py 之后运行，可以直接读 latest.json)
    import urllib.request
    resp = urllib.request.urlopen('https://www.amazingindex.com/api/latest.json')
    data = json.loads(resp.read())
    
    date = data['snapshot_date']
    items = data.get('items', [])
    if not items:
        print("No items, skip posting")
        return

    # 2. 组装推文
    top3 = items[:3]
    lines = [f"📰 AmazingIndex {date} AI 日报\n"]
    for i, item in enumerate(top3, 1):
        title = item.get('processed_title', '')
        lines.append(f"{i}. {title}")
    
    lines.append(f"\n🔗 https://www.amazingindex.com/daily/{date}")
    lines.append("#AI #AmazingIndex")
    
    tweet = '\n'.join(lines)
    
    # 3. 发推
    client = tweepy.Client(
        consumer_key=os.environ['TWITTER_API_KEY'],
        consumer_secret=os.environ['TWITTER_API_SECRET'],
        access_token=os.environ['TWITTER_ACCESS_TOKEN'],
        access_token_secret=os.environ['TWITTER_ACCESS_TOKEN_SECRET'],
    )
    
    response = client.create_tweet(text=tweet)
    print(f"✅ Tweet posted: {response.data['id']}")

if __name__ == '__main__':
    main()
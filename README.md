# WaterHole
這是自己用的小工具，所以不會有太多說明 XD<br>
大多 VIBE CODING<br>

## 安裝和執行
```sh
git clone waterhole
cd waterhole
python3 -m venv waterhole
source waterhole/bin/activate
python3 -m pip install requests dirsearch setuptools
curl ipinfo.io
python3 waterhole.py
```

## 輸入檔案範本
### path.csv
> 你想找的檔案路徑，比 dirsearch 還要前面，比較不會觸發 WAF 牆，搶水洞用
```
/img1.png
/img2.png
```

### scope.csv
> 目標網站
```
neko70.net
mygo.tw
```

## 輸出檔案範本
### result1.csv
```
http_response,website
404,https://neko70.net/img1.png
404,https://mygo.tw/img1.png
404,https://neko70.net/img2.png
404,https://mygo.tw/img2.png
```

### error.csv
```
error_type,website
CONNECTION_ERROR,https://neko70.net/img1.png
TIMEOUT,https://mygo.tw/img1.png
```

## 其他指令備註
### 開環境
```sh
python3 -m venv waterhole
source waterhole/bin/activate
```

### dirsearch
```sh
dirsearch -u <URL> --max-rate=50 --format=csv -o <scope_url>.csv
```

### sqlmap
```sh
sqlmap -u <URL>
```
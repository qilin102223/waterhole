import requests
import csv
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import time
from queue import Queue
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WebCrawler:
    def __init__(self, max_workers=10, timeout=10, retry_count=3):
        """
        初始化爬蟲
        :param max_workers: 最大線程數
        :param timeout: 請求超時時間
        :param retry_count: 重試次數
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.results = []
        self.lock = threading.Lock()
    
    def read_csv_file(self, filename):
        """讀取 CSV 文件並返回第一列的數據"""
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                return [row[0].strip() for row in reader if row]
        except FileNotFoundError:
            logger.error(f"文件 {filename} 不存在")
            return []
        except Exception as e:
            logger.error(f"讀取文件 {filename} 時發生錯誤: {e}")
            return []
    
    def generate_urls(self, paths, scopes):
        """生成要檢測的 URL 列表，按照指定順序"""
        urls = []
        for path in paths:
            for scope in scopes:
                # 確保 scope 有協議前綴
                if not scope.startswith(('http://', 'https://')):
                    scope = 'https://' + scope
                
                # 組合 URL
                full_url = urljoin(scope, path)
                urls.append(full_url)
        
        return urls
    
    def check_url(self, url):
        """檢查單個 URL 的狀態"""
        for attempt in range(self.retry_count):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                logger.info(f"檢測 {url} - 狀態碼: {response.status_code}")
                return response.status_code, url
            except requests.exceptions.Timeout:
                logger.warning(f"請求 {url} 超時 (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'TIMEOUT', url
            except requests.exceptions.ConnectionError:
                logger.warning(f"連接 {url} 失敗 (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'CONNECTION_ERROR', url
            except requests.exceptions.RequestException as e:
                logger.warning(f"請求 {url} 時發生錯誤: {e} (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'REQUEST_ERROR', url
            except Exception as e:
                logger.error(f"檢測 {url} 時發生未知錯誤: {e}")
                return 'UNKNOWN_ERROR', url
            
            # 重試前等待
            time.sleep(1)
    
    def save_result(self, status_code, url):
        """線程安全地保存結果"""
        with self.lock:
            self.results.append((status_code, url))
    
    def write_results_to_csv(self, filename='result.csv'):
        """將結果寫入 CSV 文件"""
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['http_response', 'website'])
                for status_code, url in self.results:
                    writer.writerow([status_code, url])
            logger.info(f"結果已保存到 {filename}")
        except Exception as e:
            logger.error(f"保存結果到 {filename} 時發生錯誤: {e}")
    
    def crawl(self, path_file='path.csv', scope_file='scope.csv', output_file='result.csv'):
        """主要爬蟲函數"""
        logger.info("開始爬蟲任務")
        
        # 讀取文件
        paths = self.read_csv_file(path_file)
        scopes = self.read_csv_file(scope_file)
        
        if not paths:
            logger.error("路徑文件為空或讀取失敗")
            return
        
        if not scopes:
            logger.error("域名文件為空或讀取失敗")
            return
        
        logger.info(f"讀取到 {len(paths)} 個路徑和 {len(scopes)} 個域名")
        
        # 生成 URL 列表
        urls = self.generate_urls(paths, scopes)
        logger.info(f"總共需要檢測 {len(urls)} 個 URL")
        
        # 使用線程池執行爬蟲任務
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任務
            future_to_url = {executor.submit(self.check_url, url): url for url in urls}
            
            # 處理完成的任務
            for future in as_completed(future_to_url):
                try:
                    status_code, url = future.result()
                    self.save_result(status_code, url)
                except Exception as e:
                    url = future_to_url[future]
                    logger.error(f"處理 {url} 時發生錯誤: {e}")
                    self.save_result('ERROR', url)
        
        # 保存結果
        self.write_results_to_csv(output_file)
        logger.info(f"爬蟲任務完成，共檢測了 {len(self.results)} 個 URL")
        
        # 統計結果
        self.print_statistics()
    
    def print_statistics(self):
        """打印統計信息"""
        if not self.results:
            return
        
        status_count = {}
        for status_code, _ in self.results:
            status_count[status_code] = status_count.get(status_code, 0) + 1
        
        logger.info("=== 統計結果 ===")
        for status, count in status_count.items():
            logger.info(f"{status}: {count} 個")

def main():
    """主函數"""
    # 創建爬蟲實例
    crawler = WebCrawler(
        max_workers=10,  # 可以根據需要調整線程數
        timeout=10,      # 請求超時時間
        retry_count=3    # 重試次數
    )
    
    # 開始爬蟲
    crawler.crawl(
        path_file='path.csv',
        scope_file='scope.csv',
        output_file='result.csv'
    )

if __name__ == "__main__":
    main()
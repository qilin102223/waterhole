import requests
import csv
import threading
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import time
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedWebCrawler:
    def __init__(self, max_workers=10, timeout=10, retry_count=3, dirsearch_max_rate=30, max_dirsearch_workers=30):
        """
        初始化爬蟲
        :param max_workers: 最大線程數
        :param timeout: 請求超時時間
        :param retry_count: 重試次數
        :param dirsearch_max_rate: dirsearch 的最大速率
        :param max_dirsearch_workers: 最大 dirsearch 並行數
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.retry_count = retry_count
        self.dirsearch_max_rate = dirsearch_max_rate
        self.max_dirsearch_workers = max_dirsearch_workers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.results = []
        self.error_results = []
        self.dirsearch_errors = []
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
        """檢查單個 URL 的狀態，確保單個失敗不影響其他"""
        for attempt in range(self.retry_count):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                logger.info(f"檢測 {url} - 狀態碼: {response.status_code}")
                return response.status_code, url, False  # False 表示沒有錯誤
            except requests.exceptions.Timeout:
                logger.warning(f"請求 {url} 超時 (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'TIMEOUT', url, True  # True 表示有錯誤
            except requests.exceptions.ConnectionError:
                logger.warning(f"連接 {url} 失敗 (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'CONNECTION_ERROR', url, True
            except requests.exceptions.RequestException as e:
                logger.warning(f"請求 {url} 時發生錯誤: {e} (嘗試 {attempt + 1}/{self.retry_count})")
                if attempt == self.retry_count - 1:
                    return 'REQUEST_ERROR', url, True
            except Exception as e:
                logger.error(f"檢測 {url} 時發生未知錯誤: {e}")
                return 'UNKNOWN_ERROR', url, True
            
            # 重試前等待
            time.sleep(1)
    
    def save_result(self, status_code, url, is_error=False):
        """線程安全地保存結果"""
        with self.lock:
            if is_error:
                self.error_results.append((status_code, url))
            else:
                self.results.append((status_code, url))
    
    def save_dirsearch_error(self, url, error_msg):
        """線程安全地保存 dirsearch 錯誤"""
        with self.lock:
            self.dirsearch_errors.append((url, error_msg))
    
    def write_results_to_csv(self, filename='result1.csv'):
        """將結果寫入 CSV 文件"""
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['http_response', 'website'])
                for status_code, url in self.results:
                    writer.writerow([status_code, url])
            logger.info(f"成功結果已保存到 {filename}")
        except Exception as e:
            logger.error(f"保存結果到 {filename} 時發生錯誤: {e}")
    
    def write_errors_to_csv(self, filename='error.csv'):
        """將錯誤結果寫入 CSV 文件"""
        if not self.error_results:
            logger.info("沒有錯誤結果需要保存")
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['error_type', 'website'])
                for error_type, url in self.error_results:
                    writer.writerow([error_type, url])
            logger.info(f"錯誤結果已保存到 {filename}")
        except Exception as e:
            logger.error(f"保存錯誤結果到 {filename} 時發生錯誤: {e}")
    
    def write_dirsearch_errors_to_csv(self, filename='dirsearch_error.csv'):
        """將 dirsearch 錯誤結果寫入 CSV 文件"""
        if not self.dirsearch_errors:
            logger.info("沒有 dirsearch 錯誤需要保存")
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['website', 'error_message'])
                for url, error_msg in self.dirsearch_errors:
                    writer.writerow([url, error_msg])
            logger.info(f"Dirsearch 錯誤已保存到 {filename}")
        except Exception as e:
            logger.error(f"保存 dirsearch 錯誤到 {filename} 時發生錯誤: {e}")
    
    def run_dirsearch(self, url):
        """運行 dirsearch 對單個 URL 進行目錄掃描，確保單個失敗不影響其他"""
        try:
            # 解析 URL 獲取域名
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace(':', '_').replace('.', '_')
            
            # 創建輸出文件名
            output_filename = f"dirsearch_{domain}.csv"
            
            # 構建 dirsearch 命令
            cmd = [
                'dirsearch',
                '-u', url,
                '--max-rate', str(self.dirsearch_max_rate),
                '--format', 'csv',
                '-o', output_filename
            ]
            
            logger.info(f"開始對 {url} 運行 dirsearch")
            
            # 執行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30分鐘超時
            )
            
            if result.returncode == 0:
                logger.info(f"Dirsearch 完成: {url} -> {output_filename}")
                return True, url, output_filename, ""
            else:
                error_msg = result.stderr or result.stdout or "未知錯誤"
                logger.error(f"Dirsearch 失敗: {url} - {error_msg}")
                # 保存錯誤但不影響其他任務
                self.save_dirsearch_error(url, error_msg)
                return False, url, output_filename, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "執行超時(30分鐘)"
            logger.error(f"Dirsearch 超時: {url}")
            self.save_dirsearch_error(url, error_msg)
            return False, url, output_filename, error_msg
        except FileNotFoundError:
            error_msg = "dirsearch 命令未找到"
            logger.error("dirsearch 命令未找到，請確保已安裝 dirsearch")
            self.save_dirsearch_error(url, error_msg)
            return False, url, "", error_msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"運行 dirsearch 時發生錯誤: {url} - {e}")
            self.save_dirsearch_error(url, error_msg)
            return False, url, "", error_msg
    
    def crawl_urls(self, path_file='path.csv', scope_file='scope.csv', output_file='result1.csv'):
        """第一階段：爬取指定路徑"""
        logger.info("=== 開始第一階段：URL 狀態檢測 ===")
        
        # 讀取文件
        paths = self.read_csv_file(path_file)
        scopes = self.read_csv_file(scope_file)
        
        if not paths:
            logger.error("路徑文件為空或讀取失敗")
            return []
        
        if not scopes:
            logger.error("域名文件為空或讀取失敗")
            return []
        
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
                    status_code, url, is_error = future.result()
                    self.save_result(status_code, url, is_error)
                except Exception as e:
                    url = future_to_url[future]
                    logger.error(f"處理 {url} 時發生錯誤: {e}")
                    # 將異常也作為錯誤處理，但不影響其他任務
                    self.save_result('EXCEPTION', url, True)
        
        # 保存結果
        self.write_results_to_csv(output_file)
        self.write_errors_to_csv()
        
        logger.info(f"第一階段完成，成功檢測了 {len(self.results)} 個 URL，失敗 {len(self.error_results)} 個")
        
        # 統計結果
        self.print_statistics()
        
        return scopes
    
    def run_dirsearch_parallel(self, scopes):
        """第二階段：並行運行 dirsearch"""
        logger.info("=== 開始第二階段：Dirsearch 目錄掃描 ===")
        
        if not scopes:
            logger.warning("沒有域名需要進行 dirsearch 掃描")
            return
        
        # 為每個域名準備完整的 URL
        target_urls = []
        for scope in scopes:
            if not scope.startswith(('http://', 'https://')):
                scope = 'https://' + scope
            target_urls.append(scope)
        
        logger.info(f"將對 {len(target_urls)} 個域名運行 dirsearch (最大並行數: {self.max_dirsearch_workers})")
        
        # 使用線程池並行運行 dirsearch，限制最大並行數
        dirsearch_results = []
        with ThreadPoolExecutor(max_workers=min(len(target_urls), self.max_dirsearch_workers)) as executor:
            # 提交所有 dirsearch 任務
            future_to_url = {executor.submit(self.run_dirsearch, url): url for url in target_urls}
            
            # 處理完成的任務
            for future in as_completed(future_to_url):
                try:
                    success, url, output_file, error_msg = future.result()
                    dirsearch_results.append((success, url, output_file, error_msg))
                    
                    if success:
                        logger.info(f"✓ Dirsearch 成功: {url}")
                    else:
                        logger.error(f"✗ Dirsearch 失敗: {url} - {error_msg}")
                        
                except Exception as e:
                    url = future_to_url[future]
                    logger.error(f"Dirsearch 任務異常: {url} - {e}")
                    # 將異常也保存到錯誤記錄中，但不影響其他任務
                    self.save_dirsearch_error(url, f"任務異常: {str(e)}")
                    dirsearch_results.append((False, url, "", str(e)))
        
        # 保存 dirsearch 錯誤結果
        self.write_dirsearch_errors_to_csv()
        
        # 輸出 dirsearch 結果統計
        self.print_dirsearch_statistics(dirsearch_results)
    
    def print_statistics(self):
        """打印 URL 檢測統計信息"""
        total_urls = len(self.results) + len(self.error_results)
        if total_urls == 0:
            return
        
        status_count = {}
        for status_code, _ in self.results:
            status_count[status_code] = status_count.get(status_code, 0) + 1
        
        error_count = {}
        for error_type, _ in self.error_results:
            error_count[error_type] = error_count.get(error_type, 0) + 1
        
        logger.info("=== URL 檢測統計結果 ===")
        logger.info(f"總計: {total_urls} 個 URL")
        logger.info(f"成功: {len(self.results)} 個")
        logger.info(f"失敗: {len(self.error_results)} 個")
        
        if status_count:
            logger.info("--- 成功狀態統計 ---")
            for status, count in status_count.items():
                logger.info(f"{status}: {count} 個")
        
        if error_count:
            logger.info("--- 錯誤類型統計 ---")
            for error_type, count in error_count.items():
                logger.info(f"{error_type}: {count} 個")
    
    def print_dirsearch_statistics(self, dirsearch_results):
        """打印 dirsearch 統計信息"""
        successful = sum(1 for success, _, _, _ in dirsearch_results if success)
        failed = len(dirsearch_results) - successful
        
        logger.info("=== Dirsearch 統計結果 ===")
        logger.info(f"成功: {successful} 個")
        logger.info(f"失敗: {failed} 個")
        
        # 列出生成的文件
        logger.info("=== 生成的 Dirsearch 文件 ===")
        for success, url, output_file, _ in dirsearch_results:
            if success and output_file:
                if os.path.exists(output_file):
                    logger.info(f"✓ {output_file} ({url})")
                else:
                    logger.warning(f"⚠ {output_file} 文件未找到 ({url})")
    
    def run_full_scan(self, path_file='path.csv', scope_file='scope.csv', output_file='result1.csv'):
        """運行完整的掃描流程"""
        logger.info("開始完整掃描流程")
        
        try:
            # 第一階段：URL 狀態檢測
            scopes = self.crawl_urls(path_file, scope_file, output_file)
            
            # 第二階段：Dirsearch 掃描
            if scopes:
                self.run_dirsearch_parallel(scopes)
            
            logger.info("完整掃描流程結束")
            
        except KeyboardInterrupt:
            logger.info("用戶中斷了掃描過程")
        except Exception as e:
            logger.error(f"掃描過程中發生錯誤: {e}")

def main():
    """主函數"""
    print("=== 多線程爬蟲 + Dirsearch 集成工具 ===")
    print("此工具將執行以下步驟：")
    print("1. 讀取 path.csv 和 scope.csv")
    print("2. 檢測所有組合 URL 的狀態")
    print("3. 並行運行 dirsearch 對每個域名進行目錄掃描")
    print("=" * 50)
    
    # 檢查 dirsearch 是否可用
    try:
        subprocess.run(['dirsearch', '--help'], capture_output=True, timeout=5)
        logger.info("✓ Dirsearch 工具檢測成功")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.error("✗ Dirsearch 工具未找到或無法運行")
        logger.error("請確保已安裝 dirsearch: pip install dirsearch")
        return
    
    # 創建爬蟲實例
    crawler = AdvancedWebCrawler(
        max_workers=5,               # HTTP 請求最大線程數
        timeout=10,                  # 請求超時時間
        retry_count=1,               # 重試次數
        dirsearch_max_rate=30,       # dirsearch 最大速率
        max_dirsearch_workers=30     # dirsearch 最大並行數
    )
    
    # 開始完整掃描
    crawler.run_full_scan(
        path_file='path.csv',
        scope_file='scope.csv',
        output_file='result1.csv'
    )

if __name__ == "__main__":
    main()
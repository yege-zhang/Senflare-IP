"""
IP Test - Cloudflare优选IP采集器 v2.1.0
高效采集、检测和识别Cloudflare 优选IP的状态和详情信息

主要特性:
- 智能缓存系统，支持TTL机制
- 并发处理，大幅提升检测速度
- 网络优化，智能请求间隔
- 完善日志，所有操作都有Emoji记录
- 错误处理，特别优化403错误
- 自动限制缓存大小，防止文件过大
"""

# ===== 标准库导入 =====
import re
import os
import time
import socket
import json
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, Counter

# ===== 第三方库导入 =====
import requests
from urllib3.exceptions import InsecureRequestWarning

# ===== 配置和初始化 =====

# 禁用SSL证书警告
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('IPtest.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== 核心配置 =====
     # API接口配置
CONFIG = {
    "ip_sources": [
        'https://cf.hyli.xyz/', # 行雺
        'https://raw.githubusercontent.com/ymyuuu/IPDB/main/BestCF/bestcfv4.txt', # Ymyuuu
        'https://ipdb.api.030101.xyz/?type=bestcf&country=true', # Ymyuuu（备用）
        'https://api.uouin.com/cloudflare.html', # 麒麟
        'https://api.urlce.com/cloudflare.html', # 麒麟（备用）
        'https://addressesapi.090227.xyz/CloudFlareYes', # Hostmonit
        'https://cf.090227.xyz/CloudFlareYes', # Hostmonit（备用）
        # 'https://stock.hostmonit.com/CloudFlareYes', # Hostmonit
        'https://ipdb.api.030101.xyz/?type=bestproxy&country=true', # Mingyu
        'https://ip.haogege.xyz/', # 好哥哥
        'https://vps789.com/openApi/cfIpTop20', # VPS789-综合排名前20
        'https://vps789.com/openApi/cfIpApi', # VPS789-动态获取接口
        'https://hhhhh.eu.org/vps789.txt', # VPS789（备用）
        'https://www.wetest.vip/page/cloudflare/address_v4.html', # 微测网
        'https://www.wetest.vip/page/cloudflare/total_v4.html',   # 微测网 
        'https://cf.090227.xyz/cmcc', # CMLiussss-电信
        'https://cf.090227.xyz/ct', # CMLiussss-移动
    ],

    # 脚本参数配置
    "test_ports": [443],            # 测试核心端口 示例：[443, 2053, 2083, 2087, 2096, 8443, 2052, 2082, 2086, 2095, 8444] # 443系端口：HTTPS和Cloudflare专用端
    "timeout": 8,                   # IP采集超时时间
    "api_timeout": 5,               # API查询超时时间（减少到5秒）
    "query_interval": 0.1,          # API查询间隔（减少到0.1秒，大幅提升速度）
    
    # 新增并发处理配置
    "max_workers": 20,              # 最大并发线程数
    "batch_size": 10,               # 批量处理大小
    "cache_ttl_hours": 168,         # 缓存TTL（7天）- IP地区信息很少变化
}

# ===== 国家/地区映射表 =====
COUNTRY_MAPPING = {
    # 统一添加常见国家和地区
    # 北美
    'US': '美国', 'CA': '加拿大', 'MX': '墨西哥', 'CR': '哥斯达黎加', 'GT': '危地马拉', 'HN': '洪都拉斯',
    'NI': '尼加拉瓜', 'PA': '巴拿马', 'CU': '古巴', 'JM': '牙买加', 'TT': '特立尼达和多巴哥',
    'BZ': '伯利兹', 'SV': '萨尔瓦多', 'DO': '多米尼加', 'HT': '海地',
    # 南美
    'BR': '巴西', 'AR': '阿根廷', 'CL': '智利', 'CO': '哥伦比亚', 'PE': '秘鲁', 'VE': '委内瑞拉',
    'UY': '乌拉圭', 'PY': '巴拉圭', 'BO': '玻利维亚', 'EC': '厄瓜多尔', 'GY': '圭亚那',
    'SR': '苏里南', 'FK': '福克兰群岛',
    # 欧洲
    'UK': '英国', 'GB': '英国', 'FR': '法国', 'DE': '德国', 'IT': '意大利', 'ES': '西班牙', 'NL': '荷兰',
    'RU': '俄罗斯', 'SE': '瑞典', 'CH': '瑞士', 'BE': '比利时', 'AT': '奥地利', 'IS': '冰岛',
    'PL': '波兰', 'DK': '丹麦', 'NO': '挪威', 'FI': '芬兰', 'PT': '葡萄牙', 'IE': '爱尔兰',
    'UA': '乌克兰', 'CZ': '捷克', 'GR': '希腊', 'HU': '匈牙利', 'RO': '罗马尼亚', 'TR': '土耳其',
    'BG': '保加利亚', 'LT': '立陶宛', 'LV': '拉脱维亚', 'EE': '爱沙尼亚', 'BY': '白俄罗斯',
    'LU': '卢森堡', 'LUX': '卢森堡', 'SI': '斯洛文尼亚', 'SK': '斯洛伐克', 'MT': '马耳他',
    'HR': '克罗地亚', 'RS': '塞尔维亚', 'BA': '波黑', 'ME': '黑山', 'MK': '北马其顿',
    'AL': '阿尔巴尼亚', 'XK': '科索沃', 'MD': '摩尔多瓦', 'GE': '格鲁吉亚', 'AM': '亚美尼亚',
    'AZ': '阿塞拜疆', 'CY': '塞浦路斯', 'MC': '摩纳哥', 'SM': '圣马力诺', 'VA': '梵蒂冈',
    'AD': '安道尔', 'LI': '列支敦士登',
    # 亚洲
    'CN': '中国', 'HK': '中国香港', 'TW': '中国台湾', 'MO': '中国澳门', 'JP': '日本', 'KR': '韩国',
    'SG': '新加坡', 'SGP': '新加坡', 'IN': '印度', 'ID': '印度尼西亚', 'MY': '马来西亚', 'MYS': '马来西亚',
    'TH': '泰国', 'PH': '菲律宾', 'VN': '越南', 'PK': '巴基斯坦', 'BD': '孟加拉', 'KZ': '哈萨克斯坦',
    'IL': '以色列', 'ISR': '以色列', 'SA': '沙特阿拉伯', 'SAU': '沙特阿拉伯', 'AE': '阿联酋', 
    'QAT': '卡塔尔', 'OMN': '阿曼', 'KW': '科威特', 'BH': '巴林', 'IQ': '伊拉克', 'IR': '伊朗',
    'AF': '阿富汗', 'UZ': '乌兹别克斯坦', 'KG': '吉尔吉斯斯坦', 'TJ': '塔吉克斯坦', 'TM': '土库曼斯坦',
    'MN': '蒙古', 'NP': '尼泊尔', 'BT': '不丹', 'LK': '斯里兰卡', 'MV': '马尔代夫',
    'MM': '缅甸', 'LA': '老挝', 'KH': '柬埔寨', 'BN': '文莱', 'TL': '东帝汶',
    'LK': '斯里兰卡', 'MV': '马尔代夫', 'NP': '尼泊尔', 'BT': '不丹',
    # 大洋洲
    'AU': '澳大利亚', 'NZ': '新西兰', 'FJ': '斐济', 'PG': '巴布亚新几内亚', 'NC': '新喀里多尼亚',
    'VU': '瓦努阿图', 'SB': '所罗门群岛', 'TO': '汤加', 'WS': '萨摩亚', 'KI': '基里巴斯',
    'TV': '图瓦卢', 'NR': '瑙鲁', 'PW': '帕劳', 'FM': '密克罗尼西亚', 'MH': '马绍尔群岛',
    # 非洲
    'ZA': '南非', 'EG': '埃及', 'NG': '尼日利亚', 'KE': '肯尼亚', 'ET': '埃塞俄比亚',
    'GH': '加纳', 'TZ': '坦桑尼亚', 'UG': '乌干达', 'DZ': '阿尔及利亚', 'MA': '摩洛哥',
    'TN': '突尼斯', 'LY': '利比亚', 'SD': '苏丹', 'SS': '南苏丹', 'ER': '厄立特里亚',
    'DJ': '吉布提', 'SO': '索马里', 'ET': '埃塞俄比亚', 'KE': '肯尼亚', 'TZ': '坦桑尼亚',
    'UG': '乌干达', 'RW': '卢旺达', 'BI': '布隆迪', 'MW': '马拉维', 'ZM': '赞比亚',
    'ZW': '津巴布韦', 'BW': '博茨瓦纳', 'NA': '纳米比亚', 'SZ': '斯威士兰', 'LS': '莱索托',
    'MZ': '莫桑比克', 'MG': '马达加斯加', 'MU': '毛里求斯', 'SC': '塞舌尔', 'KM': '科摩罗',
    'CV': '佛得角', 'ST': '圣多美和普林西比', 'GW': '几内亚比绍', 'GN': '几内亚', 'SL': '塞拉利昂',
    'LR': '利比里亚', 'CI': '科特迪瓦', 'GH': '加纳', 'TG': '多哥', 'BJ': '贝宁',
    'NE': '尼日尔', 'BF': '布基纳法索', 'ML': '马里', 'SN': '塞内加尔', 'GM': '冈比亚',
    'GN': '几内亚', 'GW': '几内亚比绍', 'ST': '圣多美和普林西比', 'CV': '佛得角',
    # 其他
    'Unknown': '未知'
}

# ===== 全局变量 =====
region_cache = {}

# ===== 网络会话配置 =====
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0'
})

# 配置连接池
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=3
)
session.mount('http://', adapter)
session.mount('https://', adapter)

# ===== 缓存管理模块 =====

def load_region_cache():
    """加载地区缓存"""
    global region_cache
    if os.path.exists('Cache.json'):
        try:
            with open('Cache.json', 'r', encoding='utf-8') as f:
                region_cache = json.load(f)
            logger.info(f"📦 成功加载缓存文件，包含 {len(region_cache)} 个条目")
        except Exception as e:
            logger.warning(f"⚠️ 加载缓存文件失败: {str(e)[:50]}")
            region_cache = {}
    else:
        logger.info("📦 缓存文件不存在，使用空缓存")
        region_cache = {}

def save_region_cache():
    """保存地区缓存"""
    try:
        with open('Cache.json', 'w', encoding='utf-8') as f:
            json.dump(region_cache, f, ensure_ascii=False)
        logger.info(f"💾 成功保存缓存文件，包含 {len(region_cache)} 个条目")
    except Exception as e:
        logger.error(f"❌ 保存缓存文件失败: {str(e)[:50]}")
        pass

def is_cache_valid(timestamp, ttl_hours=24):
    """检查缓存是否有效"""
    if not timestamp:
        return False
    cache_time = datetime.fromisoformat(timestamp)
    return datetime.now() - cache_time < timedelta(hours=ttl_hours)

def clean_expired_cache():
    """清理过期缓存和限制缓存大小"""
    global region_cache
    current_time = datetime.now()
    expired_keys = []
    
    # 清理过期缓存
    for ip, data in region_cache.items():
        if isinstance(data, dict) and 'timestamp' in data:
            cache_time = datetime.fromisoformat(data['timestamp'])
            if current_time - cache_time >= timedelta(hours=CONFIG["cache_ttl_hours"]):
                expired_keys.append(ip)
    
    for key in expired_keys:
        del region_cache[key]
    
    # 限制缓存大小（最多保留1000个条目）
    if len(region_cache) > 1000:
        # 按时间排序，删除最旧的条目
        sorted_items = sorted(region_cache.items(), 
                            key=lambda x: x[1].get('timestamp', '') if isinstance(x[1], dict) else '')
        items_to_remove = len(region_cache) - 1000
        for i in range(items_to_remove):
            del region_cache[sorted_items[i][0]]
        logger.info(f"缓存过大，清理了 {items_to_remove} 个旧条目")
    
    if expired_keys:
        logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")

# ===== 文件操作模块 =====

def delete_file_if_exists(file_path):
    """删除原有文件，避免结果累积"""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"🗑️ 已删除原有文件: {file_path}")
        except Exception as e:
            logger.warning(f"⚠️ 删除文件失败: {str(e)}")

# ===== 网络检测模块 =====


def test_ip_availability(ip):
    """TCP Socket检测IP可用性 - 支持多端口自定义"""
    min_delay = float('inf')
    success_count = 0
    
    # 遍历配置的测试端口
    for port in CONFIG["test_ports"]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)  # 3秒超时
                start_time = time.time()
                
                # 尝试TCP连接
                if s.connect_ex((ip, port)) == 0:
                    delay = round((time.time() - start_time) * 1000)
                    min_delay = min(min_delay, delay)
                    success_count += 1
                    
                    # 如果延迟很好，立即返回最佳结果
                    if delay < 200:
                        return (True, delay)
        except (socket.timeout, socket.error, OSError):
            continue  # 继续测试下一个端口
    
    # 返回最佳结果
    if success_count > 0:
        return (True, min_delay)
    
    return (False, 0)

# ===== 地区识别模块 =====

def get_ip_region(ip):
    """优化的IP地区识别（支持缓存TTL）"""
    # 检查缓存是否有效
    if ip in region_cache:
        cached_data = region_cache[ip]
        if isinstance(cached_data, dict) and 'timestamp' in cached_data:
            if is_cache_valid(cached_data['timestamp'], CONFIG["cache_ttl_hours"]):
                logger.debug(f"📦 IP {ip} 地区信息从缓存获取: {cached_data['region']}")
                return cached_data['region']
        else:
            # 兼容旧格式缓存
            logger.debug(f"📦 IP {ip} 地区信息从缓存获取（旧格式）: {cached_data}")
            return cached_data
    
    # 尝试主要API
    logger.debug(f"🌐 IP {ip} 开始API查询（主要API: ipinfo.io）...")
    try:
        resp = session.get(f'https://ipinfo.io/{ip}?token=2cb674df499388', timeout=CONFIG["api_timeout"])
        if resp.status_code == 200:
            country_code = resp.json().get('country', '').upper()
            if country_code:
                region_cache[ip] = {
                    'region': country_code,
                    'timestamp': datetime.now().isoformat()
                }
                logger.debug(f"✅ IP {ip} 主要API识别成功: {country_code}")
                return country_code
        else:
            logger.debug(f"⚠️ IP {ip} 主要API返回状态码: {resp.status_code}")
    except Exception as e:
        logger.debug(f"❌ IP {ip} 主要API识别失败: {str(e)[:30]}")
        pass
    
    # 尝试备用API
    logger.debug(f"🌐 IP {ip} 尝试备用API（ip-api.com）...")
    try:
        resp = session.get(f'http://ip-api.com/json/{ip}?fields=countryCode', timeout=CONFIG["api_timeout"])
        if resp.json().get('status') == 'success':
            country_code = resp.json().get('countryCode', '').upper()
            if country_code:
                region_cache[ip] = {
                    'region': country_code,
                    'timestamp': datetime.now().isoformat()
                }
                logger.debug(f"✅ IP {ip} 备用API识别成功: {country_code}")
                return country_code
        else:
            logger.debug(f"⚠️ IP {ip} 备用API返回状态: {resp.json().get('status', 'unknown')}")
    except Exception as e:
        logger.debug(f"❌ IP {ip} 备用API识别失败: {str(e)[:30]}")
        pass
    
    # 失败返回Unknown
    logger.debug(f"❌ IP {ip} 所有API识别失败，标记为Unknown")
    region_cache[ip] = {
        'region': 'Unknown',
        'timestamp': datetime.now().isoformat()
    }
    return 'Unknown'

def get_country_name(code):
    """根据国家代码获取中文名称"""
    return COUNTRY_MAPPING.get(code, code)

# ===== 并发处理模块 =====

def test_ips_concurrently(ips, max_workers=None):
    """
    超快并发检测IP可用性（防卡住优化）
    使用ThreadPoolExecutor实现并发处理，大幅提升检测效率
    """
    if max_workers is None:
        max_workers = CONFIG["max_workers"]
    
    logger.info(f"📡 开始并发检测 {len(ips)} 个IP，使用 {max_workers} 个线程")
    available_ips = []
    
    # 使用更小的批次，避免卡住
    batch_size = 20  # 减少批次大小到20
    start_time = time.time()
    
    for i in range(0, len(ips), batch_size):
        batch_ips = ips[i:i+batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(ips)-1)//batch_size + 1
        
        logger.info(f"📡 处理批次 {batch_num}/{total_batches}，包含 {len(batch_ips)} 个IP")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交批次任务，添加超时保护
            future_to_ip = {executor.submit(test_ip_availability, ip): ip for ip in batch_ips}
            
            # 处理完成的任务
            batch_completed = 0
            for future in as_completed(future_to_ip, timeout=30):  # 添加30秒超时保护
                ip = future_to_ip[future]
                batch_completed += 1
                completed = i + batch_completed
                elapsed = time.time() - start_time
                
                try:
                    is_available, delay = future.result()
                    if is_available:
                        available_ips.append((ip, delay))
                        logger.info(f"[{completed}/{len(ips)}] {ip} ✅ 可用（延迟 {delay}ms）- 耗时: {elapsed:.1f}s")
                    else:
                        logger.info(f"[{completed}/{len(ips)}] {ip} ❌ 不可用 - 耗时: {elapsed:.1f}s")
                    
                    # 添加小延迟确保日志顺序
                    time.sleep(0.01)  # 10ms延迟
                except Exception as e:
                    logger.error(f"[{completed}/{len(ips)}] {ip} ❌ 检测出错: {str(e)[:30]} - 耗时: {elapsed:.1f}s")
                    
                    # 添加小延迟确保日志顺序
                    time.sleep(0.01)  # 10ms延迟
        
        # 批次间短暂休息，避免过度占用资源
        if i + batch_size < len(ips):
            time.sleep(0.2)  # 减少休息时间
    
    total_time = time.time() - start_time
    logger.info(f"📡 并发检测完成，发现 {len(available_ips)} 个可用IP，总耗时: {total_time:.1f}秒")
    return available_ips

def get_regions_concurrently(ips, max_workers=None):
    """优化的并发地区识别 - 保持日志顺序"""
    if max_workers is None:
        max_workers = min(CONFIG["max_workers"], 15)  # 增加最大线程数到15
    
    logger.info(f"🌍 开始并发地区识别 {len(ips)} 个IP，使用 {max_workers} 个线程")
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_ip = {executor.submit(get_ip_region, ip): (ip, delay) for ip, delay in ips}
        
        # 按提交顺序处理结果，保持日志顺序
        for i, (ip, delay) in enumerate(ips, 1):
            future = None
            # 找到对应的future
            for f, (f_ip, f_delay) in future_to_ip.items():
                if f_ip == ip and f_delay == delay:
                    future = f
                    break
            
            if future:
                try:
                    region_code = future.result()
                    results.append((ip, region_code, delay))
                    country_name = get_country_name(region_code)
                    elapsed = time.time() - start_time
                    logger.info(f"[{i}/{len(ips)}] {ip} -> {country_name} ({region_code}) - 耗时: {elapsed:.1f}s")
                    
                    # 添加小延迟确保日志顺序
                    time.sleep(0.01)  # 10ms延迟
                    
                    # 只在API查询时等待，缓存查询不需要等待
                    if i % 5 == 0:  # 每5个IP等待一次，减少等待频率
                        time.sleep(CONFIG["query_interval"])
                except Exception as e:
                    logger.warning(f"地区识别失败 {ip}: {str(e)[:50]}")
                    results.append((ip, 'Unknown', delay))
                    elapsed = time.time() - start_time
                    logger.info(f"[{i}/{len(ips)}] {ip} -> 未知 (Unknown) - 耗时: {elapsed:.1f}s")
                    
                    # 添加小延迟确保日志顺序
                    time.sleep(0.01)  # 10ms延迟
    
    total_time = time.time() - start_time
    logger.info(f"🌍 地区识别完成，处理了 {len(results)} 个IP，总耗时: {total_time:.1f}秒")
    return results

# ===== 主程序模块 =====

def main():
    start_time = time.time()
    
    # 1. 预处理：删除旧文件
    delete_file_if_exists('IPlist.txt')
    delete_file_if_exists('Senflare.txt')
    logger.info("🗑️ 预处理完成，旧文件已清理")

    # 2. 采集IP地址
    logger.info("📥 ===== 采集IP地址 =====")
    all_ips = []
    successful_sources = 0
    failed_sources = 0
    
    # 采集IP源
    for i, url in enumerate(CONFIG["ip_sources"]):
        try:
            logger.info(f"🔍 从 {url} 采集...")
            # 添加请求间隔，避免频率限制
            if i > 0:
                time.sleep(CONFIG["query_interval"])  # 使用配置的间隔时间
            resp = session.get(url, timeout=CONFIG["timeout"])  # 使用配置的超时时间
            if resp.status_code == 200:
                # 提取并验证IPv4地址
                ips = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', resp.text)
                valid_ips = [
                    ip for ip in ips 
                    if all(0 <= int(part) <= 255 for part in ip.split('.'))
                ]
                
                # 调试信息：记录原始找到的IP数量
                if len(ips) > 0 and len(valid_ips) == 0:
                    logger.debug(f"从 {url} 找到 {len(ips)} 个IP，但验证后为0个")
                
                # 如果正则表达式没有找到IP，尝试按行分割查找
                if len(valid_ips) == 0:
                    lines = resp.text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        # 检查是否是纯IP地址行
                        if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', line):
                            if all(0 <= int(part) <= 255 for part in line.split('.')):
                                valid_ips.append(line)
                
                all_ips.extend(valid_ips)
                successful_sources += 1
                logger.info(f"✅ 成功采集 {len(valid_ips)} 个有效IP地址")
            elif resp.status_code == 403:
                failed_sources += 1
                logger.warning(f"⚠️ 被限制访问（状态码 403），跳过此源")
            else:
                failed_sources += 1
                logger.warning(f"❌ 失败（状态码 {resp.status_code}）")
        except Exception as e:
            failed_sources += 1
            error_msg = str(e)[:50]
            logger.error(f"❌ 出错: {error_msg}")
    
    logger.info(f"📊 采集统计: 成功 {successful_sources} 个源，失败 {failed_sources} 个源")

    # 3. IP去重与排序
    unique_ips = sorted(list(set(all_ips)), key=lambda x: [int(p) for p in x.split('.')])
    logger.info(f"🔢 去重后共 {len(unique_ips)} 个唯一IP地址")

    # 4. 并发检测IP可用性
    logger.info("📡 ===== 并发检测IP可用性 =====")
    available_ips = test_ips_concurrently(unique_ips)
    
    # 5. 保存可用IP列表
    if available_ips:
        with open('IPlist.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join([ip for ip, _ in available_ips]))
        logger.info(f"📄 已保存 {len(available_ips)} 个可用IP到 IPlist.txt")
    else:
        logger.warning("⚠️ 未检测到可用IP，跳过后续处理")

    # 6. 并发地区识别与结果格式化
    logger.info("🌍 ===== 并发地区识别与结果格式化 =====")
    region_results = get_regions_concurrently(available_ips)
    
    # 按地区分组
    region_groups = defaultdict(list)
    for ip, region_code, delay in region_results:
        country_name = get_country_name(region_code)
        region_groups[country_name].append((ip, region_code, delay))
    
    logger.info(f"🌍 地区分组完成，共 {len(region_groups)} 个地区")
    
    # 7. 生成并保存最终结果
    result = []
    for region in sorted(region_groups.keys()):
        # 同一地区内按延迟排序（更快的在前）
        sorted_ips = sorted(region_groups[region], key=lambda x: x[2])
        for idx, (ip, code, _) in enumerate(sorted_ips, 1):
            result.append(f"{ip}#{code} {region}节点 | {idx:02d}")
        logger.debug(f"地区 {region} 格式化完成，包含 {len(sorted_ips)} 个IP")
    
    if result:
        with open('Senflare.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(result))
        logger.info(f"📊 已保存 {len(result)} 条格式化记录到 Senflare.txt")
    else:
        logger.warning("⚠️ 无有效记录可保存")
    
    # 8. 保存缓存并显示统计信息
    save_region_cache()
    
    # 显示总耗时
    run_time = round(time.time() - start_time, 2)
    logger.info(f"⏱️ 总耗时: {run_time}秒")
    logger.info(f"📊 缓存统计: 总计 {len(region_cache)} 个")
    logger.info("🏁 ===== 程序完成 =====")

# ===== 程序入口 =====
if __name__ == "__main__":
    # 程序启动日志
    logger.info("🚀 ===== 开始IP处理程序 =====")
    
    # 初始化缓存
    load_region_cache()
    
    # 清理过期缓存
    clean_expired_cache()
    
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⏹️ 程序被用户中断")
    except Exception as e:
        logger.error(f"❌ 运行出错: {str(e)}")

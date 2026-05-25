import os
import time
import requests
import re
import base64
from zhipuai import ZhipuAI
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# ================= 核心配置区域 =================
# 【请务必填入你的智谱 API Key】
API_KEY = "填入你的智谱 API Key"
SEARCH_KEYWORD = "填入你的学科"
# ==============================================

def get_image_base64(image_path):
    """将本地图片转换为大模型需要的 Base64 编码格式"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def sanitize_filename(filename):
    """清理文件名中的非法字符，防止保存文件时报错"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def main():
    # 1. 准备本地文件夹
    desktop_path = os.path.join(os.path.expanduser("~"), 'Desktop')
    base_folder = os.path.join(desktop_path, f'{SEARCH_KEYWORD}_全部课程教案库')
    if not os.path.exists(base_folder):
        os.makedirs(base_folder)

    if API_KEY == "填入你的真实API_KEY":
        print("【警告】你还没有填入 API_KEY！请修改代码后再运行。")
        return

    client = ZhipuAI(api_key=API_KEY)
    
    print(">>> 启动浏览器，开始自动化流水线 <<<")
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(options=options)
    
    try:
        # ================= 第一阶段：收集所有课程网址 =================
        print(f"\n--- 阶段一：搜索【{SEARCH_KEYWORD}】并收集课程链接 ---")
        driver.get('https://xhsz.news.cn/')
        driver.maximize_window()
        time.sleep(3)
        original_window = driver.current_window_handle
        
        search_box = driver.find_element(By.XPATH, "//input[@type='text' or contains(@placeholder, '搜索')]")
        search_box.clear()
        search_box.send_keys(SEARCH_KEYWORD)
        time.sleep(1)
        
        try:
            driver.find_element(By.XPATH, "//*[contains(text(), '资源搜索')]").click()
        except:
            search_box.send_keys(Keys.RETURN)

        time.sleep(4)
        for window_handle in driver.window_handles:
            if window_handle != original_window:
                driver.switch_to.window(window_handle)
                break
                
        # 进入完整列表页
        tabs = driver.find_elements(By.XPATH, "//*[contains(text(), '示范课程')]")
        switched = False
        for tab in tabs:
            if "(" in tab.text or "（" in tab.text:
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(4)
                switched = True
                break
                
        if not switched:
            more_btns = driver.find_elements(By.XPATH, "//*[contains(text(), '更多结果') or contains(text(), '查看更多')]")
            for btn in more_btns:
                if btn.is_displayed():
                    try:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(4) 
                        break
                    except:
                        pass
        
        all_course_urls = []
        current_page = 1
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2) 
            course_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/curriculum/detail/')]")
            for el in course_elements:
                link = el.get_attribute("href")
                if link and link not in all_course_urls:
                    all_course_urls.append(link)
            
            try:
                # 终极翻页代码
                next_btn = driver.find_element(By.XPATH, "//a[contains(@class, 'next')]")
                href = next_btn.get_attribute("href")
                if not href or 'disabled' in next_btn.get_attribute("class"):
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                current_page += 1
                time.sleep(4) 
            except Exception:
                break
                
        print(f"✅ 阶段一完成：共收集到 {len(all_course_urls)} 个课程网址！\n")

        # ================= 第二阶段：逐个访问、下载并进行 AI 识别 =================
        print("--- 阶段二：逐一提取课程教案（该过程时间较长，请耐心等待） ---")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://xhsz.news.cn/'
        }
        
        system_prompt = (
            "你是一个顶级的 OCR 和排版专家。请准确提取图片中的所有文字，"
            "并严格按照原图的层级结构（如大标题、二级标题、列表、段落等）输出为纯 Markdown 格式。"
            "不要包含任何开场白、解释语或提示性文字，直接输出 Markdown 内容即可。"
        )

        for index, url in enumerate(all_course_urls, start=1):
            try:
                driver.get(url)
                time.sleep(3) # 等待页面加载
                
                # ================= 完美防覆盖命名 =================
                try:
                    title_el = driver.find_element(By.XPATH, "//h2 | //h1 | //div[contains(@class, 'title') or contains(@class, 'name')]")
                    raw_title = title_el.text.strip()
                    raw_title = raw_title.split('\n')[0][:25] 
                except:
                    raw_title = driver.title.split('-')[0].strip()
                
                if not raw_title:
                    raw_title = "未命名课程"
                    
                # 强制增加 "01_", "02_" 的序号前缀，绝对防止覆盖
                course_name = f"{index:02d}_{sanitize_filename(raw_title)}"
                # ===================================================
                
                print(f"\n==================================================")
                print(f"🚀 正在处理第 {index}/{len(all_course_urls)} 个课程：【{course_name}】")
                
                # 1. 点击“教学设计”标签
                try:
                    tab_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '教学设计')]"))
                    )
                    driver.execute_script("arguments[0].click();", tab_element)
                    time.sleep(3)
                except Exception:
                    print(f"  [跳过] 该课程没有“教学设计”版块，跳过处理。")
                    continue
                
                # 2. 提取并下载图片
                images = driver.find_elements(By.XPATH, "//img")
                valid_img_urls = []
                for img in images:
                    src = img.get_attribute('src')
                    if src and ('http' in src) and ('/document/' in src):
                        valid_img_urls.append(src)
                
                valid_img_urls = list(dict.fromkeys(valid_img_urls))
                
                if not valid_img_urls:
                    print(f"  [跳过] 该课程的教学设计中未发现有效图片。")
                    continue
                    
                print(f"  -> 发现 {len(valid_img_urls)} 页教学设计，正在下载...")
                
                # 为该课程创建一个存放图片的临时子文件夹
                course_img_folder = os.path.join(base_folder, f"{course_name}_图片库")
                if not os.path.exists(course_img_folder):
                    os.makedirs(course_img_folder)
                    
                img_files_saved = []
                for img_idx, img_url in enumerate(valid_img_urls, start=1):
                    try:
                        response = requests.get(img_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            file_name = f"第{img_idx}页.png"
                            file_path = os.path.join(course_img_folder, file_name)
                            with open(file_path, 'wb') as f:
                                f.write(response.content)
                            img_files_saved.append(file_name)
                    except:
                        pass
                
                # 3. 呼叫 AI 进行文字提取，生成 MD 文件
                md_output_path = os.path.join(base_folder, f"{course_name}.md")
                print(f"  -> 图片下载完毕，呼叫大模型提取 Markdown...")
                
                # 确保图片按顺序识别
                def sort_key(filename):
                    nums = re.findall(r'\d+', filename)
                    return int(nums[0]) if nums else 0
                img_files_saved.sort(key=sort_key)
                
                with open(md_output_path, 'w', encoding='utf-8') as md_file:
                    md_file.write(f"# {course_name.split('_', 1)[-1]}\n\n")
                    
                    for img_name in img_files_saved:
                        img_path = os.path.join(course_img_folder, img_name)
                        print(f"    - AI 正在阅读 {img_name}...")
                        
                        try:
                            base64_image = get_image_base64(img_path)
                            response = client.chat.completions.create(
                                model="glm-4v-flash", 
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": [
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                        {"type": "text", "text": "提取内容。"}
                                    ]}
                                ],
                                temperature=0.1
                            )
                            md_file.write(f"## {img_name.split('.')[0]}\n\n")
                            md_file.write(response.choices[0].message.content)
                            md_file.write("\n\n---\n\n") 
                            
                            # 【极端重要】：API 免费调用有频率限制，每张图识别完休息 2 秒防止报错
                            time.sleep(2) 
                        except Exception as e:
                            print(f"    - {img_name} 提取失败: {e}")
                            md_file.write(f"**[ {img_name} 识别失败 ]**\n\n")
                
                print(f"  ✅ 【{course_name}】处理完成！")
                
            except Exception as e:
                print(f"处理第 {index} 个网址时发生未知错误，跳过: {e}")

    finally:
        time.sleep(3)
        driver.quit()
        print(f"\n🎉🎉🎉 全部任务圆满结束！")
        print(f"请前往桌面查看 【{SEARCH_KEYWORD}_全部课程教案库】 文件夹，里面有所有的 Markdown 文件！")

if __name__ == "__main__":
    main()
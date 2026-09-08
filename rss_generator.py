#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PwC Monthly Economist Report RSS Feed Generator
指定されたURLからレポート一覧を取得し、RSSフィードを生成します
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ============================================
# 設定
# ============================================

TARGET_URL = "https://www.pwc.com/jp/ja/services/consulting/intelligence/monthly-economist-report.html"
OUTPUT_FILE = "feed.xml"
TIMEZONE_JST = timezone(timedelta(hours=9))

# RSSフィードの基本情報
FEED_TITLE = "PwC Monthly Economist Report"
FEED_LINK = "https://www.pwc.com/jp/ja/services/consulting/intelligence/monthly-economist-report.html"
FEED_DESCRIPTION = "PwC Japanグループが発行する月次マクロ経済レポートのRSSフィード"
FEED_LANGUAGE = "ja"

# ============================================
# 関数定義
# ============================================

def setup_driver():
    """Selenium WebDriverをセットアップ"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # ヘッドレスモード（画面表示なし）
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=ja")
    
    # User-Agentを設定（PwCサイトは日本語環境を要求する場合がある）
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        # WebDriver Managerを使用して自動的にChromeDriverを管理
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"ChromeDriverのセットアップに失敗しました: {e}")
        print("代替手段として、システムにインストールされたChromeDriverを使用します...")
        # フォールバック: システムのChromeDriverを使用
        return webdriver.Chrome(options=chrome_options)

def fetch_page_with_selenium(url):
    """Seleniumを使用してページを取得（JavaScriptレンダリング対応）"""
    driver = None
    try:
        print(f"ページを読み込み中: {url}")
        driver = setup_driver()
        driver.get(url)
        
        # ページが完全に読み込まれるまで待機（最大30秒）
        wait = WebDriverWait(driver, 30)
        
        # レポート一覧が表示されるまで待機（コレクション要素を待つ）
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "collection__item")))
            print("レポート一覧を検出しました")
        except:
            print("コレクション要素が見つかりませんでした。別のセレクタを試みます...")
            # 代わりにarticle要素を待つ
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        
        # スクロールしてすべてのアイテムを読み込む（無限スクロール対策）
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 5
        
        while scroll_attempts < max_scroll_attempts:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            driver.implicitly_wait(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
            print(f"スクロール {scroll_attempts}/{max_scroll_attempts}")
        
        # ページソースを取得
        html = driver.page_source
        print("ページの取得が完了しました")
        return html
        
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def parse_reports_from_html(html):
    """HTMLからレポート情報を抽出"""
    if not html:
        print("HTMLが空です")
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    
    # 複数のパターンで記事を検索
    # パターン1: collection__item クラスを持つ要素
    items = soup.find_all('article', class_='collection__item')
    
    # パターン2: もし見つからなければ、別のセレクタを試す
    if not items:
        items = soup.find_all('div', class_='collection__item')
    
    if not items:
        # AngularJSでレンダリングされたコンテンツの場合、ng-repeatで検索
        items = soup.find_all(attrs={'ng-repeat': True})
    
    print(f"見つかったアイテム数: {len(items)}")
    
    for item in items:
        try:
            # タイトルとリンクの抽出（複数のパターンを試す）
            title = None
            link = None
            
            # パターン1: h4タグ内のspan
            title_elem = item.find('h4', class_='collection__item-heading')
            if title_elem:
                span = title_elem.find('span')
                if span:
                    title = span.get_text(strip=True)
            
            # パターン2: 通常のaタグ
            if not title:
                a_tag = item.find('a')
                if a_tag and a_tag.get('href'):
                    # リンク先からタイトルを推測
                    href = a_tag.get('href')
                    if href and '/monthly-economist-report' in href:
                        # 日付部分を抽出してタイトルにする
                        date_match = re.search(r'(\d{6})', href)
                        if date_match:
                            title = f"Monthly Economist Report {date_match.group(1)}"
            
            # リンクの抽出
            a_tag = item.find('a')
            if a_tag and a_tag.get('href'):
                href = a_tag.get('href')
                if href.startswith('/'):
                    link = urljoin('https://www.pwc.com', href)
                elif href.startswith('http'):
                    link = href
            
            # 日付の抽出
            pub_date = None
            date_elem = item.find('time')
            if date_elem:
                pub_date = date_elem.get('datetime')
                if not pub_date:
                    pub_date = date_elem.get_text(strip=True)
            
            # 説明文の抽出
            description = None
            desc_elem = item.find('p', class_='paragraph')
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            
            # サムネイル画像の抽出
            image_url = None
            img_elem = item.find('img')
            if img_elem:
                image_url = img_elem.get('src') or img_elem.get('data-src')
                if image_url and not image_url.startswith('http'):
                    image_url = urljoin('https://www.pwc.com', image_url)
            
            # 有効なデータのみ追加
            if title and link:
                reports.append({
                    'title': title,
                    'link': link,
                    'description': description or f"PwC Monthly Economist Report: {title}",
                    'pub_date': pub_date,
                    'image_url': image_url
                })
                print(f"[ステッカー] レポートを追加: {title[:50]}...")
                
        except Exception as e:
            print(f"アイテムの解析中にエラー: {e}")
            continue
    
    return reports

def generate_rss(reports):
    """RSSフィードを生成"""
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=FEED_LINK, rel='alternate')
    fg.description(FEED_DESCRIPTION)
    fg.language(FEED_LANGUAGE)
    fg.lastBuildDate(datetime.now(TIMEZONE_JST))
    
    for report in reports:
        entry = fg.add_entry()
        entry.title(report['title'])
        entry.link(href=report['link'], rel='alternate')
        
        # 説明文の生成（HTMLとしてマークアップ）
        description_html = f"<p>{report['description']}</p>"
        if report.get('image_url'):
            description_html = f'<img src="{report["image_url"]}" alt="{report["title"]}" style="max-width:100%;"/><br/>' + description_html
        entry.description(description_html)
        
        # 公開日
        if report.get('pub_date'):
            try:
                # 様々な日付形式に対応
                pub_date_str = report['pub_date']
                # 形式1: "01/09/26" (日/月/年)
                if re.match(r'\d{2}/\d{2}/\d{2}', pub_date_str):
                    day, month, year = pub_date_str.split('/')
                    pub_date = datetime(2000 + int(year), int(month), int(day), tzinfo=TIMEZONE_JST)
                else:
                    # その他の形式は試行錯誤
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').replace(tzinfo=TIMEZONE_JST)
                entry.pubDate(pub_date)
            except:
                # 日付解析に失敗した場合は現在時刻を使用
                entry.pubDate(datetime.now(TIMEZONE_JST))
        else:
            entry.pubDate(datetime.now(TIMEZONE_JST))
        
        # GUID（一意の識別子）
        entry.guid(report['link'], permalink=True)
    
    # RSSフィードをファイルに出力
    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"[ステッカー] RSSフィードを生成しました: {OUTPUT_FILE}")
    print(f"[ステッカー] 合計 {len(reports)} 件のレポートを追加")

def main():
    """メイン実行関数"""
    print("=" * 50)
    print("PwC Monthly Economist Report RSS Generator")
    print("=" * 50)
    print(f"対象URL: {TARGET_URL}")
    print(f"出力先: {OUTPUT_FILE}")
    print("-" * 50)
    
    # ページを取得
    html = fetch_page_with_selenium(TARGET_URL)
    
    if not html:
        print("[ステッカー] ページの取得に失敗しました")
        return 1
    
    # レポート情報を抽出
    reports = parse_reports_from_html(html)
    
    if not reports:
        print("[ステッカー] レポートが見つかりませんでした")
        return 1
    
    # RSSを生成
    generate_rss(reports)
    
    print("-" * 50)
    print("[ステッカー] 処理が完了しました")
    return 0

if __name__ == "__main__":
    exit(main())

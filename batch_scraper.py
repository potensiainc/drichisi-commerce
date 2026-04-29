# -*- coding: utf-8 -*-
"""
Amazon Japan 일괄 스크래퍼
구글시트 URL 목록 기반 스크래핑 + 한국어 상세페이지 생성
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from urllib.parse import unquote

class AmazonBatchScraper:
    def __init__(self, output_dir="products"):
        self.output_dir = output_dir
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja-JP,ja;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.cookies.set('i18n-prefs', 'JPY', domain='.amazon.co.jp')

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def extract_asin(self, url):
        """URL에서 ASIN 추출"""
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/ASIN/([A-Z0-9]{10})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def fetch_page(self, url):
        """페이지 HTML 가져오기"""
        try:
            clean_url = url.split('?')[0] if '?' in url else url

            # 랜덤 User-Agent
            import random
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            ]
            self.session.headers['User-Agent'] = random.choice(user_agents)

            time.sleep(random.uniform(1, 2))  # 랜덤 딜레이

            response = self.session.get(clean_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"    페이지 가져오기 실패: {e}")
            return None

    def parse_product(self, html, url):
        """상품 정보 파싱"""
        soup = BeautifulSoup(html, 'html.parser')
        product = {}

        product['asin'] = self.extract_asin(url)
        product['url'] = url

        # 상품명
        title_elem = soup.select_one('#productTitle')
        product['title'] = title_elem.get_text(strip=True) if title_elem else ""

        # 브랜드
        brand_elem = soup.select_one('#bylineInfo')
        if brand_elem:
            brand_text = brand_elem.get_text(strip=True)
            brand_text = re.sub(r'(のストアを表示|ブランド:|: )', '', brand_text)
            product['brand'] = brand_text.strip()
        else:
            product['brand'] = ""

        # 가격
        product['prices'] = self._extract_prices(soup)

        # 상품 설명
        product['description'] = self._extract_description(soup)

        # 상품 특징
        product['features'] = self._extract_features(soup)

        # 상세 정보
        product['details'] = self._extract_details(soup)

        # 옵션
        product['options'] = self._extract_options(soup, html)

        # 이미지
        product['images'] = self._extract_images(soup, html)

        # 리뷰
        product['reviews'] = self._extract_reviews(soup)

        return product

    def _extract_prices(self, soup):
        prices = {}
        price_selectors = [
            '#corePrice_feature_div .a-price .a-offscreen',
            '#corePriceDisplay_desktop_feature_div .a-price .a-offscreen',
            '.a-price .a-offscreen',
        ]
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                prices['current'] = price_elem.get_text(strip=True)
                break
        return prices

    def _extract_description(self, soup):
        descriptions = []
        desc_elem = soup.select_one('#productDescription')
        if desc_elem:
            descriptions.append(desc_elem.get_text(strip=True))

        # A+ 콘텐츠
        aplus = soup.select_one('#aplus')
        if aplus:
            for text in aplus.stripped_strings:
                if len(text) > 20:
                    descriptions.append(text)

        return '\n'.join(descriptions[:5])

    def _extract_features(self, soup):
        features = []
        feature_list = soup.select('#feature-bullets li span.a-list-item')
        for item in feature_list:
            text = item.get_text(strip=True)
            if text and not text.startswith('›'):
                features.append(text)

        # 제품 정보 섹션
        product_facts = soup.select('.product-facts-title + ul li')
        for item in product_facts:
            text = item.get_text(strip=True)
            if text:
                features.append(text)

        return features

    def _extract_details(self, soup):
        details = {}
        detail_tables = soup.select('#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr')
        for row in detail_tables:
            th = row.select_one('th')
            td = row.select_one('td')
            if th and td:
                key = th.get_text(strip=True)
                value = td.get_text(strip=True)
                details[key] = value
        return details

    def _extract_options(self, soup, html):
        options = {}

        # JavaScript에서 옵션 추출
        variation_match = re.search(r'"variationValues"\s*:\s*(\{[^}]+\})', html)
        if variation_match:
            try:
                variation_data = json.loads(variation_match.group(1))
                if 'size_name' in variation_data:
                    options['sizes'] = variation_data['size_name']
                if 'color_name' in variation_data:
                    options['colors'] = variation_data['color_name']
            except:
                pass

        return options

    def _extract_images(self, soup, html):
        images = []

        # hiRes 이미지
        image_pattern = r'"hiRes":"(https://[^"]+)"'
        matches = re.findall(image_pattern, html)
        images.extend(matches)

        # large 이미지 (fallback)
        if not images:
            image_pattern2 = r'"large":"(https://[^"]+)"'
            matches = re.findall(image_pattern2, html)
            images.extend(matches)

        # 중복 제거
        seen = set()
        unique_images = []
        for img in images:
            img = re.sub(r'\._[A-Z]{2}\d+_\.', '.', img)
            if img not in seen and img.startswith('http'):
                seen.add(img)
                unique_images.append(img)

        return unique_images

    def _extract_reviews(self, soup):
        reviews = {}
        rating_elem = soup.select_one('#acrPopover')
        if rating_elem:
            reviews['rating'] = rating_elem.get('title', '')
        review_count = soup.select_one('#acrCustomerReviewText')
        if review_count:
            reviews['count'] = review_count.get_text(strip=True)
        return reviews

    def download_images(self, images, folder):
        """이미지 다운로드"""
        images_folder = os.path.join(folder, 'images')
        if not os.path.exists(images_folder):
            os.makedirs(images_folder)

        downloaded = []
        for i, img_url in enumerate(images[:10]):  # 최대 10장
            try:
                response = self.session.get(img_url, timeout=30)
                response.raise_for_status()

                ext = '.jpg'
                if 'png' in response.headers.get('content-type', ''):
                    ext = '.png'

                filename = f"thumbnail{ext}" if i == 0 else f"image_{i:02d}{ext}"
                filepath = os.path.join(images_folder, filename)

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                downloaded.append(filename)
                time.sleep(0.3)
            except Exception as e:
                print(f"      이미지 {i} 다운로드 실패: {e}")

        return downloaded

    def translate_to_korean(self, product):
        """상품 정보를 한국어로 번역/변환"""

        # 브랜드명 매핑
        brand_map = {
            'MIKIHOUSE': '미키하우스',
            'ミキハウス': '미키하우스',
            'MiKiHOUSE': '미키하우스',
            'HOT BISCUITS': '핫비스킷',
            'ホットビスケッツ': '핫비스킷',
            'MIKIHOUSE HOT BISCUITS': '미키하우스 핫비스킷',
            'Francfranc': '프랑프랑',
            'フランフラン': '프랑프랑',
            'ランドリン': '란드린',
            'LAUNDRIN': '란드린',
            'gelato pique': '젤라토피케',
            'ジェラートピケ': '젤라토피케',
            'Traditional Weatherwear': '트래디셔널 웨더웨어',
        }

        # 상품 종류 매핑
        item_type_map = {
            'Tシャツ': '티셔츠',
            '半袖': '반팔',
            '長袖': '긴팔',
            'ブラウス': '블라우스',
            'パンツ': '팬츠',
            'ロングパンツ': '롱팬츠',
            'ハーフパンツ': '반바지',
            'ショートパンツ': '숏팬츠',
            'ワンピース': '원피스',
            'スカート': '스커트',
            'オーバーオール': '오버올',
            'リュック': '백팩',
            'リュックサック': '백팩',
            'バッグ': '가방',
            'トートバッグ': '토트백',
            '帽子': '모자',
            'ハット': '햇',
            'レインコート': '레인코트',
            'レインブーツ': '레인부츠',
            '傘': '우산',
            'ディフューザー': '디퓨저',
            'ルームフレグランス': '룸프레그런스',
            'エプロン': '앞치마',
            'ルームシューズ': '실내화',
            'ランプ': '램프',
            'クロック': '시계',
        }

        # 색상 매핑
        color_map = {
            'ピンク': '핑크',
            'ホワイト': '화이트',
            '白': '화이트',
            'ブルー': '블루',
            '青': '블루',
            'レッド': '레드',
            '赤': '레드',
            'ネイビー': '네이비',
            '紺': '네이비',
            'グレー': '그레이',
            'グリーン': '그린',
            '緑': '그린',
            'イエロー': '옐로우',
            '黄': '옐로우',
            'ベージュ': '베이지',
            'ブラック': '블랙',
            '黒': '블랙',
            'マルチカラー': '멀티컬러',
            'インディゴブルー': '인디고블루',
        }

        # 특징 매핑
        feature_map = {
            '日本製': '일본제',
            '綿100%': '면 100%',
            '綿 100%': '면 100%',
            'ボーダー': '스트라이프',
            'セーラー': '세일러',
            'うさぎ': '토끼',
            'くま': '곰',
            '刺繍': '자수',
            'ロゴ': '로고',
            '無地': '무지',
            'ストレッチ': '스트레치',
            'UVカット': '자외선차단',
        }

        # 브랜드 추출
        brand_kr = product.get('brand', '')
        for jp, kr in brand_map.items():
            if jp in brand_kr:
                brand_kr = kr
                break

        # 상품 종류 추출
        title = product.get('title', '')
        item_types = []
        for jp, kr in item_type_map.items():
            if jp in title:
                item_types.append(kr)

        # 특징 추출
        features_kr = []
        for jp, kr in feature_map.items():
            if jp in title or any(jp in f for f in product.get('features', [])):
                features_kr.append(kr)

        # 색상 번역
        colors_kr = []
        for color in product.get('options', {}).get('colors', []):
            color_kr = color
            for jp, kr in color_map.items():
                if jp in color:
                    color_kr = kr
                    break
            colors_kr.append(color_kr)

        # 사이즈
        sizes = product.get('options', {}).get('sizes', [])

        return {
            'brand_kr': brand_kr,
            'item_types': item_types,
            'features_kr': features_kr,
            'colors_kr': colors_kr,
            'sizes': sizes,
        }

    def generate_korean_title(self, product, translated):
        """네이버 쇼핑 최적화 한국어 상품명 생성"""

        brand = translated['brand_kr'] or '수입'
        item_type = translated['item_types'][0] if translated['item_types'] else '의류'
        features = ' '.join(translated['features_kr'][:3])

        # 사이즈 범위
        sizes = translated['sizes']
        size_range = f"({sizes[0]}-{sizes[-1]})" if sizes else ""

        # 타겟 (아동/여성/남성)
        target = ""
        title = product.get('title', '')
        if any(x in title for x in ['ベビー', 'キッズ', '子供', '女の子', '男の子']):
            target = "아동"
        elif any(x in title for x in ['レディース', '女性']):
            target = "여성"

        # 상품명 조합
        parts = [f"[{brand}]"]
        if target:
            parts.append(target)
        parts.append(item_type)
        if features:
            parts.append(features)
        if size_range:
            parts.append(size_range)

        korean_title = ' '.join(parts)

        # 길이 제한 (50자)
        if len(korean_title) > 50:
            korean_title = korean_title[:47] + "..."

        return korean_title

    def generate_detail_page(self, product, translated, korean_title):
        """상세페이지용 JSON 생성"""

        # 특징 설명 생성
        features_desc = []
        for f in product.get('features', []):
            # 간단한 번역 적용
            f_kr = f
            for jp, kr in [('日本製', '일본제'), ('綿100%', '면 100%'), ('綿 100%', '면 100%')]:
                f_kr = f_kr.replace(jp, kr)
            features_desc.append(f_kr)

        detail = {
            "상품명_한국어": korean_title,
            "상품명_원본": product.get('title', ''),
            "브랜드": translated['brand_kr'],
            "브랜드_원본": product.get('brand', ''),
            "ASIN": product.get('asin', ''),
            "상품URL": product.get('url', ''),

            "가격정보": product.get('prices', {}),

            "옵션": {
                "색상": translated['colors_kr'],
                "색상_원본": product.get('options', {}).get('colors', []),
                "사이즈": translated['sizes'],
            },

            "상품특징": features_desc,
            "상세설명": product.get('description', ''),

            "리뷰정보": product.get('reviews', {}),

            "이미지수": len(product.get('images', [])),

            "스마트스토어_상세페이지": self._generate_html_content(product, translated, korean_title),
        }

        return detail

    def _generate_html_content(self, product, translated, korean_title):
        """스마트스토어용 HTML 상세페이지 내용"""

        brand = translated['brand_kr']
        features = translated['features_kr']
        colors = translated['colors_kr']
        sizes = translated['sizes']

        html_parts = []

        # 헤더
        html_parts.append(f"<h2>{korean_title}</h2>")

        # 브랜드 소개
        if brand:
            html_parts.append(f"<p><strong>브랜드:</strong> {brand}</p>")

        # 주요 특징
        if features:
            html_parts.append("<h3>주요 특징</h3>")
            html_parts.append("<ul>")
            for f in features:
                html_parts.append(f"<li>{f}</li>")
            html_parts.append("</ul>")

        # 상품 설명
        if product.get('features'):
            html_parts.append("<h3>상품 설명</h3>")
            html_parts.append("<ul>")
            for f in product.get('features', [])[:5]:
                html_parts.append(f"<li>{f}</li>")
            html_parts.append("</ul>")

        # 옵션 정보
        if colors or sizes:
            html_parts.append("<h3>옵션 정보</h3>")
            if colors:
                html_parts.append(f"<p><strong>색상:</strong> {', '.join(colors)}</p>")
            if sizes:
                html_parts.append(f"<p><strong>사이즈:</strong> {', '.join(sizes)}</p>")

        # 원산지
        if any('일본' in f for f in features):
            html_parts.append("<p><strong>원산지:</strong> 일본</p>")

        return '\n'.join(html_parts)

    def sanitize_folder_name(self, name):
        """폴더명으로 사용 가능하게 정리"""
        # 특수문자 제거
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        # 공백 정리
        name = ' '.join(name.split())
        # 길이 제한
        if len(name) > 50:
            name = name[:50]
        return name.strip()

    def process_product(self, url, existing_name=None):
        """단일 상품 처리"""
        asin = self.extract_asin(url)
        if not asin:
            return None, None

        # 페이지 가져오기
        html = self.fetch_page(url)
        if not html:
            return None, None

        # 파싱
        product = self.parse_product(html, url)

        # 번역
        translated = self.translate_to_korean(product)

        # 한국어 상품명 (기존 이름이 있으면 정리해서 사용)
        if existing_name and existing_name.strip():
            korean_title = existing_name.strip()
            # 기존 이름 정리 (기계번역 느낌 제거)
            korean_title = self._refine_korean_title(korean_title, product, translated)
        else:
            korean_title = self.generate_korean_title(product, translated)

        # 폴더 생성
        folder_name = self.sanitize_folder_name(korean_title)
        folder_path = os.path.join(self.output_dir, folder_name)

        # 중복 폴더 처리
        if os.path.exists(folder_path):
            folder_path = f"{folder_path}_{asin[:4]}"

        os.makedirs(folder_path, exist_ok=True)

        # 이미지 다운로드
        if product['images']:
            downloaded = self.download_images(product['images'], folder_path)
            product['downloaded_images'] = downloaded

        # 상세페이지 JSON 생성
        detail_page = self.generate_detail_page(product, translated, korean_title)

        # 저장
        with open(os.path.join(folder_path, 'detail_page.json'), 'w', encoding='utf-8') as f:
            json.dump(detail_page, f, ensure_ascii=False, indent=2)

        with open(os.path.join(folder_path, 'product_data.json'), 'w', encoding='utf-8') as f:
            json.dump(product, f, ensure_ascii=False, indent=2)

        return korean_title, folder_path

    def _refine_korean_title(self, title, product, translated):
        """기존 한국어 상품명 개선"""

        # 불필요한 부분 제거
        title = title.replace('[', '[').replace(']', ']')
        title = re.sub(r'\s+', ' ', title)

        # 브랜드가 없으면 추가
        brand = translated['brand_kr']
        if brand and f'[{brand}]' not in title and brand not in title:
            title = f'[{brand}] {title}'

        # 사이즈 범위 추가
        sizes = translated['sizes']
        if sizes and not any(s in title for s in sizes):
            size_range = f"({sizes[0]}-{sizes[-1]})"
            if size_range not in title:
                title = f"{title} {size_range}"

        return title.strip()


def main():
    # 구글시트에서 파싱한 상품 목록
    products_data = [
        {"name": "[미키하우스] 아동 반팔 티셔츠 세일러카라 토끼자수 일본제", "url": "https://www.amazon.co.jp/dp/B0DSMP9M1Z/"},
        {"name": "[미키하우스 핫비스킷] 아동 반팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0BVYZVCN5/"},
        {"name": "[미키하우스] 아동 백팩 8L 로고", "url": "https://www.amazon.co.jp/dp/B0DQ841XYN/"},
        {"name": "[미키하우스] 심플 로고 반팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0D38R1LHT/"},
        {"name": "[미키하우스 핫비스킷] 아동 긴팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0CVZ2NG9Y/"},
        {"name": "[미키하우스 핫비스킷] 아동 긴팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0DQPF3MTK/"},
        {"name": "[미키하우스] WEB한정 캔버스 토트백 일본제", "url": "https://www.amazon.co.jp/dp/B0FJLNGSYM/"},
        {"name": "[미키하우스] WEB한정 스트레치 롱팬츠", "url": "https://www.amazon.co.jp/dp/B0DJS4QQ65/"},
        {"name": "[미키하우스] WEB한정 5부 반바지", "url": "https://www.amazon.co.jp/dp/B0F327VJHD/"},
        {"name": "[미키하우스] WEB한정 와펜로고 반팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0F31WW882/"},
        {"name": "[미키하우스] WEB한정 스트라이프 원피스 일본제", "url": "https://www.amazon.co.jp/dp/B0GQSY85SG/"},
        {"name": "[미키하우스] WEB한정 스트라이프 반팔 티셔츠", "url": "https://www.amazon.co.jp/dp/B0GQDXPRRD/"},
        {"name": "[미키하우스] 아동 긴팔 티셔츠 원포인트 로고 일본제", "url": "https://www.amazon.co.jp/dp/B0BBLYQ1RQ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CMT4R6PY/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0D8KFWW2Y/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BR3L94Z1/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0FDK83QKZ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DVSMMY3T/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CT5QTP2G/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CQY73CDK/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DSMQBKQ2/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CT5BN8L9/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CT5QK2PQ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DSMK2VWF/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BT4HD2PN/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BYNGP3YD/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DB56H9XF/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0FKMTHXQ5/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0F28RFDG2/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0D48VKX8J/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BSB636F2/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BSN9L7JL/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0D491QDFZ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0B87W9KYQ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BSN7XHH6/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BVQHMCW1/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CT5QB965/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0GGRFL4C2/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0GGQZFV3K/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CRGK7WBY/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CT5L31Y5/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CRGNJC3H/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0D36NRRT5/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CRGXPGXP/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CQ3K8BCR/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0C1RS48Y5/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BR354LVC/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CSCVCHVT/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DVSTN5V3/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BT73RBGS/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BT739318/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CB23RN7V/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CQCCN933/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BVYZ5HZT/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DZ62CQSY/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CWRT6HF9/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CZMG1R5T/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CHQWBS74/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0B247CDVZ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0C5PVNRNM/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BQJ4C84J/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CWRTQD4T/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0F66KCKCP/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0CVL3QR29/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0C9BJ9C2J/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0C9BG3H1P/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B01CCDQV9G/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B00CJRIH7U/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0DDXYG288/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0GC4PZK1F/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0GC4FVH9C/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0GSGTKBWQ/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0FQHYXS4W/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0F36S95LY/"},
        {"name": "", "url": "https://www.amazon.co.jp/dp/B0BZP1MW54/"},
    ]

    scraper = AmazonBatchScraper(output_dir="products")

    print("=" * 60)
    print("Amazon Japan 일괄 스크래핑 시작")
    print(f"총 {len(products_data)}개 상품")
    print("=" * 60)

    results = []

    for i, item in enumerate(products_data, 1):
        url = item['url']
        existing_name = item['name']

        print(f"\n[{i}/{len(products_data)}] 처리 중...")
        print(f"  URL: {url}")

        try:
            korean_title, folder_path = scraper.process_product(url, existing_name)

            if korean_title:
                print(f"  완료: {korean_title}")
                results.append({
                    "success": True,
                    "korean_title": korean_title,
                    "folder": folder_path,
                    "url": url
                })
            else:
                print(f"  실패: 상품 정보를 가져올 수 없음")
                results.append({
                    "success": False,
                    "url": url
                })

            time.sleep(3)  # 요청 간격 (봇 차단 방지)

        except Exception as e:
            print(f"  오류: {e}")
            results.append({
                "success": False,
                "url": url,
                "error": str(e)
            })

    # 결과 저장
    with open("products/scraping_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 요약
    success_count = sum(1 for r in results if r.get('success'))
    print("\n" + "=" * 60)
    print(f"스크래핑 완료: {success_count}/{len(products_data)} 성공")
    print("=" * 60)


if __name__ == "__main__":
    main()

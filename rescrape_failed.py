# -*- coding: utf-8 -*-
"""
실패한 상품 재스크래핑
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
import time
import random
import shutil
import sys

# Windows 콘솔 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

class ReScraper:
    def __init__(self):
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        ]
        self.session.headers.update({
            'Accept-Language': 'ja-JP,ja;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self.session.cookies.set('i18n-prefs', 'JPY', domain='.amazon.co.jp')

    def fetch_and_parse(self, asin):
        """상품 정보 가져오기"""
        url = f"https://www.amazon.co.jp/dp/{asin}/"

        self.session.headers['User-Agent'] = random.choice(self.user_agents)
        time.sleep(random.uniform(2, 4))

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            product = {'asin': asin, 'url': url}

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

            # 옵션
            options = {}
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
            product['options'] = options

            # 설명
            desc_elem = soup.select_one('#productDescription')
            product['description'] = desc_elem.get_text(strip=True) if desc_elem else ""

            # 특징
            features = []
            feature_list = soup.select('#feature-bullets li span.a-list-item')
            for item in feature_list:
                text = item.get_text(strip=True)
                if text and not text.startswith('›'):
                    features.append(text)
            product['features'] = features

            # 이미지
            images = []
            image_pattern = r'"hiRes":"(https://[^"]+)"'
            matches = re.findall(image_pattern, html)
            for img in matches:
                img = re.sub(r'\._[A-Z]{2}\d+_\.', '.', img)
                if img not in images:
                    images.append(img)
            product['images'] = images

            return product, html

        except Exception as e:
            print(f"    오류: {e}")
            return None, None

    def translate_title(self, product):
        """한국어 상품명 생성"""
        title = product.get('title', '')
        brand = product.get('brand', '')

        # 브랜드 매핑
        brand_map = {
            'MIKIHOUSE': '미키하우스', 'ミキハウス': '미키하우스', 'MiKiHOUSE': '미키하우스',
            'HOT BISCUITS': '핫비스킷', 'ホットビスケッツ': '핫비스킷',
            'Francfranc': '프랑프랑', 'フランフラン': '프랑프랑',
            'ランドリン': '란드린', 'LAUNDRIN': '란드린', 'Laundrin': '란드린',
            'gelato pique': '젤라토피케', 'ジェラートピケ': '젤라토피케',
            'Traditional Weatherwear': '트래디셔널 웨더웨어',
        }

        brand_kr = brand
        for jp, kr in brand_map.items():
            if jp.lower() in brand.lower() or jp in brand:
                brand_kr = kr
                break

        # 상품 종류 추출
        item_types = {
            'Tシャツ': '티셔츠', '半袖': '반팔', '長袖': '긴팔',
            'ブラウス': '블라우스', 'パンツ': '팬츠', 'ワンピース': '원피스',
            'スカート': '스커트', 'オーバーオール': '오버올',
            'リュック': '백팩', 'バッグ': '가방', 'トートバッグ': '토트백',
            '帽子': '모자', 'ハット': '햇', 'レインコート': '레인코트',
            'レインブーツ': '레인부츠', '傘': '우산',
            'ディフューザー': '디퓨저', 'ルームフレグランス': '룸프레그런스',
            'ファブリックミスト': '패브릭미스트', 'エプロン': '앞치마',
            'ルームシューズ': '실내화', 'ランプ': '램프', 'クロック': '시계',
        }

        item_type = '의류'
        for jp, kr in item_types.items():
            if jp in title:
                item_type = kr
                break

        # 특징 추출
        features = []
        feature_map = {
            '日本製': '일본제', '綿100%': '면100%', 'ボーダー': '스트라이프',
            'セーラー': '세일러', 'うさぎ': '토끼', 'くま': '곰',
            '刺繍': '자수', 'ロゴ': '로고', '無地': '무지',
        }
        for jp, kr in feature_map.items():
            if jp in title:
                features.append(kr)

        # 타겟
        target = ""
        if any(x in title for x in ['ベビー', 'キッズ', '子供', '女の子', '男の子']):
            target = "아동"
        elif any(x in title for x in ['レディース', '女性']):
            target = "여성"

        # 사이즈 범위
        sizes = product.get('options', {}).get('sizes', [])
        size_range = f"({sizes[0]}-{sizes[-1]})" if sizes else ""

        # 조합
        parts = [f"[{brand_kr}]"]
        if target:
            parts.append(target)
        parts.append(item_type)
        if features:
            parts.append(' '.join(features[:2]))
        if size_range:
            parts.append(size_range)

        return ' '.join(parts)

    def download_images(self, images, folder):
        """이미지 다운로드"""
        images_folder = os.path.join(folder, 'images')
        os.makedirs(images_folder, exist_ok=True)

        for i, img_url in enumerate(images[:10]):
            try:
                response = self.session.get(img_url, timeout=30)
                response.raise_for_status()
                filename = "thumbnail.jpg" if i == 0 else f"image_{i:02d}.jpg"
                with open(os.path.join(images_folder, filename), 'wb') as f:
                    f.write(response.content)
                time.sleep(0.5)
            except:
                pass

    def generate_detail_json(self, product, korean_title):
        """상세페이지 JSON 생성"""
        # 색상 번역
        color_map = {
            'ピンク': '핑크', 'ホワイト': '화이트', 'ブルー': '블루',
            'レッド': '레드', 'ネイビー': '네이비', 'グレー': '그레이',
            'グリーン': '그린', 'イエロー': '옐로우', 'ベージュ': '베이지',
            'ブラック': '블랙', 'マルチカラー': '멀티컬러',
        }

        colors_orig = product.get('options', {}).get('colors', [])
        colors_kr = []
        for c in colors_orig:
            c_kr = c
            for jp, kr in color_map.items():
                if jp in c:
                    c_kr = kr
                    break
            colors_kr.append(c_kr)

        return {
            "상품명_한국어": korean_title,
            "상품명_원본": product.get('title', ''),
            "브랜드": korean_title.split(']')[0].replace('[', '') if ']' in korean_title else '',
            "브랜드_원본": product.get('brand', ''),
            "ASIN": product.get('asin', ''),
            "상품URL": product.get('url', ''),
            "옵션": {
                "색상": colors_kr,
                "색상_원본": colors_orig,
                "사이즈": product.get('options', {}).get('sizes', []),
            },
            "상품특징": product.get('features', []),
            "상세설명": product.get('description', ''),
            "이미지수": len(product.get('images', [])),
        }


def main():
    # 남은 상품 ASIN 목록 (이미 처리된 것 제외)
    failed_items = [
        ("B0F36S95LY", "[수입] 의류_B0F3"),
        ("B0GC4FVH9C", "[수입] 원피스 (Free Size-Free Size)"),
    ]

    scraper = ReScraper()
    products_dir = "D:\\commerce\\products"

    print("=" * 60)
    print("실패한 상품 재스크래핑")
    print(f"총 {len(failed_items)}개")
    print("=" * 60)

    for i, (asin, old_folder) in enumerate(failed_items, 1):
        print(f"\n[{i}/{len(failed_items)}] {asin} 처리 중...")

        product, html = scraper.fetch_and_parse(asin)

        if product and product.get('title'):
            korean_title = scraper.translate_title(product)
            print(f"    상품명: {korean_title}")

            # 새 폴더명
            new_folder_name = korean_title.replace('/', '-').replace('\\', '-').replace(':', '-')
            new_folder_name = new_folder_name[:50]  # 길이 제한
            new_folder = os.path.join(products_dir, new_folder_name)

            # 기존 폴더 삭제
            old_folder_path = os.path.join(products_dir, old_folder)
            if os.path.exists(old_folder_path):
                shutil.rmtree(old_folder_path)

            # 새 폴더 생성
            os.makedirs(new_folder, exist_ok=True)

            # 이미지 다운로드
            if product.get('images'):
                scraper.download_images(product['images'], new_folder)
                print(f"    이미지: {len(product['images'])}개 다운로드")

            # JSON 저장
            detail = scraper.generate_detail_json(product, korean_title)
            with open(os.path.join(new_folder, 'detail_page.json'), 'w', encoding='utf-8') as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)

            with open(os.path.join(new_folder, 'product_data.json'), 'w', encoding='utf-8') as f:
                json.dump(product, f, ensure_ascii=False, indent=2)

            print(f"    완료: {new_folder_name}")
        else:
            print(f"    실패: 상품 정보를 가져올 수 없음")

    print("\n" + "=" * 60)
    print("재스크래핑 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()

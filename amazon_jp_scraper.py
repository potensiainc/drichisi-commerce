r"""
Amazon Japan Product Scraper
=============================
Amazon.co.jp 상품 페이지에서 모든 정보를 추출하고 이미지를 다운로드합니다.

사용법:
    python amazon_jp_scraper.py <amazon_url>
    python amazon_jp_scraper.py  (대화형 입력)

출력:
    d:\commerce\amazon_products\<ASIN>\
        ├── product_info.json      # 전체 상품 정보
        ├── product_info_kr.txt    # 한국어 요약
        ├── images\
        │   ├── main_1.jpg
        │   ├── main_2.jpg
        │   ├── variant_<color>_1.jpg
        │   └── ...
        └── variants\
            └── variant_details.json
"""

import sys
import os
import io
import json
import re
import time
import hashlib
import urllib.parse
from datetime import datetime
from pathlib import Path

# Windows 콘솔 인코딩 문제 해결 (이모지 출력용)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================================
# 설정
# ============================================================
BASE_OUTPUT_DIR = Path(r"d:\commerce\products")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 1.5  # seconds between requests


# ============================================================
# 유틸리티 함수
# ============================================================

def clean_url(url: str) -> str:
    """URL에서 트래킹 파라미터 제거, ASIN 기반 URL로 정규화"""
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        asin = match.group(1)
        return f"https://www.amazon.co.jp/dp/{asin}"
    return url


def extract_asin(url: str) -> str:
    """URL에서 ASIN 추출"""
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return match.group(1)
    match = re.search(r'/gp/product/([A-Z0-9]{10})', url)
    if match:
        return match.group(1)
    return None


def download_image(url: str, save_path: Path) -> bool:
    """이미지 다운로드"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 500:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(resp.content)
            print(f"  ✅ 다운로드: {save_path.name} ({len(resp.content)//1024}KB)")
            return True
        else:
            print(f"  ❌ 실패 (status={resp.status_code}, size={len(resp.content)})")
            return False
    except Exception as e:
        print(f"  ❌ 에러: {e}")
        return False


def upgrade_image_url(url: str, size: int = 1500) -> str:
    """Amazon 이미지 URL을 고해상도로 변환"""
    if not url:
        return url
    # _SX/SY/SL 등의 크기 지정자를 큰 사이즈로 교체
    url = re.sub(r'\._[A-Z]{2}\d+_', f'._SL{size}_', url)
    # _AC_SX/SY 패턴
    url = re.sub(r'\._AC_S[XYL]\d+_', f'._AC_SL{size}_', url)
    # 사이즈 지정이 없는 경우 추가
    if f'SL{size}' not in url and '._' not in url.split('/')[-1]:
        url = url.replace('.jpg', f'._AC_SL{size}_.jpg')
        url = url.replace('.png', f'._AC_SL{size}_.png')
    return url


def safe_filename(name: str) -> str:
    """파일명으로 사용 가능하도록 정리"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:100]


# ============================================================
# 메인 스크래퍼 클래스
# ============================================================

class AmazonJPScraper:
    def __init__(self):
        self.product_data = {}
        self.variant_data = []
        self.images = []

    def scrape(self, url: str) -> dict:
        """메인 스크래핑 함수"""
        asin = extract_asin(url)
        if not asin:
            print("❌ 유효한 Amazon URL이 아닙니다.")
            return None

        clean = clean_url(url)
        print(f"\n{'='*60}")
        print(f"🔍 Amazon Japan 상품 스크래핑 시작")
        print(f"   ASIN: {asin}")
        print(f"   URL:  {clean}")
        print(f"{'='*60}\n")

        # 임시로 ASIN 폴더 사용 (나중에 한국어 상품명으로 이동)
        temp_output_dir = BASE_OUTPUT_DIR / f"_temp_{asin}"
        temp_output_dir.mkdir(parents=True, exist_ok=True)
        images_dir = temp_output_dir / "images"
        images_dir.mkdir(exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--lang=ja-JP",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="ja-JP",
                user_agent=HEADERS["User-Agent"],
            )
            page = context.new_page()

            # 🇯🇵 페이지 로드 전에 통화/로케일 쿠키 사전 설정
            context.add_cookies([
                {"name": "i18n-prefs", "value": "JPY", "domain": ".amazon.co.jp", "path": "/"},
                {"name": "lc-acbjp", "value": "ja_JP", "domain": ".amazon.co.jp", "path": "/"},
                {"name": "sp-cdn", "value": '"L5Z9:JP"', "domain": ".amazon.co.jp", "path": "/"},
            ])
            print("   통화 쿠키 사전 설정 완료 (i18n-prefs=JPY)")

            try:
                # === 1단계: 메인 페이지 로드 ===
                print("📄 1단계: 메인 페이지 로드 중...")
                page.goto(clean, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # 팝업/쿠키 배너 닫기
                self._dismiss_popups(page)

                # === 1.5단계: JPY 가격 확인 (필요시 재설정) ===
                print("🗾 1.5단계: 일본 배송지(우편번호) 설정 중...")
                self._set_japan_locale(page, clean)

                # === 2단계: 기본 정보 추출 ===
                print("📋 2단계: 기본 정보 추출 중...")
                self._extract_basic_info(page, asin)

                # === 3단계: 이미지 추출 ===
                print("🖼️  3단계: 이미지 URL 추출 중...")
                self._extract_images(page)

                # === 4단계: 옵션/변형 추출 ===
                print("🎨 4단계: 옵션(컬러/사이즈) 추출 중...")
                self._extract_variants(page)

                # === 5단계: 상세 스펙 추출 ===
                print("📊 5단계: 상세 스펙 추출 중...")
                self._extract_specs(page)

                # === 6단계: 각 변형별 이미지 수집 ===
                print("🔄 6단계: 각 컬러 변형별 이미지 수집 중...")
                self._collect_variant_images(page)

                # === 7단계: 상세 설명 추출 ===
                print("📝 7단계: 상세 설명 추출 중...")
                self._extract_description(page)

            except PlaywrightTimeout as e:
                print(f"⚠️ 타임아웃 발생: {e}")
            except Exception as e:
                print(f"❌ 에러 발생: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()

        # === 8단계: 상품명 한국어 번역 및 폴더 생성 ===
        print("\n🌐 8단계: 상품명 한국어 번역 중...")
        jp_title = self.product_data.get("title", asin)
        kr_title = self._translate_title_to_korean(jp_title)
        kr_folder_name = safe_filename(kr_title)

        # 최종 출력 폴더 설정
        output_dir = BASE_OUTPUT_DIR / kr_folder_name
        if output_dir.exists():
            # 이미 존재하면 ASIN 추가
            output_dir = BASE_OUTPUT_DIR / f"{kr_folder_name}_{asin}"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_images_dir = output_dir / "images"
        final_images_dir.mkdir(exist_ok=True)

        print(f"   일본어: {jp_title[:50]}...")
        print(f"   한국어: {kr_title[:50]}...")
        print(f"   폴더명: {kr_folder_name[:50]}...")

        # === 9단계: 이미지 다운로드 ===
        print(f"\n📥 9단계: 이미지 다운로드 ({len(self.images)}개)...")
        self._download_all_images(final_images_dir)

        # === 10단계: 결과 저장 ===
        print("\n💾 10단계: 결과 저장 중...")
        result = self._compile_result()
        result["title_kr"] = kr_title  # 한국어 상품명 추가
        result["folder_name"] = kr_folder_name
        self._save_results(output_dir, result)

        # 임시 폴더 삭제
        import shutil
        if temp_output_dir.exists():
            try:
                shutil.rmtree(temp_output_dir)
            except:
                pass

        print(f"\n{'='*60}")
        print(f"✅ 스크래핑 완료!")
        print(f"   저장 위치: {output_dir}")
        print(f"   상품명(JP): {result.get('title', 'N/A')[:40]}...")
        print(f"   상품명(KR): {kr_title[:40]}...")
        print(f"   가격: {result.get('price', 'N/A')}")
        print(f"   컬러 옵션: {len(result.get('color_options', []))}개")
        print(f"   사이즈 옵션: {len(result.get('size_options', []))}개")
        print(f"   이미지: {len(self.images)}개 다운로드")
        print(f"{'='*60}\n")

        return result

    def _translate_title_to_korean(self, jp_title: str) -> str:
        """일본어 상품명을 한국어로 번역 (간단한 매핑 + Google Translate API fallback)"""
        # 기본 일본어 -> 한국어 매핑 (의류 관련)
        translation_map = {
            # 브랜드
            "ミキハウス": "미키하우스",
            "MIKIHOUSE": "미키하우스",

            # 의류 종류
            "Ｔシャツ": "티셔츠",
            "Tシャツ": "티셔츠",
            "半袖": "반팔",
            "長袖": "긴팔",
            "ボーダー": "스트라이프",
            "ロゴ": "로고",
            "シャツ": "셔츠",
            "パンツ": "팬츠",
            "スカート": "스커트",
            "ワンピース": "원피스",
            "ジャケット": "자켓",
            "コート": "코트",
            "セーター": "스웨터",
            "カーディガン": "가디건",
            "パーカー": "후드",
            "トレーナー": "맨투맨",
            "ベスト": "조끼",
            "ブラウス": "블라우스",
            "ポロシャツ": "폴로셔츠",

            # 대상
            "男の子": "남아",
            "女の子": "여아",
            "ベビー": "베이비",
            "キッズ": "키즈",
            "子供服": "아동복",
            "子供": "아동",
            "赤ちゃん": "아기",

            # 용도/상황
            "通園": "통원",
            "通学": "통학",
            "フォーマル": "포멀",
            "カジュアル": "캐주얼",
            "普段着": "평상복",

            # 특징
            "WEB限定": "WEB한정",
            "限定": "한정",
            "新作": "신상",
            "人気": "인기",
            "おしゃれ": "세련된",
            "かわいい": "귀여운",
            "シンプル": "심플",

            # 색상
            "ブラック": "블랙",
            "ホワイト": "화이트",
            "グレー": "그레이",
            "レッド": "레드",
            "ブルー": "블루",
            "ネイビー": "네이비",
            "ピンク": "핑크",
            "イエロー": "옐로우",
            "グリーン": "그린",
            "オレンジ": "오렌지",
            "パープル": "퍼플",
            "ベージュ": "베이지",
            "マルチカラー": "멀티컬러",
            "赤": "레드",
            "紺": "네이비",
            "白": "화이트",
            "黒": "블랙",

            # 소재
            "綿": "면",
            "コットン": "코튼",
            "ポリエステル": "폴리에스터",
            "ナイロン": "나일론",
            "リネン": "린넨",
            "シルク": "실크",
            "ウール": "울",

            # 기타
            "セット": "세트",
            "枚": "장",
            "個": "개",
        }

        result = jp_title

        # 매핑 적용
        for jp, kr in translation_map.items():
            result = result.replace(jp, kr)

        # 숫자-숫자 형식 (사이즈 범위) 유지
        # 예: 10-5262-147 -> 그대로 유지

        # 괄호 안의 사이즈 유지
        # 예: (80-150) -> 그대로 유지

        return result

    def _dismiss_popups(self, page):
        """팝업, 쿠키 배너 등 닫기"""
        try:
            # 쿠키 동의
            for sel in ["#sp-cc-accept", "#a-autoid-0-announce", ".a-button-close"]:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(500)
        except:
            pass

    def _set_japan_locale(self, page, product_url: str):
        """일본 쿠키를 설정하여 JPY 가격 표시 강제 (페이지 리로드 포함)"""
        try:
            # Amazon은 i18n-prefs 쿠키로 통화를 결정함
            # JPY = 일본 엔화 표시
            cookies_to_set = [
                {
                    "name": "i18n-prefs",
                    "value": "JPY",
                    "domain": ".amazon.co.jp",
                    "path": "/",
                },
                {
                    "name": "lc-acbjp",
                    "value": "ja_JP",
                    "domain": ".amazon.co.jp",
                    "path": "/",
                },
                {
                    "name": "sp-cdn",
                    "value": '"L5Z9:JP"',
                    "domain": ".amazon.co.jp",
                    "path": "/",
                },
            ]
            page.context.add_cookies(cookies_to_set)
            print("   쿠키 설정 완료 (i18n-prefs=JPY, lc-acbjp=ja_JP)")

            # 페이지 리로드하여 JPY 가격 반영
            print("   페이지 새로고침 중...")
            page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            self._dismiss_popups(page)

            # 가격 확인
            price_el = page.query_selector(".a-price .a-offscreen")
            if price_el:
                price_text = price_el.inner_text().strip()
                if "￥" in price_text or "¥" in price_text:
                    print(f"   ✅ JPY 가격 확인: {price_text}")
                else:
                    print(f"   ⚠️ 아직 다른 통화: {price_text}, 배송지 팝업으로 재시도...")
                    self._set_japan_locale_via_popup(page, product_url)

        except Exception as e:
            print(f"   ⚠️ 배송지 설정 실패 (무시하고 계속): {e}")

    def _set_japan_locale_via_popup(self, page, product_url: str):
        """쿠키 실패 시 배송지 팝업을 통해 일본 설정"""
        try:
            deliver_to = page.query_selector("#glow-ingress-block, #nav-global-location-popover-link")
            if deliver_to:
                deliver_to.click()
                page.wait_for_timeout(2000)

                # 우편번호 입력
                zip_input = page.query_selector("#GLUXZipUpdateInput")
                if zip_input:
                    zip_input.fill("")
                    zip_input.type("1500001", delay=100)  # ハイフンなし
                    page.wait_for_timeout(500)

                    # 적용 버튼 - JavaScript로 직접 클릭
                    page.evaluate("""
                        () => {
                            const btn = document.querySelector('#GLUXZipUpdate input[type="submit"], #GLUXZipUpdate .a-button-input');
                            if (btn) btn.click();
                        }
                    """)
                    page.wait_for_timeout(2000)

                    # 완료 버튼
                    page.evaluate("""
                        () => {
                            const btn = document.querySelector('#GLUXConfirmClose, .a-popover-footer .a-button-input');
                            if (btn) btn.click();
                        }
                    """)
                    page.wait_for_timeout(1000)

                    # 리로드
                    page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    self._dismiss_popups(page)
                    print("   배송지 팝업으로 일본 설정 완료")
                    return

                # 국가 선택 드롭다운
                country_dropdown = page.query_selector("#GLUXCountryListDropdown")
                if country_dropdown:
                    page.evaluate("""
                        () => {
                            const dd = document.querySelector('#GLUXCountryListDropdown');
                            if (dd) dd.click();
                        }
                    """)
                    page.wait_for_timeout(500)
                    japan_option = page.query_selector("a[data-value='JP']")
                    if japan_option:
                        japan_option.click()
                        page.wait_for_timeout(1000)
                    page.evaluate("""
                        () => {
                            const btn = document.querySelector('#GLUXConfirmClose, .a-popover-footer .a-button-input');
                            if (btn) btn.click();
                        }
                    """)
                    page.wait_for_timeout(1000)
                    page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    self._dismiss_popups(page)

        except Exception as e:
            print(f"   ⚠️ 팝업 방식도 실패: {e}")

    def _extract_basic_info(self, page, asin: str):
        """기본 상품 정보 추출"""
        self.product_data["asin"] = asin
        self.product_data["url"] = f"https://www.amazon.co.jp/dp/{asin}"
        self.product_data["scraped_at"] = datetime.now().isoformat()

        # 상품명
        title_el = page.query_selector("#productTitle")
        if title_el:
            self.product_data["title"] = title_el.inner_text().strip()
            print(f"   상품명: {self.product_data['title'][:60]}...")

        # 브랜드
        brand_el = page.query_selector("#bylineInfo") or page.query_selector(".po-brand .a-span9 .a-size-base")
        if brand_el:
            self.product_data["brand"] = brand_el.inner_text().strip().replace("ブランド: ", "").replace("のストアを表示", "").strip()

        # 가격
        price_el = page.query_selector(".a-price .a-offscreen") or page.query_selector("#priceblock_ourprice") or page.query_selector(".a-price-whole")
        if price_el:
            self.product_data["price"] = price_el.inner_text().strip()
            print(f"   가격: {self.product_data['price']}")

        # 할인 가격
        old_price_el = page.query_selector(".basisPrice .a-offscreen")
        if old_price_el:
            self.product_data["original_price"] = old_price_el.inner_text().strip()

        discount_el = page.query_selector(".savingsPercentage")
        if discount_el:
            self.product_data["discount"] = discount_el.inner_text().strip()

        # 평점
        rating_el = page.query_selector("#acrPopover .a-icon-alt") or page.query_selector("span[data-action='acrStars498-popover'] .a-icon-alt")
        if rating_el:
            self.product_data["rating"] = rating_el.inner_text().strip()

        review_el = page.query_selector("#acrCustomerReviewText")
        if review_el:
            self.product_data["review_count"] = review_el.inner_text().strip()

        # 카테고리 (breadcrumb)
        breadcrumb_els = page.query_selector_all("#wayfinding-breadcrumbs_container a")
        if breadcrumb_els:
            self.product_data["category"] = [el.inner_text().strip() for el in breadcrumb_els if el.inner_text().strip()]

        # 판매자
        seller_el = page.query_selector("#sellerProfileTriggerId") or page.query_selector("#merchant-info a")
        if seller_el:
            self.product_data["seller"] = seller_el.inner_text().strip()

        # 배송 정보
        delivery_el = page.query_selector("#deliveryMessageMirId .a-text-bold")
        if delivery_el:
            self.product_data["delivery"] = delivery_el.inner_text().strip()

        # 재고 상태
        avail_el = page.query_selector("#availability span")
        if avail_el:
            self.product_data["availability"] = avail_el.inner_text().strip()

        # 특징 bullet points
        bullets = page.query_selector_all("#feature-bullets li span.a-list-item")
        if bullets:
            self.product_data["features"] = [b.inner_text().strip() for b in bullets if b.inner_text().strip() and "この商品について" not in b.inner_text()]

    def _extract_images(self, page):
        """모든 이미지 URL 추출"""
        image_urls = set()

        # 방법 1: altImages 섹션의 썸네일에서 고해상도 URL 추출
        thumbs = page.query_selector_all("#altImages .a-button-thumbnail img, #altImages li img")
        for thumb in thumbs:
            src = thumb.get_attribute("src") or ""
            if "media-amazon.com/images" in src:
                hi_res = upgrade_image_url(src, 1500)
                image_urls.add(hi_res)

        # 방법 2: JavaScript로 이미지 데이터 추출 (Amazon의 내부 데이터)
        try:
            js_images = page.evaluate("""
                () => {
                    const images = [];
                    // colorImages 변수에서 추출
                    if (typeof colorImages !== 'undefined') {
                        for (const key in colorImages) {
                            if (colorImages[key]) {
                                colorImages[key].forEach(img => {
                                    if (img.hiRes) images.push(img.hiRes);
                                    else if (img.large) images.push(img.large);
                                });
                            }
                        }
                    }
                    // ImageBlockATF 데이터에서 추출
                    const scripts = document.querySelectorAll('script[type="text/javascript"]');
                    for (const script of scripts) {
                        const text = script.textContent;
                        if (text.includes('colorImages')) {
                            const match = text.match(/colorImages['"]?\\s*[:=]\\s*({[^;]+})/);
                            if (match) {
                                try {
                                    const data = JSON.parse(match[1].replace(/'/g, '"'));
                                    for (const key in data) {
                                        if (Array.isArray(data[key])) {
                                            data[key].forEach(img => {
                                                if (img.hiRes) images.push(img.hiRes);
                                                else if (img.large) images.push(img.large);
                                            });
                                        }
                                    }
                                } catch(e) {}
                            }
                        }
                        // 'data' 형식
                        if (text.includes('"colorImages"')) {
                            const matches = text.matchAll(/"hiRes"\\s*:\\s*"([^"]+)"/g);
                            for (const m of matches) {
                                images.push(m[1]);
                            }
                        }
                    }
                    return images;
                }
            """)
            for url in js_images:
                if url and "media-amazon.com" in url:
                    image_urls.add(url)
        except Exception as e:
            print(f"   ⚠️ JS 이미지 추출 실패: {e}")

        # 방법 3: 메인 이미지
        main_img = page.query_selector("#landingImage") or page.query_selector("#imgBlkFront")
        if main_img:
            src = main_img.get_attribute("data-old-hires") or main_img.get_attribute("src") or ""
            if "media-amazon.com" in src:
                image_urls.add(upgrade_image_url(src, 1500))

        # 방법 4: HTML 소스에서 직접 regex로 추출
        try:
            html_content = page.content()
            hi_res_matches = re.findall(r'"hiRes"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html_content)
            for url in hi_res_matches:
                image_urls.add(url)
            large_matches = re.findall(r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html_content)
            for url in large_matches:
                image_urls.add(upgrade_image_url(url, 1500))
        except:
            pass

        self.images = list(image_urls)
        self.product_data["image_count"] = len(self.images)
        print(f"   발견한 이미지: {len(self.images)}개")
        for i, url in enumerate(self.images):
            print(f"   [{i+1}] {url[:80]}...")

    def _extract_variants(self, page):
        """컬러/사이즈 등 모든 변형 추출"""
        # --- 컬러 옵션 ---
        color_options = []

        # 방법 1: twister 내의 이미지 스와치
        color_swatches = page.query_selector_all("#variation_color_name li, #tp-inline-twister-dim-values-container li")
        if not color_swatches:
            color_swatches = page.query_selector_all("[data-csa-c-dimension-name='color_name'] li")

        for swatch in color_swatches:
            color_info = {}
            # 색상명
            title = swatch.get_attribute("title") or ""
            title = title.replace("クリックして選択 ", "").strip()
            if not title:
                img = swatch.query_selector("img")
                if img:
                    title = img.get_attribute("alt") or ""
            color_info["name"] = title

            # ASIN
            asin_attr = swatch.get_attribute("data-defaultasin") or ""
            if not asin_attr:
                dp_url = swatch.get_attribute("data-dp-url") or ""
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', dp_url)
                if asin_match:
                    asin_attr = asin_match.group(1)
            color_info["asin"] = asin_attr

            # 선택 상태
            classes = swatch.get_attribute("class") or ""
            color_info["selected"] = "swatchSelect" in classes or "selected" in classes

            # 썸네일 이미지
            img = swatch.query_selector("img")
            if img:
                thumb = img.get_attribute("src") or ""
                color_info["thumbnail"] = thumb
                color_info["image"] = upgrade_image_url(thumb, 1500)

            if color_info.get("name"):
                color_options.append(color_info)

        # 방법 2: 드롭다운 방식
        if not color_options:
            color_dropdown = page.query_selector("#native_dropdown_selected_color_name")
            if color_dropdown:
                options = color_dropdown.query_selector_all("option")
                for opt in options:
                    val = opt.get_attribute("value") or ""
                    text = opt.inner_text().strip()
                    if val and text and val != "0":
                        asin_match = re.search(r',([A-Z0-9]{10}),', val)
                        color_options.append({
                            "name": text,
                            "asin": asin_match.group(1) if asin_match else "",
                        })

        # 방법 3: inline twister 버튼
        if not color_options:
            twister_buttons = page.query_selector_all('[id*="color_name"] .a-button-text')
            for btn in twister_buttons:
                text = btn.inner_text().strip()
                if text:
                    color_options.append({"name": text})

        self.product_data["color_options"] = color_options
        print(f"   컬러 옵션: {len(color_options)}개")
        for c in color_options:
            marker = " ★" if c.get("selected") else ""
            print(f"     - {c.get('name', '?')}{marker} (ASIN: {c.get('asin', 'N/A')})")

        # --- 사이즈 옵션 ---
        size_options = []

        # 방법 1: twister 내의 사이즈 버튼
        size_buttons = page.query_selector_all("#variation_size_name li, [data-csa-c-dimension-name='size_name'] li")
        for btn in size_buttons:
            size_info = {}
            # 사이즈명
            text_el = btn.query_selector(".a-size-base") or btn.query_selector("span")
            if text_el:
                size_info["name"] = text_el.inner_text().strip()

            # ASIN
            asin_attr = btn.get_attribute("data-defaultasin") or ""
            if not asin_attr:
                dp_url = btn.get_attribute("data-dp-url") or ""
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', dp_url)
                if asin_match:
                    asin_attr = asin_match.group(1)
            size_info["asin"] = asin_attr

            # 선택 상태
            classes = btn.get_attribute("class") or ""
            size_info["selected"] = "swatchSelect" in classes or "selected" in classes

            # 재고 상태
            size_info["available"] = "swatchAvailable" in classes or "unavailable" not in classes.lower()

            if size_info.get("name"):
                size_options.append(size_info)

        # 방법 2: 드롭다운 방식
        if not size_options:
            size_dropdown = page.query_selector("#native_dropdown_selected_size_name")
            if size_dropdown:
                options = size_dropdown.query_selector_all("option")
                for opt in options:
                    val = opt.get_attribute("value") or ""
                    text = opt.inner_text().strip()
                    if val and text and val != "0":
                        asin_match = re.search(r',([A-Z0-9]{10}),', val)
                        size_options.append({
                            "name": text,
                            "asin": asin_match.group(1) if asin_match else "",
                            "available": "不可" not in text,
                        })

        # 방법 3: inline twister 버튼 (tp-inline)
        if not size_options:
            inline_size_btns = page.query_selector_all('[id*="size_name"] .a-button-text, .tp-inline-twister-dim-values-container button')
            for btn in inline_size_btns:
                text = btn.inner_text().strip()
                if text:
                    size_options.append({"name": text, "available": True})

        self.product_data["size_options"] = size_options
        print(f"   사이즈 옵션: {len(size_options)}개")
        for s in size_options:
            marker = " ★" if s.get("selected") else ""
            avail = "" if s.get("available", True) else " [품절]"
            print(f"     - {s.get('name', '?')}{marker}{avail} (ASIN: {s.get('asin', 'N/A')})")

        # --- 사이즈별 x 컬러별 매트릭스 ---
        # variant matrix (JavaScript에서 추출)
        try:
            variant_matrix = page.evaluate("""
                () => {
                    const matrix = [];
                    // twister 데이터 추출
                    const scripts = document.querySelectorAll('script');
                    for (const script of scripts) {
                        const text = script.textContent;
                        if (text.includes('dimensionValuesDisplayData')) {
                            const match = text.match(/dimensionValuesDisplayData\\s*[:=]\\s*({[^}]+})/);
                            if (match) {
                                try {
                                    return JSON.parse(match[1]);
                                } catch(e) {}
                            }
                        }
                    }
                    return null;
                }
            """)
            if variant_matrix:
                self.product_data["variant_matrix"] = variant_matrix
                print(f"   변형 매트릭스: {len(variant_matrix)}개 조합")
        except:
            pass

        # --- 가격 매트릭스 추출 (사이즈별 가격 차이) ---
        try:
            price_matrix = page.evaluate("""
                () => {
                    const prices = {};
                    const scripts = document.querySelectorAll('script');
                    for (const script of scripts) {
                        const text = script.textContent;
                        // asinPriceJSON 추출
                        if (text.includes('asinVariationValues') || text.includes('dimensionToAsinMap')) {
                            const dimMatch = text.match(/dimensionToAsinMap\\s*[:=]\\s*({[^;]+})/);
                            if (dimMatch) {
                                try {
                                    return JSON.parse(dimMatch[1]);
                                } catch(e) {}
                            }
                        }
                    }
                    return null;
                }
            """)
            if price_matrix:
                self.product_data["dimension_to_asin_map"] = price_matrix
                print(f"   사이즈-컬러 ASIN 매핑: {len(price_matrix)}개")
        except:
            pass

    def _extract_specs(self, page):
        """상세 스펙 추출"""
        specs = {}

        # 방법 1: productDetails 테이블
        detail_rows = page.query_selector_all("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr")
        for row in detail_rows:
            th = row.query_selector("th")
            td = row.query_selector("td")
            if th and td:
                key = th.inner_text().strip()
                val = td.inner_text().strip()
                if key and val:
                    specs[key] = val

        # 방법 2: detailBullets
        bullets = page.query_selector_all("#detailBullets_feature_div li span.a-list-item")
        for bullet in bullets:
            spans = bullet.query_selector_all("span")
            if len(spans) >= 2:
                key = spans[0].inner_text().strip().rstrip(":")
                val = spans[1].inner_text().strip()
                if key and val and "‎" not in key:
                    specs[key] = val

        # 방법 3: 追加情報 (Additional Info) 테이블
        add_info_rows = page.query_selector_all("#productDetails_db_sections tr, .product-facts-detail")
        for row in add_info_rows:
            th = row.query_selector("th, .product-facts-title")
            td = row.query_selector("td, .product-facts-detail")
            if th and td:
                key = th.inner_text().strip()
                val = td.inner_text().strip()
                if key and val:
                    specs[key] = val

        # 방법 4: po-break 방식 (Overview 섹션)
        overview_rows = page.query_selector_all("#poExpander .a-spacing-small")
        for row in overview_rows:
            label = row.query_selector(".po-break-word .a-color-secondary")
            value = row.query_selector(".po-break-word .a-span9 span")
            if label and value:
                specs[label.inner_text().strip()] = value.inner_text().strip()

        self.product_data["specs"] = specs
        print(f"   스펙 항목: {len(specs)}개")
        for k, v in specs.items():
            print(f"     - {k}: {v[:50]}")

    def _collect_variant_images(self, page):
        """각 컬러 변형을 클릭하고, 각 컬러의 모든 썸네일을 클릭하여 전체 이미지 수집"""
        color_options = self.product_data.get("color_options", [])

        variant_images = {}

        # 컬러 옵션이 없거나 1개인 경우에도 현재 선택된 컬러의 모든 이미지 수집
        if len(color_options) == 0:
            print("   컬러 옵션 없음 - 현재 페이지의 모든 썸네일 이미지 수집...")
            all_images = self._collect_all_thumbnail_images(page)
            variant_images["default"] = all_images
            self.product_data["variant_images"] = variant_images
            return

        for i, color in enumerate(color_options):
            color_name = color.get("name", f"color_{i}")
            print(f"   🎨 [{i+1}/{len(color_options)}] {color_name} 컬러 처리 중...")

            try:
                # 이미 선택된 컬러인 경우 바로 이미지 수집
                if color.get("selected"):
                    print(f"     (현재 선택된 컬러)")
                    color_images = self._collect_all_thumbnail_images(page)
                    variant_images[color_name] = color_images
                    for url in color_images:
                        if url not in self.images:
                            self.images.append(url)
                    print(f"     ✅ {color_name}: {len(color_images)}개 이미지 수집 완료")
                    continue

                # 선택되지 않은 컬러는 클릭 후 수집
                if not color.get("selected"):
                    # 컬러 스와치 클릭 - 다양한 셀렉터 시도
                    swatch_selectors = [
                        # 인라인 트위스터 (tp-inline) - 최신 아마존 UI
                        f'#tp-inline-twister-dim-values-container li:nth-child({i+1})',
                        f'#tp-inline-twister-dim-values-container li:nth-child({i+1}) button',
                        f'#tp-inline-twister-dim-values-container li:nth-child({i+1}) img',
                        # 기존 variation 방식
                        f'#variation_color_name li:nth-child({i+1})',
                        f'#variation_color_name li:nth-child({i+1}) img',
                        f'#variation_color_name li[title*="{color_name}"] img',
                        # data 속성 기반
                        f'[data-csa-c-dimension-name="color_name"] li:nth-child({i+1})',
                        f'[data-csa-c-dimension-name="color_name"] li:nth-child({i+1}) button',
                        # ASIN 기반 (있는 경우)
                        f'#variation_color_name li[data-defaultasin="{color.get("asin", "")}"] img',
                    ]

                    clicked = False
                    for sel in swatch_selectors:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                page.wait_for_timeout(2500)
                                clicked = True
                                print(f"     클릭 성공: {sel}")
                                break
                        except:
                            continue

                    if not clicked:
                        # JavaScript로 직접 클릭 시도
                        try:
                            clicked = page.evaluate(f"""
                                () => {{
                                    const items = document.querySelectorAll('#tp-inline-twister-dim-values-container li, #variation_color_name li');
                                    if (items && items.length > {i}) {{
                                        const el = items[{i}];
                                        const clickable = el.querySelector('button, img, a') || el;
                                        clickable.click();
                                        return true;
                                    }}
                                    return false;
                                }}
                            """)
                            if clicked:
                                page.wait_for_timeout(2500)
                                print(f"     JS 클릭 성공")
                        except Exception as e:
                            print(f"     JS 클릭 실패: {e}")

                    if not clicked:
                        print(f"     ⚠️ 컬러 클릭 실패 - 건너뜀")
                        continue

                # 현재 컬러의 모든 썸네일 이미지 수집
                color_images = self._collect_all_thumbnail_images(page)
                variant_images[color_name] = color_images

                # 전체 이미지 목록에 추가
                for url in color_images:
                    if url not in self.images:
                        self.images.append(url)

                print(f"     ✅ {color_name}: {len(color_images)}개 이미지 수집 완료")
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                print(f"     ❌ 에러: {e}")
                import traceback
                traceback.print_exc()

        self.product_data["variant_images"] = variant_images
        print(f"   📊 총 {len(color_options)}개 컬러에서 {len(self.images)}개 이미지 수집")

    def _collect_all_thumbnail_images(self, page) -> list:
        """현재 페이지의 좌측 썸네일 갤러리에서 모든 이미지를 클릭하여 고해상도 URL 수집"""
        collected_images = []

        # 썸네일 목록 찾기 - 더 정확한 셀렉터 사용
        thumbnail_selectors = [
            "#altImages ul li.a-spacing-small.item",
            "#altImages ul li.imageThumbnail",
            "#altImages .a-button-thumbnail",
            "#altImages li.a-spacing-small",
            "#altImages li[data-csa-c-type='image']",
            ".imageThumbnail",
            "#altImages ul li",
        ]

        thumbnails = []
        for sel in thumbnail_selectors:
            thumbnails = page.query_selector_all(sel)
            # 이미지가 있는 썸네일만 필터링
            if thumbnails:
                valid_thumbs = []
                for t in thumbnails:
                    img = t.query_selector("img")
                    if img:
                        src = img.get_attribute("src") or ""
                        # 실제 상품 이미지인지 확인 (비디오/플레이 아이콘 제외)
                        if "media-amazon.com/images/I/" in src and "play" not in src.lower():
                            valid_thumbs.append(t)
                if valid_thumbs:
                    thumbnails = valid_thumbs
                    break

        if not thumbnails:
            print(f"     썸네일을 찾을 수 없음, HTML에서 직접 추출 시도...")
            return self._extract_images_from_html(page)

        print(f"     발견한 썸네일: {len(thumbnails)}개")

        for idx, thumb in enumerate(thumbnails):
            try:
                # 썸네일이 비디오인지 확인 (비디오는 건너뜀)
                thumb_class = thumb.get_attribute("class") or ""
                if "videoThumbnail" in thumb_class or "video" in thumb_class.lower():
                    print(f"       [{idx+1}] 비디오 썸네일 - 건너뜀")
                    continue

                # 썸네일 내의 img 태그 확인
                thumb_img = thumb.query_selector("img")
                if not thumb_img:
                    print(f"       [{idx+1}] img 태그 없음 - 건너뜀")
                    continue

                thumb_src = thumb_img.get_attribute("src") or ""
                if "play-icon" in thumb_src or "video" in thumb_src.lower():
                    print(f"       [{idx+1}] 비디오 - 건너뜀")
                    continue

                # 썸네일 클릭 (여러 방법 시도)
                click_success = False
                try:
                    # 방법 1: 직접 클릭
                    thumb_img.click()
                    click_success = True
                except:
                    try:
                        # 방법 2: 부모 요소 클릭
                        thumb.click()
                        click_success = True
                    except:
                        try:
                            # 방법 3: JavaScript로 클릭
                            page.evaluate(f"""
                                () => {{
                                    const thumbs = document.querySelectorAll('#altImages ul li img');
                                    if (thumbs[{idx}]) thumbs[{idx}].click();
                                }}
                            """)
                            click_success = True
                        except:
                            pass

                if not click_success:
                    print(f"       [{idx+1}] 클릭 실패 - 건너뜀")
                    continue

                # 이미지 로딩 대기 (충분한 시간)
                page.wait_for_timeout(1500)

                # 고해상도 이미지 URL 추출
                hi_res_url = None

                # 먼저 썸네일 이미지 ID 추출 (클릭한 썸네일과 매칭용)
                thumb_img_id = None
                if thumb_img:
                    thumb_src = thumb_img.get_attribute("src") or ""
                    id_match = re.search(r'/images/I/([^._]+)', thumb_src)
                    if id_match:
                        thumb_img_id = id_match.group(1)

                # 방법 1: JavaScript에서 colorImages 데이터로 해당 인덱스의 이미지 직접 추출
                try:
                    hi_res_url = page.evaluate(f"""
                        () => {{
                            // colorImages 데이터에서 현재 컬러의 이미지 배열 찾기
                            const scripts = document.querySelectorAll('script');
                            for (const script of scripts) {{
                                const text = script.textContent;
                                if (text.includes('colorImages')) {{
                                    // colorImages 객체 전체 추출
                                    const match = text.match(/'colorImages'\\s*:\\s*(\\{{[^}}]+\\}})/);
                                    if (match) {{
                                        try {{
                                            // 현재 컬러의 이미지 배열에서 인덱스로 접근
                                            const allHiRes = [];
                                            const hiResMatches = text.matchAll(/"hiRes"\\s*:\\s*"(https:\\/\\/[^"]+)"/g);
                                            for (const m of hiResMatches) {{
                                                allHiRes.push(m[1]);
                                            }}
                                            // 현재 컬러에 해당하는 이미지 (3개씩 그룹)
                                            // 썸네일 인덱스에 맞는 이미지 반환
                                            if (allHiRes.length > {idx}) {{
                                                return allHiRes[{idx}];
                                            }}
                                        }} catch(e) {{}}
                                    }}
                                }}
                            }}

                            // 대체: 메인 이미지에서 추출
                            const mainImg = document.querySelector('#landingImage');
                            if (mainImg) {{
                                const hiRes = mainImg.getAttribute('data-old-hires');
                                if (hiRes && !hiRes.includes('sprite')) return hiRes;
                                const src = mainImg.src;
                                if (src && src.includes('media-amazon.com')) {{
                                    return src.replace(/\\._[A-Z]{{2}}\\d+_/, '._AC_SL1500_')
                                              .replace(/\\._AC_S[XYL]\\d+_/, '._AC_SL1500_');
                                }}
                            }}
                            return null;
                        }}
                    """)
                except:
                    pass

                # 방법 2: 메인 이미지 영역에서 추출 (클릭 후 변경된 이미지)
                if not hi_res_url:
                    main_img = page.query_selector("#landingImage")
                    if main_img:
                        hi_res_url = main_img.get_attribute("data-old-hires")
                        if not hi_res_url or "sprite" in hi_res_url:
                            hi_res_url = main_img.get_attribute("src")

                # 방법 3: 썸네일 이미지 ID로 직접 고해상도 URL 생성 (가장 확실한 방법)
                if thumb_img_id:
                    # 썸네일 ID에서 고해상도 URL 직접 생성
                    generated_url = f"https://m.media-amazon.com/images/I/{thumb_img_id}._AC_SL1500_.jpg"
                    # 기존 추출된 URL과 비교하여 더 나은 것 선택
                    if not hi_res_url or "sprite" in hi_res_url or thumb_img_id not in (hi_res_url or ""):
                        hi_res_url = generated_url

                # URL 정리 및 고해상도로 변환
                if hi_res_url and "media-amazon.com" in hi_res_url:
                    hi_res_url = upgrade_image_url(hi_res_url, 1500)
                    if hi_res_url not in collected_images:
                        collected_images.append(hi_res_url)
                        print(f"       [{idx+1}] ✅ 수집: ...{hi_res_url[-50:]}")
                    else:
                        print(f"       [{idx+1}] ⏭️ 이미 수집됨")
                else:
                    print(f"       [{idx+1}] ⚠️ 고해상도 URL 추출 실패")

            except Exception as e:
                print(f"       [{idx+1}] ❌ 에러: {e}")

        return collected_images

    def _extract_images_from_html(self, page) -> list:
        """HTML/JavaScript에서 모든 이미지 URL 직접 추출 (fallback)"""
        images = []
        try:
            html_content = page.content()

            # hiRes 이미지
            hi_res_matches = re.findall(
                r'"hiRes"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"',
                html_content
            )
            for url in hi_res_matches:
                upgraded = upgrade_image_url(url, 1500)
                if upgraded not in images:
                    images.append(upgraded)

            # large 이미지 (hiRes 없을 경우)
            if not images:
                large_matches = re.findall(
                    r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"',
                    html_content
                )
                for url in large_matches:
                    upgraded = upgrade_image_url(url, 1500)
                    if upgraded not in images:
                        images.append(upgraded)
        except Exception as e:
            print(f"     HTML 이미지 추출 에러: {e}")

        return images

    def _extract_description(self, page):
        """상세 설명 추출"""
        desc = {}

        # 상품 설명 (productDescription)
        desc_el = page.query_selector("#productDescription")
        if desc_el:
            desc["main"] = desc_el.inner_text().strip()

        # A+ 콘텐츠 / aplus
        aplus = page.query_selector("#aplus, #aplus_feature_div, .aplus-v2")
        if aplus:
            desc["aplus_text"] = aplus.inner_text().strip()
            # A+ 이미지 추출
            aplus_images = aplus.query_selector_all("img")
            aplus_img_urls = []
            for img in aplus_images:
                src = img.get_attribute("data-src") or img.get_attribute("src") or ""
                if "media-amazon.com" in src and "grey-pixel" not in src:
                    hi_res = upgrade_image_url(src, 1500)
                    aplus_img_urls.append(hi_res)
                    if hi_res not in self.images:
                        self.images.append(hi_res)
            desc["aplus_images"] = aplus_img_urls

        # 브랜드 스토리
        brand_story = page.query_selector("#aplusBrandStory_feature_div")
        if brand_story:
            desc["brand_story"] = brand_story.inner_text().strip()

        self.product_data["description"] = desc
        print(f"   설명 섹션: {len(desc)}개")

    def _download_all_images(self, images_dir: Path):
        """모든 이미지 다운로드 - 컬러별 폴더 구조로 저장"""
        variant_images = self.product_data.get("variant_images", {})

        # 컬러별로 이미지 다운로드
        if variant_images:
            for color_name, urls in variant_images.items():
                if not urls:
                    continue

                # 컬러별 폴더 생성
                safe_color = safe_filename(color_name)
                color_dir = images_dir / safe_color
                color_dir.mkdir(parents=True, exist_ok=True)

                print(f"\n  📁 [{safe_color}] 폴더 - {len(urls)}개 이미지")

                for idx, url in enumerate(urls):
                    ext = ".jpg"
                    if ".png" in url:
                        ext = ".png"

                    # 첫 번째는 thumbnail, 나머지는 순번
                    if idx == 0:
                        filename = f"thumbnail{ext}"
                    else:
                        filename = f"image_{idx:02d}{ext}"

                    save_path = color_dir / filename
                    if not save_path.exists():
                        download_image(url, save_path)
                        time.sleep(0.3)
                    else:
                        print(f"    ⏭️ 이미 존재: {filename}")

        # 컬러 옵션이 없는 경우 기존 방식으로 저장
        else:
            print(f"\n  📁 기본 이미지 폴더 - {len(self.images)}개 이미지")
            for i, url in enumerate(self.images):
                ext = ".jpg"
                if ".png" in url:
                    ext = ".png"

                if i == 0:
                    filename = f"thumbnail{ext}"
                else:
                    filename = f"image_{i:02d}{ext}"

                save_path = images_dir / filename
                if not save_path.exists():
                    download_image(url, save_path)
                    time.sleep(0.3)
                else:
                    print(f"  ⏭️ 이미 존재: {filename}")

    def _compile_result(self) -> dict:
        """최종 결과 데이터 구성"""
        result = {
            **self.product_data,
            "all_image_urls": self.images,
        }
        return result

    def _save_results(self, output_dir: Path, result: dict):
        """결과 저장"""
        # JSON 저장
        json_path = output_dir / "product_info.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"   📄 JSON: {json_path}")

        # 한국어 요약 텍스트 저장
        summary_path = output_dir / "product_summary.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"Amazon Japan 상품 정보\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"상품명: {result.get('title', 'N/A')}\n")
            f.write(f"브랜드: {result.get('brand', 'N/A')}\n")
            f.write(f"ASIN: {result.get('asin', 'N/A')}\n")
            f.write(f"URL: {result.get('url', 'N/A')}\n")
            f.write(f"가격: {result.get('price', 'N/A')}\n")
            if result.get('original_price'):
                f.write(f"정가: {result['original_price']}\n")
                f.write(f"할인: {result.get('discount', 'N/A')}\n")
            f.write(f"평점: {result.get('rating', 'N/A')}\n")
            f.write(f"리뷰: {result.get('review_count', 'N/A')}\n")
            f.write(f"판매자: {result.get('seller', 'N/A')}\n")
            f.write(f"재고: {result.get('availability', 'N/A')}\n\n")

            f.write(f"--- 카테고리 ---\n")
            for cat in result.get('category', []):
                f.write(f"  > {cat}\n")

            f.write(f"\n--- 컬러 옵션 ({len(result.get('color_options', []))}) ---\n")
            for c in result.get('color_options', []):
                marker = " [선택됨]" if c.get('selected') else ""
                f.write(f"  • {c.get('name', '?')}{marker} (ASIN: {c.get('asin', 'N/A')})\n")

            f.write(f"\n--- 사이즈 옵션 ({len(result.get('size_options', []))}) ---\n")
            for s in result.get('size_options', []):
                marker = " [선택됨]" if s.get('selected') else ""
                avail = "" if s.get('available', True) else " [품절]"
                f.write(f"  • {s.get('name', '?')}{marker}{avail} (ASIN: {s.get('asin', 'N/A')})\n")

            f.write(f"\n--- 상품 특징 ---\n")
            for feat in result.get('features', []):
                f.write(f"  • {feat}\n")

            f.write(f"\n--- 상세 스펙 ---\n")
            for k, v in result.get('specs', {}).items():
                f.write(f"  {k}: {v}\n")

            f.write(f"\n--- 이미지 ({len(result.get('all_image_urls', []))}) ---\n")
            for i, url in enumerate(result.get('all_image_urls', [])):
                f.write(f"  [{i+1}] {url}\n")

            if result.get('description', {}).get('main'):
                f.write(f"\n--- 상품 설명 ---\n")
                f.write(result['description']['main'] + "\n")

            if result.get('dimension_to_asin_map'):
                f.write(f"\n--- 사이즈×컬러 ASIN 매핑 ---\n")
                for combo, asin in result['dimension_to_asin_map'].items():
                    f.write(f"  {combo}: {asin}\n")

        print(f"   📝 요약: {summary_path}")


# ============================================================
# 실행
# ============================================================

def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Amazon.co.jp 상품 URL을 입력하세요: ").strip()

    if not url:
        print("❌ URL을 입력해주세요.")
        sys.exit(1)

    if "amazon.co.jp" not in url and "amazon.jp" not in url:
        print("⚠️ Amazon Japan URL이 아닌 것 같습니다. 계속 진행합니다...")

    scraper = AmazonJPScraper()
    result = scraper.scrape(url)

    if result:
        print("\n✅ 스크래핑 완료!")
    else:
        print("\n❌ 스크래핑 실패!")
        sys.exit(1)


if __name__ == "__main__":
    main()

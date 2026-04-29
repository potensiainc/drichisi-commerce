# -*- coding: utf-8 -*-
"""
배치 스크래핑 실행 스크립트
batch_urls.txt의 모든 URL을 순차적으로 스크래핑
"""

import sys
import os
import time
from pathlib import Path

# 현재 디렉토리를 추가
sys.path.insert(0, str(Path(__file__).parent))

from amazon_jp_scraper import AmazonJPScraper

def main():
    urls_file = Path("D:/commerce/batch_urls.txt")

    if not urls_file.exists():
        print("❌ batch_urls.txt 파일이 없습니다.")
        return

    # URL 목록 읽기
    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and line.strip().startswith("http")]

    print(f"\n{'='*60}")
    print(f"📦 배치 스크래핑 시작")
    print(f"   총 {len(urls)}개 상품")
    print(f"{'='*60}\n")

    scraper = AmazonJPScraper()

    success_count = 0
    fail_count = 0
    failed_urls = []

    for i, url in enumerate(urls, 1):
        print(f"\n{'='*60}")
        print(f"📌 [{i}/{len(urls)}] 진행 중...")
        print(f"{'='*60}")

        try:
            result = scraper.scrape(url)
            if result:
                success_count += 1
                print(f"✅ [{i}/{len(urls)}] 성공: {result.get('title_kr', result.get('title', 'N/A'))[:40]}...")
            else:
                fail_count += 1
                failed_urls.append(url)
                print(f"❌ [{i}/{len(urls)}] 실패: {url}")
        except Exception as e:
            fail_count += 1
            failed_urls.append(url)
            print(f"❌ [{i}/{len(urls)}] 에러: {e}")

        # 다음 요청 전 대기 (봇 감지 방지)
        if i < len(urls):
            print(f"\n⏳ 다음 상품까지 5초 대기...")
            time.sleep(5)

        # 스크래퍼 상태 초기화
        scraper.product_data = {}
        scraper.variant_data = []
        scraper.images = []

    # 결과 요약
    print(f"\n{'='*60}")
    print(f"📊 배치 스크래핑 완료!")
    print(f"{'='*60}")
    print(f"   ✅ 성공: {success_count}개")
    print(f"   ❌ 실패: {fail_count}개")

    if failed_urls:
        print(f"\n실패한 URL:")
        for url in failed_urls:
            print(f"   - {url}")

        # 실패한 URL 저장
        with open("D:/commerce/failed_urls.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(failed_urls))
        print(f"\n실패 URL 저장: D:/commerce/failed_urls.txt")

    print(f"\n저장 위치: D:/commerce/products/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

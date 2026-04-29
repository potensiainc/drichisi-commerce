# 드리치시 스마트스토어 자동화 시스템

일본 구매대행 스마트스토어 **드리치시(Drichisi)**의 상품 등록 및 마케팅 자동화 시스템입니다.

## 주요 기능

### 상품 등록 파이프라인
- **product-analyzer**: 상품 데이터 분석 및 리스크 체크
- **naver-smartstore-seo**: 네이버 검색 최적화 상품명/태그 생성
- **smartstore-page-builder**: 860px 고정폭 상세페이지 HTML 생성

### 마케팅 파이프라인
- **threads-content-creator**: 품격/인사이트 콘텐츠 (팔로워 유입용)
- **instagram-content-creator**: 카드뉴스 + 릴스 스크립트
- **naver-blog-content-creator**: SEO 최적화 상품 리뷰
- **content-calendar-manager**: 발행 일정 관리

## 프로젝트 구조

```
commerce/
├── .claude/
│   ├── CLAUDE.md              # 프로젝트 설정 및 브랜드 가이드
│   └── agents/                # 에이전트 정의 파일
├── products/                  # 상품별 데이터 폴더
│   └── [상품명]/
│       ├── product_data.json
│       ├── analysis.json
│       ├── seo.json
│       └── images/
├── marketing/
│   ├── brand-guidelines.md    # 브랜드 가이드라인
│   ├── history/               # 콘텐츠 히스토리
│   ├── threads/               # Threads 콘텐츠
│   ├── instagram/             # Instagram 콘텐츠
│   ├── naver-blog/            # 네이버 블로그 콘텐츠
│   └── calendar/              # 발행 캘린더
├── assets/                    # 공통 에셋
└── scripts/                   # 유틸리티 스크립트
```

## 워크플로우

### 상품 등록
```
1. 상품 스크래핑 → products/[상품명]/ 폴더 생성
2. product-analyzer → analysis.json 생성
3. naver-smartstore-seo → seo.json 생성
4. smartstore-page-builder → detail.html 생성
```

### 마케팅 콘텐츠
```
1. 콘텐츠 히스토리 확인 (중복 방지)
2. 플랫폼별 에이전트로 콘텐츠 생성
3. 히스토리 업데이트
4. 캘린더에 발행 일정 등록
```

## 브랜드 정보

| 항목 | 내용 |
|------|------|
| 스토어명 | 드리치시 (Drichisi) |
| 스토어 URL | https://smartstore.naver.com/drichisi |
| 블로그 URL | https://blog.naver.com/prohustler |
| SNS | @drichisi_ (Threads/Instagram) |
| 타겟 고객 | 20-40대 여성 |
| 카테고리 | 일본 인테리어/잡화, 육아/유아용품 |

## 설치

```bash
# 의존성 설치
npm install
pip install -r requirements.txt  # Python 스크래퍼용
```

## 사용법

Claude Code CLI에서 에이전트를 호출하여 사용합니다:

```
# 상품 분석
"products/[상품명] 분석해줘"

# 전체 상품 등록 프로세스
"products/[상품명] 전체 프로세스 돌려줘"

# 마케팅 콘텐츠 생성
"Threads 글 5개 만들어줘"
"인스타 콘텐츠 만들어줘"
"블로그 글 써줘"
```

## 라이선스

Private - All rights reserved

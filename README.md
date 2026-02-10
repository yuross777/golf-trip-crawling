# NZ Golf Course Crawler

Google Places API (New)를 사용하여 **뉴질랜드 전체 골프장 (~420개)** 정보를 자동 수집하는 크롤러입니다.

## 수집 파이프라인

```
Phase 1: Text Search     - 16개 지역별 골프장 검색 (Google Places API)
Phase 2: Place Details   - 각 코스 상세 정보 수집 (전화, 웹사이트, 평점, 사진 등)
Phase 3: Region Classify - 주소 기반 섬/지역 자동 분류
Phase 4: Web Scraping    - 코스 웹사이트에서 그린피, 예약 URL 추출 (선택)
Phase 5: Tag Generation  - 가격/뷰/특성 기반 태그 자동 생성
```

## 설치

### 1. Python 패키지 설치

```bash
pip install requests beautifulsoup4 lxml
```

### 2. Google Places API 키 발급

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성 또는 선택
3. **Places API (New)** 활성화
4. **사용자 인증 정보** > **API 키 만들기**
5. (권장) API 키 제한 설정: Places API만 허용

> 비용: Places API Text Search $32 / 1,000건, Place Details $17 / 1,000건
> 매월 $200 무료 크레딧 제공 (약 400개 코스 수집 시 ~$20 USD)

### 3. API 키 설정

**방법 A: 환경변수 (권장)**

```bash
# Windows (CMD)
set GOOGLE_PLACES_API_KEY=your_api_key_here

# Windows (PowerShell)
$env:GOOGLE_PLACES_API_KEY="your_api_key_here"

# Linux / macOS
export GOOGLE_PLACES_API_KEY=your_api_key_here
```

**방법 B: 실행 시 직접 전달**

```bash
python comprehensive_crawler.py --api-key your_api_key_here
```

**방법 C: 대화형 입력**

환경변수와 `--api-key` 모두 없으면 실행 시 직접 입력을 요청합니다.

## 실행

### 테스트 실행 (Auckland만)

```bash
# 기본 테스트 (Phase 1~3 + Phase 5)
python comprehensive_crawler.py --test --api-key your_api_key_here

# 웹사이트 스크래핑 포함 (Phase 1~5 전체)
python comprehensive_crawler.py --test --scrape-websites --api-key your_api_key_here
```

### 전체 크롤링 (16개 지역)

```bash
# 기본 실행 (Phase 1~3 + Phase 5)
python comprehensive_crawler.py --api-key your_api_key_here

# 웹사이트 스크래핑 포함 (Phase 1~5 전체, 권장)
python comprehensive_crawler.py --scrape-websites --api-key your_api_key_here

# 출력 파일명 지정
python comprehensive_crawler.py --scrape-websites --output my_golf_data --api-key your_api_key_here
```

### 중단 후 이어서 실행

크롤링 중 중단되면 `crawl_progress.json`에 진행상황이 저장됩니다.

```bash
# 이어서 실행 (이미 수집한 데이터 유지)
python comprehensive_crawler.py --resume --api-key your_api_key_here

# 이어서 실행 + 웹 스크래핑
python comprehensive_crawler.py --resume --scrape-websites --api-key your_api_key_here
```

### Place Details 생략

Text Search만 빠르게 실행하고 싶을 때:

```bash
python comprehensive_crawler.py --skip-details --api-key your_api_key_here
```

### 전체 옵션 요약

| 옵션 | 설명 |
|------|------|
| `--api-key KEY` | Google Places API 키 직접 전달 |
| `--test` | 테스트 모드 (Auckland 지역만 검색) |
| `--resume` | 중단된 크롤링 이어서 실행 |
| `--skip-details` | Phase 2 (Place Details) 생략 |
| `--scrape-websites` | Phase 4 (웹사이트 스크래핑) 활성화 |
| `--output PREFIX` | 출력 파일명 접두사 (기본: `nz_golf_courses`) |

## 출력 파일

| 파일 | 설명 |
|------|------|
| `nz_golf_courses.json` | 전체 코스 데이터 (JSON) |
| `nz_golf_courses.csv` | 전체 코스 데이터 (CSV) |
| `crawl_progress.json` | 진행상황 저장 (중단 시 복구용) |

## 데이터 구조

```json
{
  "id": 1,
  "name": "Muriwai Golf Club",
  "place_id": "ChIJ...",
  "address": "Muriwai Beach, Auckland 0881",
  "lat": -36.8301,
  "lng": 174.4401,
  "island": "North Island",
  "region": "Auckland",
  "phone": "+64 9 411 8454",
  "website_url": "http://www.muriwaigolfclub.co.nz",
  "rating": 4.6,
  "review_count": 215,
  "opening_hours": ["Monday: 6:00 AM – 6:00 PM", "..."],
  "google_maps_url": "https://maps.google.com/?cid=...",
  "photo_url": "https://places.googleapis.com/v1/...",
  "description": "Dramatic clifftop links course with stunning ocean views.",
  "price_min_nzd": 60,
  "price_max_nzd": 190,
  "tags": ["coast", "links", "mid"],
  "booking_url": "http://www.muriwaigolfclub.co.nz/book-a-round"
}
```

### 필드별 데이터 소스

| 필드 | Phase | 소스 |
|------|-------|------|
| name, address, lat, lng | 1 | Google Text Search |
| phone, website_url, rating, review_count | 2 | Google Place Details |
| opening_hours, google_maps_url, photo_url | 2 | Google Place Details |
| description | 2 | Google editorialSummary |
| price_min_nzd, price_max_nzd | 2+4 | Google priceRange + 웹 스크래핑 |
| island, region | 3 | 주소 기반 자동 분류 |
| booking_url | 4 | 웹사이트 스크래핑 |
| tags | 5 | 가격/뷰/특성 자동 파생 |

## 태그 분류 체계

각 코스에 3가지 카테고리에서 태그가 자동 부여됩니다.

### 가격 (price_min_nzd 기준)

| 태그 | 기준 |
|------|------|
| `premium` | NZD 120 이상 |
| `mid` | NZD 40 ~ 119 |
| `value` | NZD 39 이하 |

### 뷰 / 환경

| 태그 | 키워드 |
|------|--------|
| `coast` | ocean, sea, cliff, beach, bay, harbour 등 |
| `mountain` | mountain, alpine, hill, volcano 등 |
| `lake` | lake, lakeside, riverside 등 |
| `forest` | forest, bush, woodland 등 |
| `city` | cbd, central, metropolitan, urban 등 |
| `rural` | 위 키워드에 해당 없는 경우 (기본값) |

### 코스 특성

| 태그 | 기준 |
|------|------|
| `links` | 이름/설명에 "links" 포함 |
| `resort` | "resort" 포함 또는 Google 타입이 resort/lodging |
| `local` | 위에 해당 없는 경우 (기본값) |

## 대상 지역 (16개)

| 북섬 (North Island) | 남섬 (South Island) |
|---------------------|---------------------|
| Auckland | Canterbury |
| Bay of Plenty | Marlborough |
| Gisborne | Nelson |
| Hawke's Bay | Otago |
| Manawatu-Wanganui | Southland |
| Northland | Tasman |
| Taranaki | West Coast |
| Waikato | |
| Wellington | |

## 비용 예상

| 항목 | 단가 | 400개 코스 기준 |
|------|------|----------------|
| Text Search | $32 / 1,000건 | ~$1 (16건) |
| Place Details | $17 / 1,000건 | ~$7 (420건) |
| **합계** | | **~$8 USD** |

> Google Cloud 매월 $200 무료 크레딧이 제공되므로 무료로 사용 가능합니다.

## 주의사항

- 웹사이트 스크래핑(`--scrape-websites`)은 best-effort 방식입니다. 모든 코스에서 가격/예약 정보가 추출되지는 않습니다.
- 가격 정보는 시즌별로 변동되므로 정기적인 재수집을 권장합니다.
- Google Places API `editorialSummary`(description)는 일부 코스에만 제공됩니다.

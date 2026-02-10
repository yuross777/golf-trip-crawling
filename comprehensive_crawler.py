"""
뉴질랜드 전체 골프 코스 크롤링 시스템
Google Places API (New)를 사용하여 ~420개 골프 코스 정보 수집

사용법:
    set GOOGLE_PLACES_API_KEY=your_key_here
    python comprehensive_crawler.py

    python comprehensive_crawler.py --api-key your_key_here
    python comprehensive_crawler.py --test  # Auckland만 테스트
    python comprehensive_crawler.py --resume  # 중단된 크롤링 이어서 수행
"""

import sys
import io
import os
import json
import csv
import re
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Windows stdout UTF-8 강제 설정 (cp949 문제 해결)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import requests
except ImportError:
    print("requests 라이브러리가 필요합니다: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ============================================================
# 상수 정의
# ============================================================

# GolfPass 기준 16개 지역 (총 ~426개 코스)
NZ_REGIONS = [
    "Auckland",
    "Bay of Plenty",
    "Canterbury",
    "Gisborne",
    "Hawke's Bay",
    "Manawatu-Wanganui",
    "Marlborough",
    "Nelson",
    "Northland",
    "Otago",
    "Southland",
    "Taranaki",
    "Tasman",
    "Waikato",
    "Wellington",
    "West Coast",
]

# 지역 → 섬 매핑
REGION_TO_ISLAND = {
    "Auckland": "North Island",
    "Bay of Plenty": "North Island",
    "Gisborne": "North Island",
    "Hawke's Bay": "North Island",
    "Manawatu-Wanganui": "North Island",
    "Northland": "North Island",
    "Taranaki": "North Island",
    "Waikato": "North Island",
    "Wellington": "North Island",
    "Canterbury": "South Island",
    "Marlborough": "South Island",
    "Nelson": "South Island",
    "Otago": "South Island",
    "Southland": "South Island",
    "Tasman": "South Island",
    "West Coast": "South Island",
}

# 주소 키워드 → 지역 매핑 (Place Details 주소에서 지역 추출용)
ADDRESS_REGION_KEYWORDS = {
    "Auckland": "Auckland",
    "Bay of Plenty": "Bay of Plenty",
    "Tauranga": "Bay of Plenty",
    "Rotorua": "Bay of Plenty",
    "Whakatane": "Bay of Plenty",
    "Canterbury": "Canterbury",
    "Christchurch": "Canterbury",
    "Ashburton": "Canterbury",
    "Timaru": "Canterbury",
    "Gisborne": "Gisborne",
    "Hawke's Bay": "Hawke's Bay",
    "Napier": "Hawke's Bay",
    "Hastings": "Hawke's Bay",
    "Manawatu": "Manawatu-Wanganui",
    "Wanganui": "Manawatu-Wanganui",
    "Whanganui": "Manawatu-Wanganui",
    "Palmerston North": "Manawatu-Wanganui",
    "Marlborough": "Marlborough",
    "Blenheim": "Marlborough",
    "Nelson": "Nelson",
    "Northland": "Northland",
    "Whangarei": "Northland",
    "Kerikeri": "Northland",
    "Otago": "Otago",
    "Dunedin": "Otago",
    "Queenstown": "Otago",
    "Wanaka": "Otago",
    "Cromwell": "Otago",
    "Southland": "Southland",
    "Invercargill": "Southland",
    "Taranaki": "Taranaki",
    "New Plymouth": "Taranaki",
    "Tasman": "Tasman",
    "Motueka": "Tasman",
    "Waikato": "Waikato",
    "Hamilton": "Waikato",
    "Cambridge": "Waikato",
    "Taupo": "Waikato",
    "Te Awamutu": "Waikato",
    "Wellington": "Wellington",
    "Lower Hutt": "Wellington",
    "Upper Hutt": "Wellington",
    "Porirua": "Wellington",
    "Kapiti": "Wellington",
    "Paraparaumu": "Wellington",
    "West Coast": "West Coast",
    "Greymouth": "West Coast",
    "Hokitika": "West Coast",
}

# Places API (New) 엔드포인트
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
PLACE_PHOTO_URL = "https://places.googleapis.com/v1/{photo_name}/media"

# Text Search에서 요청할 필드
TEXT_SEARCH_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
])

# Place Details에서 요청할 필드
DETAILS_FIELD_MASK = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "internationalPhoneNumber",
    "websiteUri",
    "rating",
    "userRatingCount",
    "currentOpeningHours",
    "regularOpeningHours",
    "googleMapsUri",
    "photos",
    "editorialSummary",
    "priceLevel",
    "priceRange",
])

# 진행상황 저장 파일
PROGRESS_FILE = "crawl_progress.json"


# ============================================================
# 크롤러 클래스
# ============================================================


class NZGolfCourseCrawler:
    """Google Places API (New) 기반 뉴질랜드 골프 코스 크롤러"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
        })
        # place_id → course dict
        self.courses: Dict[str, Dict] = {}
        self.api_call_count = 0

    # ----------------------------------------------------------
    # 1단계: Text Search - 지역별 골프 코스 검색
    # ----------------------------------------------------------

    def search_region(self, region: str) -> List[Dict]:
        """한 지역의 골프 코스를 Text Search API로 검색한다.

        페이지네이션(nextPageToken)을 처리하여 최대한 모든 결과를 가져온다.
        """
        query = f"golf course in {region}, New Zealand"
        print(f"  Searching: {query}")

        all_places = []
        page_token = None
        page_num = 0

        while True:
            page_num += 1
            body: Dict = {
                "textQuery": query,
                "languageCode": "en",
                "regionCode": "NZ",
                "pageSize": 20,
            }
            if page_token:
                body["pageToken"] = page_token

            headers = {
                "X-Goog-FieldMask": TEXT_SEARCH_FIELD_MASK,
            }

            resp = self._api_post(TEXT_SEARCH_URL, json_body=body, extra_headers=headers)
            if resp is None:
                break

            places = resp.get("places", [])
            all_places.extend(places)
            print(f"    Page {page_num}: {len(places)} results (total: {len(all_places)})")

            page_token = resp.get("nextPageToken")
            if not page_token or len(places) == 0:
                break

            # nextPageToken 사용 전 짧은 대기
            time.sleep(2)

        return all_places

    def search_all_regions(self, regions: List[str]) -> None:
        """모든 지역을 검색하여 self.courses에 place_id 기준 저장 (중복 자동 제거)."""
        print("\n[Phase 1] Text Search - searching golf courses by region")
        print("=" * 60)

        for i, region in enumerate(regions, 1):
            print(f"\n[{i}/{len(regions)}] Region: {region}")
            places = self.search_region(region)

            new_count = 0
            for place in places:
                place_id = place.get("id", "")
                if not place_id or place_id in self.courses:
                    continue

                display_name = place.get("displayName", {})
                location = place.get("location", {})

                self.courses[place_id] = {
                    "place_id": place_id,
                    "name": display_name.get("text", ""),
                    "address": place.get("formattedAddress", ""),
                    "lat": location.get("latitude"),
                    "lng": location.get("longitude"),
                    "types": place.get("types", []),
                    "search_region": region,
                    # 아래 필드는 Phase 2에서 채움
                    "phone": None,
                    "website_url": None,
                    "rating": None,
                    "review_count": None,
                    "opening_hours": None,
                    "google_maps_url": None,
                    "photo_url": None,
                    # 추가 필드 (Phase 2 + Phase 4에서 채움)
                    "description": None,
                    "price_min_nzd": None,
                    "price_max_nzd": None,
                    "tags": [],
                    "booking_url": None,
                }
                new_count += 1

            print(f"    -> {new_count} new courses added (duplicates skipped)")

            # 지역 간 짧은 대기
            time.sleep(1)

        print(f"\n  Total unique courses after Text Search: {len(self.courses)}")

    # ----------------------------------------------------------
    # 2단계: Place Details - 상세 정보 수집
    # ----------------------------------------------------------

    def fetch_details(self, place_id: str) -> Optional[Dict]:
        """한 place_id에 대한 상세 정보를 가져온다."""
        url = PLACE_DETAILS_URL.format(place_id=place_id)
        headers = {
            "X-Goog-FieldMask": DETAILS_FIELD_MASK,
        }
        return self._api_get(url, extra_headers=headers)

    def enrich_all_courses(self) -> None:
        """모든 코스에 대해 Place Details를 가져와 상세 정보를 채운다."""
        print("\n[Phase 2] Place Details - enriching course information")
        print("=" * 60)

        courses_list = list(self.courses.values())
        total = len(courses_list)

        for i, course in enumerate(courses_list, 1):
            place_id = course["place_id"]

            # 이미 enriched 된 경우 스킵
            if course.get("_enriched"):
                print(f"  [{i}/{total}] {course['name']} - skipped (already enriched)")
                continue

            print(f"  [{i}/{total}] {course['name']}...", end=" ", flush=True)

            details = self.fetch_details(place_id)
            if details:
                self._apply_details(place_id, details)
                print("OK")
            else:
                print("FAILED")

            # Rate limiting: ~5 QPS (안전 마진 포함)
            time.sleep(0.25)

            # 50개마다 중간 저장
            if i % 50 == 0:
                self._save_progress()
                print(f"    [Progress saved at {i}/{total}]")

    def _apply_details(self, place_id: str, details: Dict) -> None:
        """API 응답에서 필요한 필드를 추출하여 courses 딕셔너리에 반영."""
        course = self.courses[place_id]

        # 전화번호
        course["phone"] = details.get("internationalPhoneNumber")

        # 웹사이트
        course["website_url"] = details.get("websiteUri")

        # 평점
        course["rating"] = details.get("rating")
        course["review_count"] = details.get("userRatingCount")

        # Google Maps URL
        course["google_maps_url"] = details.get("googleMapsUri")

        # 운영 시간
        hours = details.get("currentOpeningHours") or details.get("regularOpeningHours")
        if hours and "weekdayDescriptions" in hours:
            course["opening_hours"] = hours["weekdayDescriptions"]

        # 주소 업데이트 (Details가 더 정확할 수 있음)
        if details.get("formattedAddress"):
            course["address"] = details["formattedAddress"]

        # 이름 업데이트
        display_name = details.get("displayName", {})
        if display_name.get("text"):
            course["name"] = display_name["text"]

        # 좌표 업데이트
        loc = details.get("location", {})
        if loc.get("latitude"):
            course["lat"] = loc["latitude"]
            course["lng"] = loc["longitude"]

        # 대표 사진 URL (첫 번째 사진)
        photos = details.get("photos", [])
        if photos:
            photo_name = photos[0].get("name", "")
            if photo_name:
                course["photo_url"] = (
                    f"{PLACE_PHOTO_URL.format(photo_name=photo_name)}"
                    f"?maxWidthPx=800&key={self.api_key}"
                )

        # 설명 (editorialSummary)
        editorial = details.get("editorialSummary", {})
        if editorial.get("text"):
            course["description"] = editorial["text"]

        # 가격 범위 (priceRange - Google Places API New)
        price_range = details.get("priceRange", {})
        if price_range:
            start_price = price_range.get("startPrice", {})
            end_price = price_range.get("endPrice", {})
            if start_price.get("units"):
                course["price_min_nzd"] = int(start_price["units"])
            if end_price.get("units"):
                course["price_max_nzd"] = int(end_price["units"])

        # 가격 레벨 (태그 생성용으로 내부 저장)
        course["_price_level"] = details.get("priceLevel")

        course["_enriched"] = True

    # ----------------------------------------------------------
    # 3단계: 지역 분류
    # ----------------------------------------------------------

    def classify_regions(self) -> None:
        """주소 기반으로 island과 region을 매핑한다."""
        print("\n[Phase 3] Classifying regions (island & region mapping)")
        print("=" * 60)

        classified = 0
        for course in self.courses.values():
            region, island = self._detect_region(course.get("address", ""))
            if not region:
                # 검색 시 사용한 지역을 fallback으로 사용
                region = course.get("search_region", "")
                island = REGION_TO_ISLAND.get(region, "")

            course["region"] = region
            course["island"] = island
            if region:
                classified += 1

        print(f"  Classified: {classified}/{len(self.courses)}")

    def _detect_region(self, address: str) -> Tuple[str, str]:
        """주소 문자열에서 지역과 섬을 추출한다."""
        if not address:
            return ("", "")

        # 긴 키워드 먼저 매칭하기 위해 길이 역순 정렬
        for keyword in sorted(ADDRESS_REGION_KEYWORDS.keys(), key=len, reverse=True):
            if keyword.lower() in address.lower():
                region = ADDRESS_REGION_KEYWORDS[keyword]
                island = REGION_TO_ISLAND.get(region, "")
                return (region, island)

        return ("", "")

    # ----------------------------------------------------------
    # 4단계: 웹사이트 스크래핑 (가격, 예약 URL)
    # ----------------------------------------------------------

    # 가격 페이지를 찾기 위한 하위 경로 후보
    _PRICE_SUB_PATHS = [
        "/green-fees", "/greenfees", "/green-fee", "/greenfee",
        "/visitors", "/visitor", "/visitor-info", "/visitor-information",
        "/rates", "/pricing", "/prices", "/fees",
        "/play", "/play-golf", "/casual-play",
    ]

    # booking_url에서 제외할 패턴
    _BOOKING_URL_EXCLUDE = re.compile(
        r'\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|pdf)(\?|$)'
        r'|facebook\.com|instagram\.com|twitter\.com|youtube\.com'
        r'|linkedin\.com|tiktok\.com|mailto:',
        re.IGNORECASE,
    )

    def scrape_websites(self) -> None:
        """골프 코스 웹사이트에서 가격 및 예약 URL을 추출한다 (best-effort)."""
        if BeautifulSoup is None:
            print("\n  [WARNING] beautifulsoup4 not installed. Skipping website scraping.")
            print("  Install with: pip install beautifulsoup4 lxml")
            return

        print("\n[Phase 4] Website Scraping - extracting pricing & booking info")
        print("=" * 60)

        courses_with_website = [
            c for c in self.courses.values()
            if c.get("website_url") and not c.get("_website_scraped")
        ]
        total = len(courses_with_website)
        print(f"  Courses to scrape: {total}")

        success = 0
        for i, course in enumerate(courses_with_website, 1):
            url = course["website_url"]
            print(f"  [{i}/{total}] {course['name']}...", end=" ", flush=True)

            try:
                # 메인 페이지 + 가격 하위 페이지 크롤링
                pages = self._fetch_pages(url)

                for page_url, soup in pages:
                    self._extract_booking_url(course, soup, page_url)
                    self._extract_pricing(course, soup)
                    self._extract_description(course, soup)

                course["_website_scraped"] = True
                info = []
                if course.get("price_min_nzd"):
                    info.append(f"${course['price_min_nzd']}-${course['price_max_nzd']}")
                if course.get("booking_url"):
                    info.append("booking")
                if course.get("description"):
                    info.append("desc")
                status = ", ".join(info) if info else "nothing found"
                print(f"OK ({status}) [{len(pages)} pages]")
                success += 1
            except Exception as e:
                print(f"FAILED ({type(e).__name__})")

            time.sleep(0.5)

            if i % 50 == 0:
                self._save_progress()
                print(f"    [Progress saved at {i}/{total}]")

        print(f"\n  Successfully scraped: {success}/{total}")

    def _fetch_pages(self, base_url: str) -> List[Tuple[str, "BeautifulSoup"]]:
        """메인 페이지와 가격 관련 하위 페이지들을 가져온다."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NZGolfCrawler/1.0)"}
        pages = []

        # 1) 메인 페이지
        try:
            resp = requests.get(base_url, timeout=10, headers=headers, allow_redirects=True)
            soup = BeautifulSoup(resp.text, "lxml")
            pages.append((base_url, soup))
        except Exception:
            return pages

        # 2) 메인 페이지의 <a> 태그에서 가격/방문자 관련 링크 탐색
        fee_keywords = re.compile(
            r'green.?fee|visitor|rates?|pricing|prices?|fees?|casual.?play',
            re.IGNORECASE,
        )
        found_sub_urls = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            link_text = a_tag.get_text(strip=True).lower()
            # 링크 텍스트 또는 href에 키워드가 있으면 후보
            if fee_keywords.search(link_text) or fee_keywords.search(href):
                sub_url = self._resolve_url(href, base_url)
                if sub_url and sub_url != base_url and sub_url not in found_sub_urls:
                    found_sub_urls.add(sub_url)

        # 3) 후보가 없으면 고정 경로 시도
        if not found_sub_urls:
            base_origin = re.match(r'(https?://[^/]+)', base_url)
            if base_origin:
                origin = base_origin.group(1)
                for path in self._PRICE_SUB_PATHS:
                    found_sub_urls.add(origin + path)

        # 하위 페이지 최대 3개만 요청
        for sub_url in list(found_sub_urls)[:3]:
            try:
                resp = requests.get(sub_url, timeout=8, headers=headers, allow_redirects=True)
                if resp.status_code == 200:
                    sub_soup = BeautifulSoup(resp.text, "lxml")
                    pages.append((sub_url, sub_soup))
            except Exception:
                pass
            time.sleep(0.3)

        return pages

    def _resolve_url(self, href: str, base_url: str) -> Optional[str]:
        """href를 절대 URL로 변환한다. 유효하지 않으면 None."""
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            return None
        if href.startswith("http"):
            return href
        # 상대 경로
        base_origin = re.match(r'(https?://[^/]+)', base_url)
        if not base_origin:
            return None
        origin = base_origin.group(1)
        if href.startswith("/"):
            return origin + href
        return base_url.rstrip("/") + "/" + href

    def _extract_pricing(self, course: Dict, soup: "BeautifulSoup") -> None:
        """BeautifulSoup으로 파싱된 페이지에서 그린피 가격을 추출한다."""
        if course.get("price_min_nzd"):
            return

        # script, style 태그 제거한 텍스트 추출
        text = soup.get_text(separator=" ", strip=True).lower()

        # 그린피 관련 키워드 주변 300자에서 가격 탐색
        fee_keywords = [
            "green fee", "green-fee", "greenfee",
            "visitor rate", "visitor fee", "visitor green",
            "casual rate", "casual play", "casual green",
            "affiliated", "non-affiliated",
            "18 hole", "18-hole", "9 hole", "9-hole",
            "weekday rate", "weekend rate", "round",
        ]

        fee_sections = []
        for keyword in fee_keywords:
            for m in re.finditer(re.escape(keyword), text):
                start = max(0, m.start() - 80)
                end = min(len(text), m.end() + 300)
                fee_sections.append(text[start:end])

        if not fee_sections:
            return

        # 가격 패턴 추출
        price_patterns = [
            r'\$\s?(\d{2,4})(?:\.\d{2})?',
            r'nzd\s*\$?\s*(\d{2,4})',
            r'(\d{2,4})\s*nzd',
        ]

        prices = []
        search_text = " ".join(fee_sections)
        for pattern in price_patterns:
            for m in re.findall(pattern, search_text):
                p = int(m)
                if 15 <= p <= 1500:
                    prices.append(p)

        if prices:
            course["price_min_nzd"] = min(prices)
            course["price_max_nzd"] = max(prices)

    def _extract_booking_url(self, course: Dict, soup: "BeautifulSoup", page_url: str) -> None:
        """BeautifulSoup으로 파싱된 페이지에서 예약 페이지 URL을 추출한다."""
        if course.get("booking_url"):
            return

        booking_keywords = re.compile(
            r'book\s*(a\s+)?(round|tee\s*time|now|online|here)|'
            r'tee\s*time|reserve|make\s*a\s*booking',
            re.IGNORECASE,
        )

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            link_text = a_tag.get_text(strip=True)

            # 링크 텍스트에 예약 키워드가 있는지 확인
            if not booking_keywords.search(link_text):
                continue

            resolved = self._resolve_url(href, page_url)
            if not resolved:
                continue

            # 제외 패턴 필터링 (CSS/JS/이미지/SNS)
            if self._BOOKING_URL_EXCLUDE.search(resolved):
                continue

            course["booking_url"] = resolved
            return

    def _extract_description(self, course: Dict, soup: "BeautifulSoup") -> None:
        """웹사이트에서 코스 설명을 추출한다 (meta 태그 → 본문 단락)."""
        if course.get("description"):
            return

        # 1) meta description / og:description
        for attr in [{"name": "description"}, {"property": "og:description"}]:
            meta = soup.find("meta", attrs=attr)
            if meta and meta.get("content", "").strip():
                desc = meta["content"].strip()
                # 너무 짧거나 일반적인 설명은 건너뛰기
                if len(desc) > 30 and not re.match(
                    r'^(welcome|home page|official|website)', desc, re.IGNORECASE
                ):
                    course["description"] = desc[:500]
                    return

        # 2) 본문에서 골프 관련 단락 추출
        golf_keywords = ["golf", "course", "club", "hole", "par",
                         "fairway", "green", "tee", "links"]
        for p_tag in soup.find_all("p"):
            text = p_tag.get_text(strip=True)
            if len(text) > 60 and any(kw in text.lower() for kw in golf_keywords):
                course["description"] = text[:500]
                return

    # ----------------------------------------------------------
    # 5단계: 누락 데이터 채우기 (description + price 추정)
    # ----------------------------------------------------------

    def fill_missing_data(self) -> None:
        """description과 price가 누락된 코스에 자동 생성/추정 값을 채운다."""
        print("\n[Phase 5] Fill Missing Data (descriptions & price estimates)")
        print("=" * 60)

        desc_generated = 0
        price_estimated = 0

        for course in self.courses.values():
            # description 자동 생성
            if not course.get("description"):
                course["description"] = self._generate_description(course)
                desc_generated += 1

            # price 추정
            if not course.get("price_min_nzd"):
                min_p, max_p = self._estimate_price_range(course)
                course["price_min_nzd"] = min_p
                course["price_max_nzd"] = max_p
                course["_price_estimated"] = True
                price_estimated += 1

        total = len(self.courses)
        scraped_desc = total - desc_generated
        scraped_price = total - price_estimated
        print(f"  Description: {scraped_desc} scraped + {desc_generated} generated = {total}")
        print(f"  Price:       {scraped_price} scraped + {price_estimated} estimated = {total}")

    def _generate_description(self, course: Dict) -> str:
        """수집된 데이터를 기반으로 코스 설명을 자동 생성한다."""
        name = course.get("name", "Golf Course")
        region = course.get("region", "New Zealand")
        island = course.get("island", "")
        rating = course.get("rating")
        review_count = course.get("review_count") or 0
        address = (course.get("address") or "").lower()
        name_lower = name.lower()
        text = f"{name_lower} {address}"

        # 코스 스타일 감지
        if "links" in name_lower:
            style = "Links-style"
        elif "resort" in name_lower:
            style = "Resort"
        elif "country club" in name_lower:
            style = "Country club"
        elif "club" in name_lower:
            style = "Golf club"
        else:
            style = "Golf course"

        # 뷰/환경 감지
        view_map = [
            (["ocean", "sea", "cliff", "coast", "beach", "bay", "harbour", "shore"],
             "featuring stunning coastal views"),
            (["mountain", "alpine", "hill", "volcano", "mt ", "mount "],
             "set against a scenic mountain backdrop"),
            (["lake", "lakeside", "riverside", "river"],
             "with beautiful lakeside scenery"),
            (["forest", "bush", "woodland"],
             "nestled among native bush"),
        ]
        view_phrase = "offering a peaceful playing environment"
        for keywords, phrase in view_map:
            if any(kw in text for kw in keywords):
                view_phrase = phrase
                break

        # 설명 조립
        desc = f"{style} in {region}"
        if island:
            desc += f", {island}"
        desc += f", {view_phrase}."

        if rating:
            desc += f" Rated {rating}/5"
            if review_count:
                desc += f" ({review_count:,} reviews)"
            desc += " on Google."

        return desc

    def _estimate_price_range(self, course: Dict) -> Tuple[int, int]:
        """코스 특성을 기반으로 그린피 범위를 추정한다 (NZD)."""
        name = (course.get("name") or "").lower()
        desc = (course.get("description") or "").lower()
        types = course.get("types", [])
        rating = course.get("rating") or 0
        region = course.get("region", "")
        text = f"{name} {desc}"

        is_resort = "resort" in text or any(
            t in types for t in ["resort_hotel", "lodging"]
        )
        is_links = "links" in text
        premium_regions = ["Otago", "Hawke's Bay", "Bay of Plenty"]

        if is_resort:
            return (150, 400)
        elif is_links and region in premium_regions:
            return (120, 300)
        elif is_links:
            return (80, 200)
        elif region in premium_regions and rating >= 4.5:
            return (80, 180)
        elif rating >= 4.5:
            return (50, 120)
        elif rating >= 4.0:
            return (35, 80)
        else:
            return (25, 60)

    # ----------------------------------------------------------
    # 6단계: 태그 생성
    # ----------------------------------------------------------

    def generate_all_tags(self) -> None:
        """모든 코스에 대해 태그를 자동 생성한다."""
        print("\n[Phase 6] Tag Generation")
        print("=" * 60)

        for course in self.courses.values():
            course["tags"] = self._generate_tags(course)

        # 태그 통계
        tag_counts: Dict[str, int] = {}
        for course in self.courses.values():
            for tag in course.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        print("  Tag distribution:")
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
            print(f"    {tag}: {count}")

    def _generate_tags(self, course: Dict) -> List[str]:
        """코스 정보를 기반으로 태그를 파생 생성한다.

        태그는 3가지 카테고리로 구분:
          - 가격: premium / mid / value
          - 뷰:   city / coast / forest / mountain / lake / rural
          - 특성: links / resort / local
        """
        tags = []
        name = (course.get("name") or "").lower()
        desc = (course.get("description") or "").lower()
        address = (course.get("address") or "").lower()
        types = course.get("types", [])
        text = f"{name} {desc} {address}"

        # ── 1. 가격 태그 (premium / mid / value) ── 항상 부여
        min_price = course.get("price_min_nzd") or 0
        if min_price >= 120:
            tags.append("premium")
        elif min_price >= 40:
            tags.append("mid")
        else:
            tags.append("value")

        # ── 2. 뷰 태그 (coast / mountain / lake / forest / city / rural) ──
        coast_kw = ["ocean", "sea", "cliff", "coast", "coastal", "beach",
                     "harbour", "harbor", "bay", "seaside", "waterfront",
                     "island", "peninsula", "shore"]
        mountain_kw = ["mountain", "alpine", "hill", "ridge", "highland",
                       "volcano", "mt ", "mount "]
        lake_kw = ["lake", "lakeside", "lakefront", "riverside", "river"]
        forest_kw = ["forest", "bush", "native bush", "woodland", "tree"]
        city_kw = ["cbd", "central", "metropolitan", "urban", "downtown"]

        if any(kw in text for kw in coast_kw):
            tags.append("coast")
        elif any(kw in text for kw in mountain_kw):
            tags.append("mountain")
        elif any(kw in text for kw in lake_kw):
            tags.append("lake")
        elif any(kw in text for kw in forest_kw):
            tags.append("forest")
        elif any(kw in text for kw in city_kw):
            tags.append("city")
        else:
            tags.append("rural")

        # ── 3. 특성 태그 (links / resort / local) ──
        if "links" in text:
            tags.append("links")
        elif "resort" in text or any(t in types for t in ["resort_hotel", "lodging"]):
            tags.append("resort")
        else:
            tags.append("local")

        return sorted(tags)

    # ----------------------------------------------------------
    # 내보내기
    # ----------------------------------------------------------

    def export_json(self, filename: str = "nz_golf_courses.json") -> str:
        """JSON 파일로 내보내기."""
        courses_list = self._build_export_list()

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(courses_list, f, ensure_ascii=False, indent=2)

        print(f"\n  Saved {len(courses_list)} courses to {filename}")
        return filename

    def export_csv(self, filename: str = "nz_golf_courses.csv") -> str:
        """CSV 파일로 내보내기."""
        courses_list = self._build_export_list()
        if not courses_list:
            print("  No data to export.")
            return filename

        fieldnames = [
            "id", "name", "place_id", "address", "lat", "lng",
            "island", "region", "phone", "website_url",
            "rating", "review_count", "opening_hours",
            "google_maps_url", "photo_url",
            "description", "price_min_nzd", "price_max_nzd",
            "tags", "booking_url",
        ]

        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(courses_list)

        print(f"  Saved {len(courses_list)} courses to {filename}")
        return filename

    def _build_export_list(self) -> List[Dict]:
        """내보내기용 코스 리스트를 생성한다. 내부 필드 제거 및 ID 부여."""
        courses_list = []
        for idx, course in enumerate(
            sorted(self.courses.values(), key=lambda c: c.get("name", "")), 1
        ):
            export = {
                "id": idx,
                "name": course.get("name", ""),
                "place_id": course.get("place_id", ""),
                "address": course.get("address", ""),
                "lat": course.get("lat"),
                "lng": course.get("lng"),
                "island": course.get("island", ""),
                "region": course.get("region", ""),
                "phone": course.get("phone"),
                "website_url": course.get("website_url"),
                "rating": course.get("rating"),
                "review_count": course.get("review_count"),
                "opening_hours": course.get("opening_hours"),
                "google_maps_url": course.get("google_maps_url"),
                "photo_url": course.get("photo_url"),
                "description": course.get("description"),
                "price_min_nzd": course.get("price_min_nzd"),
                "price_max_nzd": course.get("price_max_nzd"),
                "tags": course.get("tags", []),
                "booking_url": course.get("booking_url"),
            }
            courses_list.append(export)
        return courses_list

    # ----------------------------------------------------------
    # 통계
    # ----------------------------------------------------------

    def print_statistics(self) -> None:
        """수집된 데이터의 통계를 출력한다."""
        courses = list(self.courses.values())
        total = len(courses)
        if total == 0:
            print("\n  No courses collected.")
            return

        print("\n[Statistics]")
        print("=" * 60)
        print(f"  Total courses: {total}")

        # 섬별 분포
        islands: Dict[str, int] = {}
        for c in courses:
            isl = c.get("island", "Unknown") or "Unknown"
            islands[isl] = islands.get(isl, 0) + 1

        print("\n  By island:")
        for isl, count in sorted(islands.items()):
            print(f"    {isl}: {count}")

        # 지역별 분포
        regions: Dict[str, int] = {}
        for c in courses:
            reg = c.get("region", "Unknown") or "Unknown"
            regions[reg] = regions.get(reg, 0) + 1

        print("\n  By region:")
        for reg, count in sorted(regions.items(), key=lambda x: -x[1]):
            print(f"    {reg}: {count}")

        # 필드 완성도
        fields = [
            "name", "address", "phone", "website_url",
            "rating", "review_count", "google_maps_url", "photo_url",
            "description", "price_min_nzd", "price_max_nzd", "booking_url",
        ]
        print("\n  Field completion:")
        for field in fields:
            filled = sum(1 for c in courses if c.get(field))
            pct = filled / total * 100
            print(f"    {field}: {filled}/{total} ({pct:.0f}%)")

    # ----------------------------------------------------------
    # 진행상황 저장 / 복원
    # ----------------------------------------------------------

    def _save_progress(self) -> None:
        """현재 상태를 파일에 저장하여 중단 시 이어서 수집 가능."""
        data = {
            "saved_at": datetime.now().isoformat(),
            "api_call_count": self.api_call_count,
            "courses": self.courses,
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_progress(self) -> bool:
        """저장된 진행상황을 불러온다. 성공 시 True."""
        if not os.path.exists(PROGRESS_FILE):
            return False

        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.courses = data.get("courses", {})
            self.api_call_count = data.get("api_call_count", 0)
            saved_at = data.get("saved_at", "unknown")
            print(f"  Resumed from progress file (saved: {saved_at})")
            print(f"  Loaded {len(self.courses)} courses, {self.api_call_count} API calls made")
            return True
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Failed to load progress: {e}")
            return False

    # ----------------------------------------------------------
    # HTTP 헬퍼
    # ----------------------------------------------------------

    def _api_post(self, url: str, json_body: Dict, extra_headers: Optional[Dict] = None) -> Optional[Dict]:
        """POST 요청을 보내고 JSON 응답을 반환한다."""
        headers = dict(self.session.headers)
        if extra_headers:
            headers.update(extra_headers)

        self.api_call_count += 1
        try:
            resp = self.session.post(url, json=json_body, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            body = ""
            if e.response is not None:
                try:
                    body = e.response.json().get("error", {}).get("message", "")
                except Exception:
                    body = e.response.text[:200]
            print(f"\n    API Error (HTTP {status}): {body}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"\n    Request Error: {e}")
            return None

    def _api_get(self, url: str, extra_headers: Optional[Dict] = None) -> Optional[Dict]:
        """GET 요청을 보내고 JSON 응답을 반환한다."""
        headers = dict(self.session.headers)
        if extra_headers:
            headers.update(extra_headers)

        self.api_call_count += 1
        try:
            resp = self.session.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            body = ""
            if e.response is not None:
                try:
                    body = e.response.json().get("error", {}).get("message", "")
                except Exception:
                    body = e.response.text[:200]
            print(f"\n    API Error (HTTP {status}): {body}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"\n    Request Error: {e}")
            return None


# ============================================================
# 메인
# ============================================================


def get_api_key(args) -> str:
    """API 키를 가져온다: CLI 인자 > 환경변수 > 사용자 입력."""
    if args.api_key:
        return args.api_key

    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if key:
        return key

    print("Google Places API key not found.")
    print("Set the GOOGLE_PLACES_API_KEY environment variable or use --api-key.\n")
    key = input("Enter API key (or press Enter to exit): ").strip()
    if not key:
        sys.exit(0)
    return key


def main():
    parser = argparse.ArgumentParser(description="NZ Golf Course Crawler (Google Places API)")
    parser.add_argument("--api-key", type=str, default=None, help="Google Places API key")
    parser.add_argument("--test", action="store_true", help="Test mode: Auckland only")
    parser.add_argument("--resume", action="store_true", help="Resume from saved progress")
    parser.add_argument("--skip-details", action="store_true", help="Skip Phase 2 (Place Details)")
    parser.add_argument("--scrape-websites", action="store_true", help="Phase 4: Scrape course websites for pricing & booking")
    parser.add_argument("--output", type=str, default="nz_golf_courses", help="Output filename prefix")
    args = parser.parse_args()

    print("=" * 60)
    print("  NZ Golf Course Crawler - Google Places API (New)")
    print("=" * 60)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    api_key = get_api_key(args)
    crawler = NZGolfCourseCrawler(api_key)

    # 이어하기 모드
    if args.resume:
        print("\n[Resume mode]")
        if not crawler.load_progress():
            print("  No progress file found. Starting fresh.\n")

    # 검색 대상 지역 결정
    regions = ["Auckland"] if args.test else NZ_REGIONS
    if args.test:
        print("\n  ** TEST MODE: Auckland only **")

    # Phase 1: Text Search (이미 로드한 코스가 없을 때만)
    if not crawler.courses:
        crawler.search_all_regions(regions)
        crawler._save_progress()
    else:
        print(f"\n  Skipping Text Search (already have {len(crawler.courses)} courses)")

    # Phase 2: Place Details
    if not args.skip_details:
        crawler.enrich_all_courses()
        crawler._save_progress()
    else:
        print("\n  Skipping Place Details (--skip-details)")

    # Phase 3: Region classification
    crawler.classify_regions()

    # Phase 4: Website scraping (optional)
    if args.scrape_websites:
        crawler.scrape_websites()
        crawler._save_progress()
    else:
        print("\n  Skipping website scraping (use --scrape-websites to enable)")

    # Phase 5: Fill missing data (description + price estimates)
    crawler.fill_missing_data()

    # Phase 6: Tag generation (always 3 tags: price + view + type)
    crawler.generate_all_tags()

    # Statistics
    crawler.print_statistics()

    # Export
    print("\n[Export]")
    print("=" * 60)
    json_file = crawler.export_json(f"{args.output}.json")
    csv_file = crawler.export_csv(f"{args.output}.csv")

    print(f"\n  API calls made: {crawler.api_call_count}")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("\nDone!")


if __name__ == "__main__":
    main()

# 뉴질랜드 전체 골프장 크롤링 시스템 가이드

## 📋 개요

이 시스템은 뉴질랜드의 **모든 골프장**(약 400+개)의 정보를 자동으로 수집하는 종합 크롤링 도구입니다.

### 주요 데이터 소스
1. **All Square Golf** - 뉴질랜드 전체 골프장 디렉토리
2. **GolfPass** - 426개 코스 리스트
3. **Golfshake** - 415개 코스 데이터
4. **Google Places API** - 좌표, 평점, 사진, 리뷰 (선택사항)

## 🚀 빠른 시작

### 1단계: 환경 설정

```bash
# 필수 라이브러리 설치
pip install requests beautifulsoup4 lxml

# 파일 확인
ls -la *.py
```

필요한 파일들:
- `comprehensive_crawler.py` - 메인 크롤러
- `google_places_enricher.py` - Google API 보강 도구
- `master_crawler.py` - 전체 파이프라인 관리

### 2단계: 기본 크롤링 실행

**옵션 A: 빠른 실행 (Google API 없이)**
```bash
python master_crawler.py --quick
```

**옵션 B: 대화형 모드**
```bash
python master_crawler.py
# 프롬프트에 따라 선택
```

**옵션 C: Google API 포함 (권장)**
```bash
python master_crawler.py --with-google YOUR_GOOGLE_API_KEY
```

### 3단계: 결과 확인

```bash
# JSON 파일 확인
cat nz_all_golf_courses.json | jq '.[0]'

# CSV 파일 열기
open nz_all_golf_courses.csv
```

## 📁 파일 구조

```
.
├── comprehensive_crawler.py      # 메인 크롤러
├── google_places_enricher.py     # Google Places API 통합
├── master_crawler.py             # 파이프라인 관리자
│
├── nz_all_golf_courses.json      # [출력] 전체 코스 데이터 (JSON)
├── nz_all_golf_courses.csv       # [출력] 전체 코스 데이터 (CSV)
└── nz_golf_courses_enriched.json # [출력] Google API 보강 데이터
```

## 🔧 상세 사용법

### 1. 웹 크롤링만 실행

```python
from comprehensive_crawler import ComprehensiveNZGolfCrawler

crawler = ComprehensiveNZGolfCrawler()

# 전체 크롤링
crawler.crawl_all_sources()

# 또는 테스트용 (처음 50개만)
crawler.crawl_all_sources(max_courses=50)

# 결과 저장
crawler.export_to_json('my_courses.json')
crawler.export_to_csv('my_courses.csv')

# 통계 출력
crawler.generate_statistics()
```

### 2. Google Places API 보강

#### Google API 키 발급 방법

1. **Google Cloud Console** 접속
   ```
   https://console.cloud.google.com/
   ```

2. **새 프로젝트 생성** (또는 기존 프로젝트 선택)

3. **APIs & Services > Library** 메뉴에서 활성화:
   - Places API
   - Geocoding API (선택사항)
   - Maps JavaScript API (선택사항)

4. **APIs & Services > Credentials** 메뉴에서:
   - "CREATE CREDENTIALS" 클릭
   - "API key" 선택
   - 생성된 키 복사

5. **API 키 제한 설정** (보안):
   - Application restrictions: None (또는 IP 주소 지정)
   - API restrictions: "Restrict key" 선택
   - Places API만 허용

#### API 사용

```python
from google_places_enricher import GooglePlacesEnricher
import json

# 크롤링한 데이터 로드
with open('nz_all_golf_courses.json', 'r') as f:
    courses = json.load(f)

# Google Places로 보강
enricher = GooglePlacesEnricher('YOUR_API_KEY_HERE')
enriched_courses = enricher.enrich_courses_batch(courses)

# 결과 저장
with open('enriched_courses.json', 'w') as f:
    json.dump(enriched_courses, f, indent=2, ensure_ascii=False)
```

### 3. 커스텀 크롤링

특정 지역만 크롤링하거나 추가 데이터 소스 통합:

```python
class CustomCrawler(ComprehensiveNZGolfCrawler):
    
    def crawl_queenstown_only(self):
        """퀸스타운 지역만 크롤링"""
        all_courses = self.crawl_allsquare_courses()
        
        queenstown_courses = [
            c for c in all_courses 
            if 'queenstown' in c['name'].lower()
        ]
        
        return queenstown_courses
    
    def add_custom_source(self, url):
        """커스텀 데이터 소스 추가"""
        # 구현...
        pass

# 사용
crawler = CustomCrawler()
courses = crawler.crawl_queenstown_only()
```

## 📊 수집되는 데이터

### 기본 정보 (웹 크롤링)
- ✅ 코스 이름
- ✅ 주소
- ✅ 전화번호
- ✅ 웹사이트 URL
- ✅ 섬 (북섬/남섬)
- ✅ 지역

### 추가 정보 (Google Places API)
- ✅ 정확한 좌표 (위도/경도)
- ✅ Google 평점 (1-5)
- ✅ 리뷰 수
- ✅ 가격 레벨 (0-4)
- ✅ 운영 시간
- ✅ 사진 URL
- ✅ Google Maps URL

### 수동 보완 필요
- ⏳ 정확한 그린피 가격
- ⏳ 코스 설명
- ⏳ 태그/카테고리
- ⏳ 예약 링크
- ⏳ 고품질 이미지

## 🎯 데이터 품질 관리

### 자동 검증

시스템은 다음 항목을 자동으로 검증합니다:

1. **필수 필드**: id, name
2. **좌표 범위**: -47° ~ -34° (위도), 166° ~ 179° (경도)
3. **가격 범위**: 0 ~ 1000 NZD
4. **중복 제거**: 정규화된 이름으로 중복 체크

### 수동 검증 체크리스트

```bash
# 1. 총 코스 수 확인 (약 400개 예상)
jq 'length' nz_all_golf_courses.json

# 2. 좌표가 있는 코스 수
jq '[.[] | select(.lat != null)] | length' nz_all_golf_courses.json

# 3. 중복 확인
jq -r '.[].name' nz_all_golf_courses.json | sort | uniq -d

# 4. 섬별 분포
jq -r '.[].island' nz_all_golf_courses.json | sort | uniq -c

# 5. 누락된 주소 찾기
jq -r '.[] | select(.address == null or .address == "") | .name' nz_all_golf_courses.json
```

## ⚙️ 고급 설정

### 크롤링 속도 조절

```python
# comprehensive_crawler.py에서

# 서버 부하 방지 대기 시간 조정
time.sleep(1)  # 기본값: 1초
time.sleep(2)  # 보수적: 2초
time.sleep(0.5)  # 빠르게: 0.5초 (주의!)
```

### 타임아웃 설정

```python
# 느린 웹사이트를 위한 타임아웃 증가
response = requests.get(url, timeout=10)  # 기본값
response = requests.get(url, timeout=30)  # 증가
```

### 동시 처리 (병렬화)

```python
from concurrent.futures import ThreadPoolExecutor

def crawl_with_threads(courses, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(extract_course_details, courses)
    return list(results)
```

## 🚨 문제 해결

### 일반적인 오류

**1. "Connection refused" 또는 "Timeout"**
```bash
# 해결: 대기 시간 증가
time.sleep(2)  # comprehensive_crawler.py에서
```

**2. "Too Many Requests" (429 에러)**
```bash
# 해결: 속도 제한 추가
time.sleep(5)  # 더 긴 대기 시간
# 또는 배치 크기 감소
```

**3. Google API "OVER_QUERY_LIMIT"**
```bash
# 해결: 쿼리 속도 줄이기
time.sleep(0.2)  # google_places_enricher.py에서
```

**4. "No such file or directory"**
```bash
# 해결: 올바른 디렉토리에서 실행
cd /path/to/project
python master_crawler.py
```

### 로그 활성화

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)
```

## 📈 성능 최적화

### 예상 실행 시간

- **웹 크롤링**: 약 30-60분 (400개 코스, 1초 대기)
- **Google Places API**: 약 40-80분 (400개 코스, 0.1초 대기)
- **총 소요 시간**: 약 1-2시간

### 메모리 사용량

- **Python 프로세스**: 약 50-100 MB
- **출력 파일**: JSON ~2-5 MB, CSV ~1-3 MB

### API 비용 (Google Places)

- **Places API**: $17/1000 requests
- **400개 코스** × 2 requests = 800 requests
- **예상 비용**: 약 $14 USD

무료 크레딧: 매월 $200 (신규 사용자)

## 🔄 정기 업데이트

### Cron 작업 설정

```bash
# 매주 일요일 오전 2시 실행
0 2 * * 0 cd /path/to/project && python master_crawler.py --quick

# 또는 매월 1일
0 2 1 * * cd /path/to/project && python master_crawler.py --with-google API_KEY
```

### 변경 감지

```python
# 이전 데이터와 비교
def detect_changes(old_file, new_file):
    with open(old_file, 'r') as f:
        old_data = json.load(f)
    with open(new_file, 'r') as f:
        new_data = json.load(f)
    
    old_names = {c['name'] for c in old_data}
    new_names = {c['name'] for c in new_data}
    
    added = new_names - old_names
    removed = old_names - new_names
    
    print(f"추가됨: {len(added)}")
    print(f"제거됨: {len(removed)}")
```

## 📝 데이터 활용

### 앱 통합 예제

```javascript
// React Native에서 사용
import golfCourses from './nz_all_golf_courses.json';

function GolfCourseList() {
  return (
    <FlatList
      data={golfCourses}
      keyExtractor={item => item.id}
      renderItem={({item}) => (
        <GolfCourseCard course={item} />
      )}
    />
  );
}
```

### 지도에 표시

```javascript
// 좌표가 있는 코스만 필터링
const coursesWithCoords = golfCourses.filter(
  c => c.lat && c.lng
);

// 지도 마커 생성
coursesWithCoords.map(course => (
  <Marker
    key={course.id}
    coordinate={{
      latitude: course.lat,
      longitude: course.lng
    }}
    title={course.name}
  />
))
```

### 검색 및 필터링

```javascript
// 지역별 필터
const aucklandCourses = golfCourses.filter(
  c => c.region === 'Auckland'
);

// 가격대별 필터
const premiumCourses = golfCourses.filter(
  c => c.price_max_nzd > 200
);

// 평점별 정렬
const topRated = golfCourses
  .filter(c => c.rating)
  .sort((a, b) => b.rating - a.rating);
```

## 🤝 기여 및 개선

### 데이터 품질 향상

1. **누락된 정보 보완**: 가격, 설명, 이미지 URL
2. **태그 추가**: premium, links, mountain, ocean 등
3. **새로운 소스 통합**: 추가 웹사이트 크롤링
4. **오류 수정**: 잘못된 좌표, 주소 등

### 코드 개선

1. **에러 처리 강화**
2. **재시도 로직 추가**
3. **캐싱 구현**
4. **동시 처리 최적화**

## 📞 지원

문제가 발생하면:
1. `crawler.log` 파일 확인
2. GitHub Issues에 문의
3. 이메일: support@example.com

---

**버전**: 2.0  
**최종 업데이트**: 2025년 2월 10일  
**라이선스**: MIT

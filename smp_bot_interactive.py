"""
KPX SMP 대화형 텔레그램 봇

사용자가 텔레그램에서 원하는 날짜/기간을 입력하면 
해당 SMP 데이터를 조회하여 전송하는 봇입니다.

명령어:
  /start - 봇 시작 및 사용법 안내
  /smp - 최신 SMP 데이터 조회
  /today - 오늘 SMP 데이터
  /week - 이번주 SMP 데이터
  
또는 직접 날짜 입력:
  "오늘"
  "이번주"
  "2025-09-24"
  "2024-01-01~2024-03-31" (과거 기간 조회)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
from datetime import datetime, timedelta
import os
from typing import Optional
import re
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# .env 파일에서 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smp_bot_interactive.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SMPCrawler:
    """KPX 웹사이트에서 SMP 데이터를 크롤링하는 클래스"""
    
    def __init__(self):
        """초기화 메서드"""
        # 육지 SMP 데이터
        self.base_url = "https://new.kpx.or.kr/smpInland.es?mid=a10606080100&device=pc"
        self.api_url = "https://new.kpx.or.kr/smpInland.es"
        
        # 제주 SMP 데이터 (하루전 시장)
        self.jeju_base_url = "https://new.kpx.or.kr/smpInland.es?mid=a10606080200&device=pc"
        self.jeju_api_url = "https://new.kpx.or.kr/smpInland.es"
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://new.kpx.or.kr/'
        }
        logger.info("SMPCrawler 초기화 완료 (육지 + 제주)")
    
    def fetch_smp_data(self, target_date: Optional[str] = None, is_jeju: bool = False) -> Optional[pd.DataFrame]:
        """
        KPX 웹사이트에서 SMP 데이터를 가져오는 메서드
        
        Args:
            target_date: 조회할 날짜 (YYYY-MM-DD 형식), None이면 최신 데이터
                        선택한 날짜를 기준으로 일주일치 데이터 반환
            is_jeju: True면 제주 데이터, False면 육지 데이터 (기본값)
        
        Returns:
            pd.DataFrame: SMP 데이터 (실패시 None)
        """
        try:
            from io import StringIO
            
            # 육지/제주에 따라 URL 선택
            if is_jeju:
                base_url = self.jeju_base_url
                api_url = self.jeju_api_url
                mid_param = 'a10606080200'  # 제주 mid
                region = "제주"
                logger.info("🏝 제주 SMP 데이터 조회")
            else:
                base_url = self.base_url
                api_url = self.api_url
                mid_param = 'a10606080100'  # 육지 mid
                region = "육지"
                logger.info("🌍 육지 SMP 데이터 조회")
            
            # 날짜 지정 시 POST 요청, 아니면 GET 요청
            if target_date:
                logger.info(f"특정 날짜 기준 {region} SMP 데이터 조회: {target_date}")
                
                # 세션 생성
                session = requests.Session()
                
                # 먼저 GET 요청으로 CSRF 토큰 가져오기
                logger.info("CSRF 토큰 획득을 위한 GET 요청")
                get_response = session.get(base_url, headers=self.headers, timeout=30)
                get_soup = BeautifulSoup(get_response.content, 'html.parser')
                
                # CSRF 토큰 찾기
                csrf_token = ''
                csrf_input = get_soup.find('input', {'name': '_csrf'})
                if csrf_input:
                    csrf_token = csrf_input.get('value', '')
                    logger.info(f"CSRF 토큰 획득 성공")
                
                # POST 데이터 구성 (웹사이트의 form과 동일하게)
                post_data = {
                    'issue_date': target_date,
                    '_csrf': csrf_token
                }
                
                # POST 요청으로 날짜별 데이터 조회
                logger.info(f"POST 요청: {api_url}")
                logger.info(f"날짜 파라미터: {target_date}")
                
                response = session.post(
                    api_url,
                    data=post_data,
                    headers=self.headers,
                    params={'mid': mid_param, 'device': 'pc'},
                    timeout=30
                )
            else:
                # 최신 데이터 조회 (최근 7일)
                logger.info(f"최신 {region} SMP 데이터 크롤링: {base_url}")
                response = requests.get(base_url, headers=self.headers, timeout=30)
            
            response.raise_for_status()
            logger.info(f"웹페이지 요청 성공 (상태코드: {response.status_code})")
            
            # HTML 파싱
            soup = BeautifulSoup(response.content, 'html.parser')
            logger.info("HTML 파싱 완료")
            
            # 테이블 찾기 (class가 conTable tdCenter인 테이블)
            table = soup.find('table', {'class': 'conTable'})
            
            if not table:
                logger.error("conTable 테이블을 찾을 수 없습니다")
                return None
            
            # 테이블 데이터 추출
            df = pd.read_html(StringIO(str(table)))[0]
            logger.info(f"데이터 추출 성공 (shape: {df.shape})")
            logger.info(f"컬럼: {df.columns.tolist()}")
            
            # 데이터 유효성 검증
            if df.shape[0] < 24:  # 24시간 데이터가 없으면
                logger.warning(f"시간대별 데이터가 부족합니다 (행 수: {df.shape[0]})")
            
            return df
            
        except Exception as e:
            logger.error(f"데이터 크롤링 중 오류 발생: {e}", exc_info=True)
            return None
    
    def format_smp_data(self, df: pd.DataFrame, date_filter: Optional[str] = None, is_jeju: bool = False) -> str:
        """
        SMP 데이터를 텔레그램 메시지 형식으로 포맷팅
        
        Args:
            df: SMP 데이터프레임
            date_filter: 날짜 필터 (예: "09.30", "이번주", "오늘")
            is_jeju: True면 제주 데이터, False면 육지 데이터
            
        Returns:
            str: 포맷팅된 메시지
        """
        try:
            logger.info(f"데이터 포맷팅 시작 (필터: {date_filter}, 제주: {is_jeju})")
            
            if df is None or df.empty:
                return "⚠️ 데이터를 가져올 수 없습니다."
            
            # 메시지 헤더 (지역 정보 포함)
            today = datetime.now().strftime('%Y년 %m월 %d일')
            region_icon = "🏝" if is_jeju else "🌍"
            region_name = "제주" if is_jeju else "육지"
            
            message = f"{region_icon} <b>KPX SMP 데이터 - {region_name}</b>\n"
            message += f"🗓 조회일시: {today}\n"
            message += "=" * 40 + "\n\n"
            
            # 시간대별 데이터 추출 (1h~24h 행)
            hourly_data = df[df.iloc[:, 0].astype(str).str.contains('h$', regex=True, na=False)]
            
            logger.info(f"시간대별 데이터 행 수: {len(hourly_data)}")
            
            if hourly_data.empty:
                logger.error("시간대별 데이터를 찾을 수 없습니다")
                logger.error(f"전체 데이터:\n{df}")
                return message + "⚠️ 시간대별 데이터를 찾을 수 없습니다."
            
            # 날짜 컬럼 가져오기 (첫 번째 컬럼은 '구분'이므로 제외)
            date_columns = list(df.columns[1:])
            
            # 날짜 필터링
            if date_filter:
                # 특정 날짜가 입력되면 일주일 전체를 보여줌
                logger.info(f"날짜 필터 '{date_filter}'로 조회 - 일주일 전체 표시")
                # 일주일 전체 데이터 표시 (모든 컬럼)
                date_columns = date_columns
            else:
                # 기본: 최근 3일
                date_columns = date_columns[-3:] if len(date_columns) > 3 else date_columns
            
            logger.info(f"선택된 날짜: {date_columns}")
            
            # 각 날짜별로 데이터 표시
            for date_col in date_columns:
                message += f"<b>📅 {date_col}</b>\n"
                message += "-" * 30 + "\n"
                
                # 통계 정보
                try:
                    max_row = df[df.iloc[:, 0] == '최대']
                    min_row = df[df.iloc[:, 0] == '최소']
                    avg_row = df[df.iloc[:, 0] == '가중평균']
                    
                    if not max_row.empty and date_col in max_row.columns:
                        max_val = max_row[date_col].values[0]
                        message += f"🔴 최대: {max_val} 원/kWh\n"
                    
                    if not min_row.empty and date_col in min_row.columns:
                        min_val = min_row[date_col].values[0]
                        message += f"🟢 최소: {min_val} 원/kWh\n"
                    
                    if not avg_row.empty and date_col in avg_row.columns:
                        avg_val = avg_row[date_col].values[0]
                        message += f"📊 평균: {avg_val} 원/kWh\n"
                    
                    message += "\n"
                except Exception as e:
                    logger.warning(f"통계 정보 추출 중 오류: {e}")
                
                # 시간대별 상세 데이터
                for idx, row in hourly_data.iterrows():
                    time_slot = row.iloc[0]
                    value = row[date_col]
                    
                    if pd.notna(value):
                        try:
                            val_float = float(value)
                            # 값에 따라 이모지 추가
                            if val_float > 120:
                                emoji = "🔴"
                            elif val_float > 90:
                                emoji = "🟡"
                            else:
                                emoji = "🟢"
                            message += f"{emoji} {time_slot:>3}: {value:>7} 원/kWh\n"
                        except:
                            message += f"  {time_slot:>3}: {value:>7} 원/kWh\n"
                
                message += "\n"
            
            message += "=" * 40 + "\n"
            message += "📌 출처: KPX 한국전력거래소\n"
            message += f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            
            logger.info(f"메시지 포맷팅 완료 (길이: {len(message)})")
            return message
            
        except Exception as e:
            logger.error(f"포맷팅 중 오류: {e}")
            return f"❌ 오류가 발생했습니다: {str(e)}"
    
    def _filter_dates(self, date_columns: list, date_filter: str) -> list:
        """
        날짜 필터에 맞는 컬럼 선택
        
        Args:
            date_columns: 전체 날짜 컬럼 리스트
            date_filter: 필터 문자열
            
        Returns:
            list: 필터링된 컬럼 리스트
        """
        try:
            date_filter_lower = date_filter.strip().lower()
            
            # "오늘" 처리
            if date_filter_lower in ['오늘', 'today']:
                today_str = datetime.now().strftime('%m.%d')
                logger.info(f"오늘 날짜 검색: {today_str}")
                filtered = [col for col in date_columns if today_str in str(col)]
                return filtered if filtered else date_columns[-1:]  # 없으면 마지막 날짜
            
            # "이번주" 처리
            elif date_filter_lower in ['이번주', 'week', '주간']:
                logger.info("이번주 데이터 반환 (전체)")
                return date_columns  # 모든 데이터 반환 (최근 7일)
            
            # YYYY-MM-DD 형식 파싱
            parsed_date = self._parse_date(date_filter)
            if parsed_date:
                # YYYY-MM-DD를 MM.DD 형식으로 변환
                try:
                    dt = datetime.strptime(parsed_date, '%Y-%m-%d')
                    target_str = dt.strftime('%m.%d')
                    logger.info(f"날짜 변환: {parsed_date} -> {target_str}")
                    
                    # 해당 날짜 찾기
                    filtered = [col for col in date_columns if target_str in str(col)]
                    
                    if filtered:
                        logger.info(f"날짜 매칭 성공: {filtered}")
                        return filtered
                    else:
                        logger.warning(f"{target_str} 날짜를 찾을 수 없습니다. 최근 3일 반환")
                        return date_columns[-3:]
                except:
                    pass
            
            # 기본: 최근 3일
            logger.warning(f"알 수 없는 필터: {date_filter}. 최근 3일 반환")
            return date_columns[-3:]
                
        except Exception as e:
            logger.error(f"날짜 필터링 중 오류: {e}")
            return date_columns[-3:]


class InteractiveSMPBot:
    """대화형 SMP 텔레그램 봇"""
    
    def __init__(self, token: str):
        """
        초기화 메서드
        
        Args:
            token: 텔레그램 봇 토큰
        """
        self.crawler = SMPCrawler()
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
        logger.info("InteractiveSMPBot 초기화 완료")
    
    def _setup_handlers(self):
        """명령어 핸들러 설정"""
        # 명령어 핸들러
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("smp", self.smp_command))
        self.application.add_handler(CommandHandler("today", self.today_command))
        self.application.add_handler(CommandHandler("week", self.week_command))
        self.application.add_handler(CommandHandler("jeju", self.jeju_command))  # 제주 추가
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # 일반 메시지 핸들러 (날짜 입력 처리)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        logger.info("핸들러 설정 완료 (육지 + 제주)")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /start 명령어 처리
        봇 사용법 안내
        """
        logger.info(f"사용자 {update.effective_user.id}가 /start 명령어 실행")
        
        welcome_message = """
🤖 <b>KPX SMP 데이터 봇에 오신 것을 환영합니다!</b>

이 봇은 한국전력거래소(KPX)의 시간대별 SMP(계통한계가격) 데이터를 제공합니다.

📝 <b>사용 방법:</b>

<b>명령어:</b>
  /smp - 최신 육지 SMP 데이터
  /today - 오늘 데이터
  /week - 이번주 데이터
  /jeju - 제주 SMP 데이터 🏝
  /help - 도움말

<b>직접 입력:</b>
  "오늘" - 오늘 데이터
  "이번주" - 이번주 데이터
  "제주" - 제주 SMP 데이터 🏝
  "09.30" - 특정 날짜 데이터
  "2025-09-30" - 특정 날짜 (전체 형식)

💡 <b>예시:</b>
  "오늘" - 오늘 육지 SMP 조회
  "제주" - 제주 SMP 조회
  "09.24" - 9월 24일 데이터
  "2025-09-24" - 2025년 9월 24일

🎯 원하는 날짜와 지역을 선택해서 조회하세요! 👇
        """
        
        await update.message.reply_text(welcome_message, parse_mode='HTML')
        logger.info("환영 메시지 전송 완료")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /help 명령어 처리
        도움말 표시
        """
        logger.info(f"사용자 {update.effective_user.id}가 /help 명령어 실행")
        
        help_message = """
📖 <b>SMP 데이터 봇 사용 가이드</b>

<b>1. 명령어 사용:</b>
  /smp - 최신 육지 SMP 데이터
  /today - 오늘 데이터
  /week - 이번주 전체 데이터
  /jeju - 제주 SMP 데이터 🏝

<b>2. 텍스트로 입력:</b>
  • "오늘" 또는 "today"
  • "이번주" 또는 "week"
  • "제주" - 제주 SMP 데이터 🏝
  • "09.30" (월.일 형식)
  • "2025-09-30" (전체 날짜, YYYY-MM-DD)

<b>3. 날짜 선택 조회:</b>
  • 원하는 날짜를 YYYY-MM-DD 또는 MM.DD 형식으로 입력
  • 예: "2025-09-24" 또는 "09.24"
  • 선택한 날짜 기준 일주일치 데이터 표시

<b>4. 지역 선택:</b>
  • 기본: 육지 SMP (🌍)
  • "제주" 또는 /jeju: 제주 SMP (🏝)

<b>💡 팁:</b>
  • 간단하게 "오늘"만 입력해도 됩니다
  • 날짜는 여러 형식으로 입력 가능합니다
  
<b>📊 데이터 정보:</b>
  • 🔴 빨강: 높은 가격 (120원/kWh 이상)
  • 🟡 노랑: 중간 가격 (90-120원/kWh)
  • 🟢 초록: 낮은 가격 (90원/kWh 미만)

궁금한 점이 있으면 메시지를 보내주세요!
        """
        
        await update.message.reply_text(help_message, parse_mode='HTML')
        logger.info("도움말 전송 완료")
    
    async def smp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /smp 명령어 처리
        최신 SMP 데이터 조회
        """
        logger.info(f"사용자 {update.effective_user.id}가 /smp 명령어 실행")
        await self._send_smp_data(update, None)
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /today 명령어 처리
        오늘 SMP 데이터 조회
        """
        logger.info(f"사용자 {update.effective_user.id}가 /today 명령어 실행")
        await self._send_smp_data(update, "오늘")
    
    async def week_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /week 명령어 처리
        이번주 SMP 데이터 조회
        """
        logger.info(f"사용자 {update.effective_user.id}가 /week 명령어 실행")
        await self._send_smp_data(update, "이번주")
    
    async def jeju_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /jeju 명령어 처리
        제주 SMP 데이터 조회
        """
        logger.info(f"사용자 {update.effective_user.id}가 /jeju 명령어 실행")
        await self._send_smp_data(update, "제주", is_jeju=True)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        일반 메시지 처리
        사용자가 입력한 날짜로 SMP 데이터 조회
        """
        user_input = update.message.text.strip()
        logger.info(f"사용자 {update.effective_user.id}의 메시지: {user_input}")
        
        # 인사말 처리
        greetings = ['안녕', '안녕하세요', 'hi', 'hello', '헬로']
        if user_input.lower() in greetings:
            await update.message.reply_text(
                "안녕하세요! 👋\n"
                "SMP 데이터를 조회하려면:\n"
                "• '오늘' 또는 '이번주' 입력\n"
                "• 날짜 입력 (예: 09.30)\n"
                "• '제주' - 제주 데이터 조회\n"
                "• /help 로 도움말 확인"
            )
            return
        
        # 제주 데이터 조회
        if user_input.lower() in ['제주', 'jeju']:
            await self._send_smp_data(update, None, is_jeju=True)
            return
        
        # 육지 SMP 데이터 조회
        await self._send_smp_data(update, user_input)
    
    def _parse_date(self, date_filter: str) -> Optional[str]:
        """
        날짜 필터를 파싱하여 날짜 추출
        
        Args:
            date_filter: 날짜 필터 문자열
            
        Returns:
            str: YYYY-MM-DD 형식 날짜 or None
        """
        try:
            # 단일 날짜 YYYY-MM-DD 형식 체크
            single_pattern = r'^(\d{4}-\d{2}-\d{2})$'
            single_match = re.match(single_pattern, date_filter.strip())
            
            if single_match:
                date = single_match.group(1)
                logger.info(f"날짜 파싱 성공: {date}")
                return date
            
            # MM.DD 형식을 YYYY-MM-DD로 변환
            short_pattern = r'^(\d{2})\.(\d{2})$'
            short_match = re.match(short_pattern, date_filter.strip())
            
            if short_match:
                month = short_match.group(1)
                day = short_match.group(2)
                year = datetime.now().year
                date = f"{year}-{month}-{day}"
                logger.info(f"짧은 날짜 형식 변환: {date_filter} -> {date}")
                return date
            
            return None
            
        except Exception as e:
            logger.error(f"날짜 파싱 중 오류: {e}")
            return None
    
    async def _send_smp_data(self, update: Update, date_filter: Optional[str], is_jeju: bool = False):
        """
        SMP 데이터를 조회하고 전송하는 내부 메서드
        
        Args:
            update: 텔레그램 업데이트 객체
            date_filter: 날짜 필터
            is_jeju: True면 제주 데이터, False면 육지 데이터
        """
        try:
            # "조회 중..." 메시지 전송
            region = "🏝 제주" if is_jeju else "🌍 육지"
            status_msg = await update.message.reply_text(f"🔍 {region} SMP 데이터를 조회하고 있습니다...")
            logger.info(f"{region} 데이터 조회 시작 (필터: {date_filter})")
            
            # 날짜 파싱
            target_date = None
            if date_filter:
                target_date = self._parse_date(date_filter)
            
            # 데이터 크롤링 (날짜 기준으로)
            if target_date:
                await status_msg.edit_text(
                    f"🔍 {region} {target_date} 기준 일주일 데이터 조회 중...\n"
                    f"⏳ 잠시만 기다려주세요..."
                )
                logger.info(f"날짜 기준 조회: {target_date}")
                df = self.crawler.fetch_smp_data(target_date, is_jeju)
            else:
                # 최신 데이터 조회
                df = self.crawler.fetch_smp_data(is_jeju=is_jeju)
            
            if df is None:
                await status_msg.edit_text("❌ 데이터 조회에 실패했습니다. 잠시 후 다시 시도해주세요.")
                logger.error("데이터 크롤링 실패")
                return
            
            # 데이터 포맷팅 (지역 정보 포함)
            message = self.crawler.format_smp_data(df, date_filter, is_jeju)
            
            # 메시지 전송
            await status_msg.delete()  # "조회 중..." 메시지 삭제
            
            # 메시지가 너무 길면 분할 전송
            max_length = 4000
            if len(message) > max_length:
                logger.info(f"메시지 길이 초과 ({len(message)}자), 분할 전송")
                parts = self._split_message(message, max_length)
                for i, part in enumerate(parts, 1):
                    await update.message.reply_text(
                        f"[{i}/{len(parts)}]\n{part}",
                        parse_mode='HTML'
                    )
                    logger.info(f"Part {i}/{len(parts)} 전송 완료")
            else:
                await update.message.reply_text(message, parse_mode='HTML')
                logger.info("메시지 전송 완료")
            
        except Exception as e:
            logger.error(f"SMP 데이터 전송 중 오류: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ 오류가 발생했습니다: {str(e)}\n"
                "잠시 후 다시 시도해주세요."
            )
    
    def _split_message(self, message: str, max_length: int) -> list:
        """
        긴 메시지를 여러 개로 분할
        
        Args:
            message: 원본 메시지
            max_length: 최대 길이
            
        Returns:
            list: 분할된 메시지 리스트
        """
        lines = message.split('\n')
        parts = []
        current_part = ""
        
        for line in lines:
            if len(current_part) + len(line) + 1 > max_length:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        
        if current_part:
            parts.append(current_part)
        
        return parts
    
    def run(self):
        """봇 실행"""
        logger.info("봇 실행 시작")
        print("\n" + "=" * 70)
        print("✅ 대화형 SMP 텔레그램 봇이 시작되었습니다!")
        print("=" * 70)
        print("📱 텔레그램에서 봇과 대화를 시작하세요!")
        print("💬 '오늘', '이번주' 또는 날짜를 입력하세요")
        print("❓ 도움말: /help")
        print("⏸️  종료: Ctrl+C")
        print("=" * 70 + "\n")
        
        # 봇 실행
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """메인 함수"""
    logger.info("프로그램 시작")
    
    # 환경변수에서 토큰 가져오기
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # 토큰 검증
    if not token or token == 'YOUR_BOT_TOKEN_HERE':
        logger.error("텔레그램 봇 토큰이 설정되지 않았습니다")
        print("\n❌ 오류: TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요!")
        print("python setup_env.py를 실행하여 설정하세요.\n")
        return
    
    try:
        # 대화형 봇 생성 및 실행
        bot = InteractiveSMPBot(token)
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램 종료")
        print("\n\n👋 프로그램을 종료합니다...")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {e}", exc_info=True)
        print(f"\n❌ 오류 발생: {e}\n")


if __name__ == "__main__":
    main()

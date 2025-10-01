"""
KPX(한국전력거래소) SMP 데이터 크롤러 및 텔레그램 전송 프로그램

이 프로그램은 다음 기능을 수행합니다:
1. KPX 웹사이트에서 시간대별 SMP(계통한계가격) 데이터 크롤링
2. 데이터를 보기 좋게 포맷팅
3. 텔레그램 봇을 통해 메시지 전송
4. 매주 월요일 오전 9시에 자동 실행
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
from datetime import datetime, timedelta
import time
import schedule
import os
from typing import Dict, List, Optional
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
from flask import Flask, jsonify
from threading import Thread

# .env 파일에서 환경변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smp_bot.log', encoding='utf-8'),  # 파일에 로그 저장
        logging.StreamHandler()  # 콘솔에도 출력
    ]
)
logger = logging.getLogger(__name__)


class SMPCrawler:
    """KPX 웹사이트에서 SMP 데이터를 크롤링하는 클래스"""
    
    def __init__(self):
        """초기화 메서드"""
        self.base_url = "https://new.kpx.or.kr/smpInland.es?mid=a10606080100&device=pc"
        self.api_url = "https://new.kpx.or.kr/smpInland.es"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://new.kpx.or.kr/'
        }
        logger.info("SMPCrawler 초기화 완료")
    
    def fetch_smp_data(self, target_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        KPX 웹사이트에서 SMP 데이터를 가져오는 메서드
        
        Args:
            target_date: 조회할 날짜 (YYYY-MM-DD 형식), None이면 최신 데이터
                        해당 날짜를 기준으로 일주일치 데이터 반환
        
        Returns:
            pd.DataFrame: SMP 데이터 (실패시 None)
        """
        try:
            from io import StringIO
            
            # 날짜 지정 시 POST 요청으로 해당 주 데이터 가져오기
            if target_date:
                logger.info(f"지정 날짜 기준 SMP 데이터 조회: {target_date}")
                
                # 세션 생성
                session = requests.Session()
                
                # GET 요청으로 CSRF 토큰 가져오기
                logger.info("CSRF 토큰 획득을 위한 GET 요청")
                get_response = session.get(self.base_url, headers=self.headers, timeout=30)
                get_soup = BeautifulSoup(get_response.content, 'html.parser')
                
                # CSRF 토큰 찾기
                csrf_token = ''
                csrf_input = get_soup.find('input', {'name': '_csrf'})
                if csrf_input:
                    csrf_token = csrf_input.get('value', '')
                    logger.info("CSRF 토큰 획득 성공")
                
                # POST 데이터 구성
                post_data = {
                    'issue_date': target_date,
                    '_csrf': csrf_token
                }
                
                # POST 요청으로 날짜별 데이터 조회
                logger.info(f"POST 요청: {self.api_url}, 날짜: {target_date}")
                response = session.post(
                    self.api_url,
                    data=post_data,
                    headers=self.headers,
                    params={'mid': 'a10606080100', 'device': 'pc'},
                    timeout=30
                )
            else:
                # 최신 데이터 조회
                logger.info(f"최신 SMP 데이터 크롤링: {self.base_url}")
                response = requests.get(self.base_url, headers=self.headers, timeout=30)
            
            response.raise_for_status()
            logger.info(f"웹페이지 요청 성공 (상태코드: {response.status_code})")
            
            # HTML 파싱
            soup = BeautifulSoup(response.content, 'html.parser')
            logger.info("HTML 파싱 완료")
            
            # 테이블 찾기 (class가 conTable인 테이블)
            table = soup.find('table', {'class': 'conTable'})
            
            if not table:
                # class 없이 테이블 찾기
                table = soup.find('table')
                logger.warning("conTable 클래스를 찾지 못해 일반 테이블 검색")
            
            if not table:
                logger.error("테이블을 찾을 수 없습니다")
                return None
            
            # 테이블 데이터 추출
            df = pd.read_html(StringIO(str(table)))[0]
            logger.info(f"데이터 추출 성공 (shape: {df.shape})")
            logger.info(f"컬럼: {df.columns.tolist()}")
            
            return df
            
        except requests.RequestException as e:
            logger.error(f"웹 요청 중 오류 발생: {e}")
            return None
        except Exception as e:
            logger.error(f"데이터 크롤링 중 예상치 못한 오류 발생: {e}", exc_info=True)
            return None
    
    def format_smp_data(self, df: pd.DataFrame) -> str:
        """
        SMP 데이터를 텔레그램 메시지 형식으로 포맷팅
        
        Args:
            df: SMP 데이터프레임
            
        Returns:
            str: 포맷팅된 메시지
        """
        try:
            logger.info("데이터 포맷팅 시작")
            
            # 메시지 헤더
            today = datetime.now().strftime('%Y년 %m월 %d일')
            message = f"📊 <b>KPX 시간대별 SMP 데이터</b>\n"
            message += f"🗓 {today}\n"
            message += "=" * 50 + "\n\n"
            
            # 데이터가 비어있는지 확인
            if df is None or df.empty:
                logger.warning("데이터프레임이 비어있습니다")
                return message + "⚠️ 데이터를 가져올 수 없습니다."
            
            # 컬럼명 정리
            df_formatted = df.copy()
            
            # 최근 7일 데이터만 표시 (또는 사용 가능한 모든 데이터)
            logger.info(f"총 컬럼 수: {len(df_formatted.columns)}")
            
            # 요약 정보 먼저 표시
            message += "📈 <b>주간 요약</b>\n"
            
            # 최대, 최소, 평균값 추출 (마지막 3행에 있을 가능성)
            try:
                if '최대' in df_formatted.iloc[:, 0].values:
                    max_row = df_formatted[df_formatted.iloc[:, 0] == '최대']
                    min_row = df_formatted[df_formatted.iloc[:, 0] == '최소']
                    avg_row = df_formatted[df_formatted.iloc[:, 0] == '가중평균']
                    
                    message += "\n<b>최대값:</b>\n"
                    for col in df_formatted.columns[1:]:
                        if not max_row.empty and col in max_row.columns:
                            val = max_row[col].values[0]
                            message += f"  • {col}: {val} 원/kWh\n"
                    
                    message += "\n<b>최소값:</b>\n"
                    for col in df_formatted.columns[1:]:
                        if not min_row.empty and col in min_row.columns:
                            val = min_row[col].values[0]
                            message += f"  • {col}: {val} 원/kWh\n"
                    
                    message += "\n<b>가중평균:</b>\n"
                    for col in df_formatted.columns[1:]:
                        if not avg_row.empty and col in avg_row.columns:
                            val = avg_row[col].values[0]
                            message += f"  • {col}: {val} 원/kWh\n"
            except Exception as e:
                logger.warning(f"요약 정보 추출 중 오류: {e}")
            
            message += "\n" + "=" * 50 + "\n\n"
            
            # 시간대별 상세 데이터
            message += "⏰ <b>시간대별 상세 데이터</b>\n\n"
            
            # 시간대별 데이터만 추출 (1h~24h)
            hourly_data = df_formatted[df_formatted.iloc[:, 0].astype(str).str.contains('h$', regex=True, na=False)]
            
            if not hourly_data.empty:
                # 날짜 컬럼들
                date_columns = [col for col in hourly_data.columns[1:]]
                
                # 모든 날짜 데이터 표시 (일주일 전체)
                logger.info(f"일주일 전체 데이터 표시: {len(date_columns)}일")
                recent_dates = date_columns
                
                for date_col in recent_dates:
                    message += f"\n<b>📅 {date_col}</b>\n"
                    message += "-" * 30 + "\n"
                    
                    for idx, row in hourly_data.iterrows():
                        time_slot = row.iloc[0]
                        value = row[date_col]
                        
                        # 값에 따라 이모지 추가
                        if pd.notna(value):
                            try:
                                val_float = float(value)
                                if val_float > 120:
                                    emoji = "🔴"  # 높음
                                elif val_float > 90:
                                    emoji = "🟡"  # 중간
                                else:
                                    emoji = "🟢"  # 낮음
                                message += f"{emoji} {time_slot:>3}: {value:>7} 원/kWh\n"
                            except:
                                message += f"  {time_slot:>3}: {value:>7} 원/kWh\n"
            else:
                logger.warning("시간대별 데이터를 찾을 수 없습니다")
                message += "⚠️ 시간대별 데이터를 찾을 수 없습니다.\n"
            
            message += "\n" + "=" * 50 + "\n"
            message += "📌 데이터 출처: KPX 한국전력거래소\n"
            message += f"🕐 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            logger.info(f"메시지 포맷팅 완료 (길이: {len(message)} 자)")
            
            return message
            
        except Exception as e:
            logger.error(f"데이터 포맷팅 중 오류 발생: {e}")
            return f"❌ 데이터 포맷팅 중 오류가 발생했습니다: {str(e)}"


class TelegramBot:
    """텔레그램 봇 클래스"""
    
    def __init__(self, token: str, chat_id: str):
        """
        초기화 메서드
        
        Args:
            token: 텔레그램 봇 토큰
            chat_id: 메시지를 받을 채팅방 ID
        """
        self.token = token
        self.chat_id = chat_id
        self.bot = Bot(token=token)
        logger.info(f"TelegramBot 초기화 완료 (Chat ID: {chat_id})")
    
    async def send_message(self, message: str):
        """
        텔레그램으로 메시지 전송
        
        Args:
            message: 전송할 메시지
        """
        try:
            logger.info("텔레그램 메시지 전송 시작")
            logger.debug(f"메시지 내용 (길이: {len(message)})")
            
            # 메시지가 너무 길면 여러 개로 분할 (텔레그램 메시지 길이 제한: 4096자)
            max_length = 4000
            
            if len(message) > max_length:
                logger.warning(f"메시지가 너무 깁니다 ({len(message)}자). 분할 전송합니다.")
                
                # 메시지를 줄 단위로 분할
                lines = message.split('\n')
                current_message = ""
                part_number = 1
                
                for line in lines:
                    if len(current_message) + len(line) + 1 > max_length:
                        # 현재 메시지 전송
                        await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=f"[Part {part_number}]\n{current_message}",
                            parse_mode='HTML'
                        )
                        logger.info(f"Part {part_number} 전송 완료")
                        current_message = line + '\n'
                        part_number += 1
                        await asyncio.sleep(1)  # API 제한 방지
                    else:
                        current_message += line + '\n'
                
                # 마지막 메시지 전송
                if current_message:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=f"[Part {part_number}]\n{current_message}",
                        parse_mode='HTML'
                    )
                    logger.info(f"Part {part_number} 전송 완료")
            else:
                # 일반 전송
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info("메시지 전송 성공")
            
        except TelegramError as e:
            logger.error(f"텔레그램 전송 중 오류 발생: {e}")
            raise
        except Exception as e:
            logger.error(f"예상치 못한 오류 발생: {e}")
            raise


class SMPBot:
    """SMP 데이터를 크롤링하고 텔레그램으로 전송하는 메인 봇 클래스"""
    
    def __init__(self, telegram_token: str, chat_id: str):
        """
        초기화 메서드
        
        Args:
            telegram_token: 텔레그램 봇 토큰
            chat_id: 메시지를 받을 채팅방 ID
        """
        self.crawler = SMPCrawler()
        self.telegram_bot = TelegramBot(telegram_token, chat_id)
        logger.info("SMPBot 초기화 완료")
    
    async def send_smp_report(self):
        """
        SMP 리포트 생성 및 전송
        매주 월요일에 실행 시: 지난주 월~일 7일치 데이터 전송
        """
        try:
            logger.info("=" * 70)
            logger.info("SMP 리포트 생성 및 전송 시작")
            logger.info("=" * 70)
            
            # 지난주 일요일 날짜 계산 (월요일 기준)
            today = datetime.now()
            # 오늘이 월요일이면 어제(일요일)이 지난주 마지막 날
            if today.weekday() == 0:  # 월요일
                last_sunday = today - timedelta(days=1)
                target_date = last_sunday.strftime('%Y-%m-%d')
                logger.info(f"📅 월요일 스케줄 실행 - 지난주 일요일: {target_date}")
                logger.info(f"📊 조회 기간: 지난주 월요일~일요일 (7일)")
            else:
                # 월요일이 아니면 최신 데이터
                target_date = None
                logger.info("월요일이 아님 - 최신 데이터 조회")
            
            # 1. 데이터 크롤링
            logger.info("Step 1: 데이터 크롤링")
            df = self.crawler.fetch_smp_data(target_date)
            
            if df is None:
                error_msg = "❌ SMP 데이터를 가져오는데 실패했습니다."
                logger.error(error_msg)
                await self.telegram_bot.send_message(error_msg)
                return
            
            # 2. 데이터 포맷팅
            logger.info("Step 2: 데이터 포맷팅")
            
            # 메시지 헤더 추가 (지난주 정보)
            if target_date:
                last_monday = datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=6)
                week_info = f"📅 <b>지난주 주간 리포트</b>\n"
                week_info += f"기간: {last_monday.strftime('%Y.%m.%d')} (월) ~ {target_date[:4]}.{target_date[5:7]}.{target_date[8:10]} (일)\n"
                week_info += "=" * 50 + "\n\n"
            else:
                week_info = ""
            
            message = week_info + self.crawler.format_smp_data(df)
            
            # 3. 텔레그램 전송
            logger.info("Step 3: 텔레그램 전송")
            await self.telegram_bot.send_message(message)
            
            logger.info("=" * 70)
            logger.info("SMP 리포트 전송 완료!")
            logger.info("=" * 70)
            
        except Exception as e:
            error_msg = f"❌ SMP 리포트 생성 중 오류 발생: {str(e)}"
            logger.error(error_msg, exc_info=True)
            try:
                await self.telegram_bot.send_message(error_msg)
            except:
                logger.error("오류 메시지 전송도 실패했습니다")
    
    def run_scheduled_task(self):
        """스케줄러에서 호출할 동기 메서드"""
        logger.info("스케줄된 작업 실행")
        asyncio.run(self.send_smp_report())


def job_wrapper(bot: SMPBot):
    """스케줄러를 위한 래퍼 함수"""
    logger.info("스케줄된 작업이 트리거되었습니다")
    bot.run_scheduled_task()


# Flask 헬스체크 엔드포인트
@app.route('/')
def home():
    """메인 헬스체크 엔드포인트"""
    logger.info("헬스체크 요청 수신")
    return jsonify({
        'status': 'OK',
        'message': 'SMP 텔레그램 봇이 정상 작동 중입니다.',
        'timestamp': datetime.now().isoformat(),
        'timezone': 'Asia/Seoul',
        'schedule': '매주 월요일 오전 9시',
        'next_run': '월요일 09:00 (KST)'
    })


@app.route('/health')
def health():
    """간단한 헬스체크 엔드포인트"""
    logger.info("간단한 헬스체크 요청 수신")
    return 'OK', 200


def run_flask_app():
    """Flask 앱을 별도 스레드에서 실행"""
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Flask 서버 시작 - 포트: {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def run_scheduler(bot: SMPBot):
    """스케줄러를 실행하는 함수"""
    logger.info("스케줄러 시작")
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 체크


def main():
    """메인 함수"""
    logger.info("=" * 70)
    logger.info("SMP 텔레그램 봇 프로그램 시작")
    logger.info("=" * 70)
    
    # 환경변수 또는 설정에서 토큰과 채팅 ID 가져오기
    # 보안을 위해 환경변수 사용을 권장합니다
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID_HERE')
    
    # 설정 검증
    if TELEGRAM_TOKEN == 'YOUR_BOT_TOKEN_HERE' or CHAT_ID == 'YOUR_CHAT_ID_HERE':
        logger.error("환경변수를 설정해주세요!")
        logger.error("TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요")
        print("\n" + "="*70)
        print("⚠️  설정 필요!")
        print("="*70)
        print("\n1. .env 파일을 생성하거나")
        print("2. 환경변수를 설정해주세요:")
        print("\n   TELEGRAM_BOT_TOKEN=your_bot_token")
        print("   TELEGRAM_CHAT_ID=your_chat_id")
        print("\n또는 코드에서 직접 설정할 수 있습니다 (보안상 권장하지 않음)")
        print("="*70 + "\n")
        return
    
    # 봇 초기화
    logger.info("SMPBot 초기화 중...")
    bot = SMPBot(TELEGRAM_TOKEN, CHAT_ID)
    logger.info("SMPBot 초기화 완료")
    
    # 즉시 한 번 실행 (테스트용)
    logger.info("=" * 70)
    logger.info("첫 실행을 시작합니다 (테스트)")
    logger.info("=" * 70)
    asyncio.run(bot.send_smp_report())
    logger.info("첫 실행 완료")
    
    # 스케줄 설정: 매주 월요일 오전 9시
    schedule.every().monday.at("09:00").do(job_wrapper, bot=bot)
    logger.info("스케줄 설정 완료: 매주 월요일 오전 9시")
    
    # 매시간마다 서버 활성 상태 체크 (Render 슬립 방지)
    def keep_alive():
        """서버 활성 상태 유지"""
        logger.info("🔄 서버 활성 상태 확인")
    
    schedule.every().hour.do(keep_alive)
    logger.info("서버 활성 상태 체크 스케줄 설정 완료: 매시간")
    
    # 추가 스케줄 (선택사항 - 필요시 주석 해제)
    # schedule.every().day.at("09:00").do(job_wrapper, bot=bot)  # 매일 9시
    
    print("\n" + "="*70)
    print("✅ SMP 텔레그램 봇이 시작되었습니다!")
    print("="*70)
    print(f"📅 스케줄: 매주 월요일 오전 9시")
    print(f"📱 Chat ID: {CHAT_ID}")
    print(f"🌐 Flask 서버: 포트 {os.getenv('PORT', 10000)}")
    print(f"🔄 봇이 백그라운드에서 실행 중입니다...")
    print(f"⏸️  종료하려면 Ctrl+C를 누르세요")
    print("="*70 + "\n")
    
    # Flask 서버를 별도 스레드에서 시작
    logger.info("Flask 서버 스레드 시작")
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    logger.info("Flask 서버 스레드 시작 완료")
    
    # 스케줄러 실행 (메인 스레드)
    logger.info("스케줄러 시작 - 메인 스레드에서 실행")
    try:
        run_scheduler(bot)
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 종료되었습니다")
        print("\n프로그램을 종료합니다...")


if __name__ == "__main__":
    main()

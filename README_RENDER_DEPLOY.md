# SMP 텔레그램 봇 - Render.com 배포 가이드

## 📌 개요

이 가이드는 SMP 텔레그램 봇을 Render.com 클라우드 서비스에 배포하여 **24시간 자동으로 실행**되도록 하는 방법을 설명합니다.

Render.com에 배포하면:
- ✅ **커서(Cursor)를 끄거나 컴퓨터를 꺼도** 봇이 계속 작동합니다
- ✅ **매주 월요일 오전 9시**에 자동으로 SMP 리포트를 전송합니다
- ✅ **무료 플랜**으로 시작할 수 있습니다 (월 750시간 무료)

---

## 🚀 배포 준비

### 1. 필요한 것들

1. **Render.com 계정**
   - [Render.com](https://render.com) 가입 (무료)
   - GitHub 계정 연동 권장

2. **환경 변수**
   - `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
   - `TELEGRAM_CHAT_ID`: 텔레그램 채팅방 ID

3. **GitHub 저장소** (선택사항 - 권장)
   - 코드를 GitHub에 푸시하면 자동 배포가 가능합니다

---

## 📝 배포 단계별 가이드

### 단계 1: GitHub 저장소 준비 (권장)

#### 1-1. 새 GitHub 저장소 생성
- [GitHub](https://github.com)에서 새 저장소 생성
- 저장소 이름: `smp-telegram-bot` (원하는 이름)
- Public 또는 Private 선택

#### 1-2. 코드 푸시
```bash
# Git 초기화 (아직 안했다면)
cd SMP
git init

# 저장소 연결
git remote add origin https://github.com/YOUR_USERNAME/smp-telegram-bot.git

# 코드 추가 및 커밋
git add .
git commit -m "SMP 텔레그램 봇 초기 커밋"

# 푸시
git branch -M main
git push -u origin main
```

---

### 단계 2: Render.com에서 Web Service 생성

#### 2-1. Render.com 로그인
- [Render.com](https://render.com) 로그인
- Dashboard로 이동

#### 2-2. 새 Web Service 생성
1. **"New +" 버튼** 클릭
2. **"Web Service"** 선택
3. GitHub 저장소 연결 또는 Public Git Repository URL 입력

#### 2-3. 서비스 설정
다음과 같이 설정하세요:

| 항목 | 값 |
|------|-----|
| **Name** | `smp-telegram-bot` (원하는 이름) |
| **Region** | `Singapore` (한국과 가장 가까움) |
| **Branch** | `main` |
| **Root Directory** | `SMP` (또는 비워두기) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python smp_information.py` |
| **Instance Type** | `Free` |

---

### 단계 3: 환경 변수 설정

#### 3-1. Environment Variables 추가
Render 서비스 설정 페이지에서:

1. **"Environment"** 탭 클릭
2. **"Add Environment Variable"** 클릭
3. 다음 환경 변수들을 추가:

```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
PORT=10000
```

⚠️ **중요**: 
- `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`는 실제 값으로 변경하세요
- `PORT`는 10000으로 설정하세요 (Render 기본 포트)

#### 3-2. 텔레그램 봇 토큰 발급 방법
1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령어 입력
3. 봇 이름과 사용자명 설정
4. 발급된 토큰을 복사하여 `TELEGRAM_BOT_TOKEN`에 입력

#### 3-3. 텔레그램 Chat ID 확인 방법
1. 봇과 대화 시작 (한 번 메시지 보내기)
2. 브라우저에서 다음 URL 접속:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
3. `"chat":{"id":123456789}` 형식으로 나오는 숫자가 Chat ID
4. 복사하여 `TELEGRAM_CHAT_ID`에 입력

---

### 단계 4: 배포 및 확인

#### 4-1. 배포 시작
- **"Create Web Service"** 버튼 클릭
- Render가 자동으로 빌드 및 배포를 시작합니다
- 로그를 확인하며 배포 진행 상황을 모니터링하세요

#### 4-2. 배포 완료 확인
배포가 완료되면:
1. **"Logs"** 탭에서 다음과 같은 메시지 확인:
   ```
   ✅ SMP 텔레그램 봇이 시작되었습니다!
   📅 스케줄: 매주 월요일 오전 9시
   🌐 Flask 서버: 포트 10000
   ```

2. **웹 브라우저**에서 서비스 URL 접속:
   ```
   https://your-service-name.onrender.com/
   ```
   
   다음과 같은 JSON 응답이 나오면 성공:
   ```json
   {
     "status": "OK",
     "message": "SMP 텔레그램 봇이 정상 작동 중입니다.",
     "timestamp": "2025-10-01T12:00:00",
     "timezone": "Asia/Seoul",
     "schedule": "매주 월요일 오전 9시"
   }
   ```

3. **텔레그램**에서 첫 실행 메시지 확인
   - 배포 직후 테스트 메시지가 전송됩니다

---

## 🔧 추가 설정 (선택사항)

### Health Check 설정 (무료 플랜 슬립 방지)

Render 무료 플랜은 15분 동안 요청이 없으면 슬립 모드로 들어갑니다.
이를 방지하기 위해 외부 모니터링 서비스를 사용하세요:

#### 방법 1: UptimeRobot (권장)
1. [UptimeRobot](https://uptimerobot.com) 무료 가입
2. **"Add New Monitor"** 클릭
3. 다음과 같이 설정:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: SMP Telegram Bot
   - **URL**: `https://your-service-name.onrender.com/health`
   - **Monitoring Interval**: 5 minutes (무료 플랜)
4. **"Create Monitor"** 클릭

#### 방법 2: GitHub Actions (완전 무료)
GitHub Actions를 사용하여 5분마다 핑을 보낼 수 있습니다.
(설정 방법은 별도 문서 참조)

---

## 📊 모니터링 및 로그

### 로그 확인
- Render Dashboard → 서비스 선택 → **"Logs"** 탭
- 실시간으로 봇의 동작 상황을 확인할 수 있습니다

### 주요 로그 메시지
```
✅ 정상 작동
🔄 서버 활성 상태 확인 (매시간)
📅 스케줄된 작업 트리거 (매주 월요일 9시)
📊 SMP 리포트 생성 및 전송
```

### 오류 발생 시
1. **Logs 탭**에서 오류 메시지 확인
2. **Environment 탭**에서 환경 변수 재확인
3. 필요시 **"Manual Deploy"** 버튼으로 재배포

---

## 🔄 업데이트 및 재배포

### 코드 수정 후 재배포
```bash
# 코드 수정 후
git add .
git commit -m "수정 내용"
git push origin main
```

Render가 자동으로 새 코드를 감지하고 재배포합니다!

### 수동 재배포
- Render Dashboard → 서비스 선택 → **"Manual Deploy"** → **"Deploy latest commit"**

---

## 💰 비용

### 무료 플랜
- ✅ **월 750시간** 무료 (31일 기준으로 충분)
- ✅ SSL 인증서 자동 제공
- ✅ 자동 배포
- ⚠️ 15분 동안 요청이 없으면 슬립 모드 (Health Check로 방지 가능)

### 유료 플랜 ($7/월)
- ✅ 슬립 모드 없음
- ✅ 더 빠른 성능
- ✅ 더 많은 리소스

대부분의 경우 **무료 플랜으로 충분**합니다!

---

## ❓ 문제 해결 (Troubleshooting)

### 1. 배포가 실패하는 경우
- **Build Logs** 확인
- `requirements.txt` 파일이 올바른지 확인
- Python 버전 호환성 확인

### 2. 봇이 메시지를 보내지 않는 경우
- 환경 변수 (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) 재확인
- 텔레그램 봇과 대화를 시작했는지 확인
- Logs에서 오류 메시지 확인

### 3. 서버가 슬립 모드로 들어가는 경우
- UptimeRobot 또는 GitHub Actions로 Health Check 설정
- 매시간 서버 활성 상태 체크가 동작하는지 확인

### 4. 스케줄이 작동하지 않는 경우
- 시간대(Timezone) 확인
- Logs에서 스케줄 설정 메시지 확인
- 환경 변수 `TZ=Asia/Seoul` 추가 (선택사항)

---

## 📚 참고 자료

- [Render.com 공식 문서](https://render.com/docs)
- [Python Telegram Bot 문서](https://python-telegram-bot.readthedocs.io/)
- [Schedule 라이브러리 문서](https://schedule.readthedocs.io/)

---

## ✅ 체크리스트

배포 전 확인사항:

- [ ] Render.com 계정 생성 완료
- [ ] GitHub 저장소 생성 및 코드 푸시 완료
- [ ] 텔레그램 봇 토큰 발급 완료
- [ ] 텔레그램 Chat ID 확인 완료
- [ ] Render에서 Web Service 생성 완료
- [ ] 환경 변수 설정 완료
- [ ] 배포 성공 및 로그 확인 완료
- [ ] 웹 브라우저에서 Health Check 응답 확인 완료
- [ ] 텔레그램에서 첫 메시지 수신 확인 완료
- [ ] (선택) UptimeRobot Health Check 설정 완료

---

## 🎉 완료!

이제 SMP 텔레그램 봇이 클라우드에서 24시간 자동으로 실행됩니다!

- 매주 **월요일 오전 9시**에 자동으로 지난주 SMP 데이터를 전송합니다
- 컴퓨터를 끄거나 Cursor를 종료해도 계속 작동합니다
- 언제든지 로그를 확인하여 상태를 모니터링할 수 있습니다

궁금한 점이 있으시면 Render.com 문서를 참고하거나 이슈를 등록해주세요!



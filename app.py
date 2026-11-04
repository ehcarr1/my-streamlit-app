
import hashlib  # 업로드한 회의록이 변경되었는지 확인
import html  # 사용자 입력을 웹 화면에 안전하게 표시
import os  # 환경변수에 저장된 인증정보 읽기
import re  # 답변의 첫 줄에서 표시용 문장 추출
import smtplib  # Gmail SMTP 연결
from email.message import EmailMessage  # 한글 이메일 작성

import streamlit as st  # 웹앱 화면 구성
from openai import OpenAI  # OpenAI API 호출


# 1. 페이지 및 스타일 -----------------------------------------------------------
st.set_page_config(page_title="Thumbs Up | 음성 AI 비서", page_icon="👍", layout="wide", initial_sidebar_state="collapsed")  # 기본 화면 설정

st.markdown("""
<style>
:root { color-scheme: light; }
.stApp { background: radial-gradient(ellipse at 36% 12%, #f7f6ff 0%, #fff 42%, #fff 100%); color:#1c2034; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display:none !important; }
.block-container { max-width: 1450px; padding-top:1.7rem; padding-bottom:3rem; }
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label { color:#34374f; }
.hero { text-align:center; padding: 1.4rem 0 1.1rem; }
.hero h1 { font-size:2.65rem; font-weight:800; letter-spacing:-.04em; margin:0; color:#22243a; }
.hero h1 span { color:#8464f0; }
.hero p { color:#77758a; font-size:1rem; margin-top:.55rem; }
.question-card { max-width:1040px; margin-left:auto; margin-right:auto; background:#fff; border:1px solid #eceaf8; border-radius:22px; padding:1.5rem 2rem; text-align:center; box-shadow:0 12px 32px #4440a70c; margin:.65rem 0 1.1rem; }
.question-card .small { color:#8b7bb9; font-size:.82rem; margin-bottom:.8rem; }
.question-card .big { font-size:1.35rem; font-weight:750; color:#28253b; line-height:1.65; white-space:pre-wrap; }
.voice-center { text-align:center; margin:.25rem 0 .55rem; }
.voice-center .mic { display:inline-flex; align-items:center; justify-content:center; width:100px; height:100px; border-radius:50%; font-size:3.2rem; color:#8b63f2; background:#fff; box-shadow:0 0 0 10px #eeebff70, 0 0 40px #ba9ffa88; }
.wave { height:15px; max-width:750px; margin:-53px auto 57px; border-radius:100%; background:linear-gradient(90deg,transparent 0%,#b4c8ff 19%,#c2a2fa 42%,#f1b0e0 63%,#e9b8f0 77%,transparent 100%); opacity:.55; filter:blur(5px); }
.preview { max-width:1050px; margin-left:auto; margin-right:auto; background:#fff; border:1px solid #e8e5f6; border-radius:17px; padding:16px 21px; margin:1rem 0 .7rem; font-size:1.04rem; font-weight:650; color:#28243d; box-shadow:0 5px 16px #6663a70c; }
.section-hint { color:#858198; font-size:.9rem; text-align:center; }
.panel-heading { font-weight:800; font-size:1.25rem; margin-bottom:1.1rem; }
.panel-caption { font-size:.88rem; font-weight:700; color:#4c4868; margin:.65rem 0; }
.risk-note { color:#737187; font-size:.86rem; margin-bottom:.5rem; }
.risk-box { padding:1rem; border:1px solid #e5e1f4; border-radius:18px; background:#fcfbff; margin-top:.5rem; }
div[data-testid="stAudioInput"] { padding: .4rem 1rem; border-radius:15px; background:#faf9ff; border:1px solid #eeebf7; }
div[data-testid="stButton"] button[kind="primary"] { background:#7858e6; border-color:#7858e6; border-radius:13px; }
@media (max-width:800px) { .hero h1{font-size:1.9rem;} .question-card .big{font-size:1.04rem;} .block-container{padding-top:.7rem;} }
</style>
""", unsafe_allow_html=True)  # 기본 흰색·연보라색 화면 디자인 적용


# 2. 비밀정보와 기본 상태 ------------------------------------------------------
def get_secret(name):  # 환경변수 또는 Streamlit Secrets에서 인증정보 읽기
    if os.getenv(name):  # 코랩에서 환경변수를 전달했다면
        return os.getenv(name)  # 환경변수 사용
    try:  # 배포한 Streamlit 앱이라면
        return st.secrets.get(name, "")  # Secrets에서 읽기
    except Exception:  # 설정 파일이 아직 없어도 화면은 보여주기
        return ""  # 인증정보 없음


api_key = get_secret("OPENAI_API_KEY")  # OpenAI API 키 확인
client = OpenAI(api_key=api_key) if api_key else None  # API 키가 있을 때만 클라이언트 생성

initial_state = {  # 앱 화면과 대화에 필요한 상태 초기값
    "panel_open": True,  # 오른쪽 설정 패널은 처음에 열린 상태
    "use_meeting": True,  # 회의록 분석 기능 활성화
    "enable_risk": True,  # 업무 리스크 점검 기능 활성화
    "enable_email": False,  # 이메일 발송 영역은 처음에 감춤
    "use_tts": True,  # 음성으로 답변 듣기 활성화
    "voice": "nova",  # 기본 TTS 목소리
    "keep_history": True,  # 같은 세션에서 대화 문맥 유지
    "turns": [],  # 질문과 답변 기록
    "last_question": "",  # 최근 사용자 질문
    "last_answer": "",  # 최근 GPT 답변
    "last_audio": None,  # 최근 TTS 음성 바이트
    "risk_result": "",  # 업무 리스크 분석 결과
    "document_hash": "",  # 현재 업로드된 문서 식별자
    "recorder_count": 0,  # 녹음 완료 후 새 녹음기를 표시하기 위한 번호
    "mail_body": "",  # 이메일 전송 본문
}  # 기본 상태 정의 완료
for name, value in initial_state.items():  # 각 상태를 확인해
    if name not in st.session_state:  # 처음 실행할 때만
        st.session_state[name] = value  # 초기값 저장


def to_text(upload):  # 업로드 파일을 한국어 문자열로 변환
    if upload is None:  # 파일이 없다면
        return ""  # 빈 문자열 반환
    contents = upload.getvalue()  # 파일 내용 읽기
    if len(contents) > 1_000_000:  # 1MB 이상은 비용·처리 부담을 피하기 위해 제한
        st.warning("회의록은 1MB 이하 TXT 파일을 사용해 주세요.")  # 용량 안내
        return ""  # 처리하지 않음
    for enc in ("utf-8-sig", "cp949"):  # UTF-8과 한국어 Windows 인코딩 순서로 시도
        try:  # 지정한 인코딩으로 변환
            return contents.decode(enc)  # 변환에 성공한 문자열 반환
        except UnicodeDecodeError:  # 다른 인코딩이라면
            continue  # 다음 형식 시도
    st.error("회의록을 읽지 못했습니다. UTF-8 TXT 파일을 사용해 주세요.")  # 읽기 오류 안내
    return ""  # 처리하지 않음


def ask_gpt(question, meeting_text):  # 기존 미션 3의 GPT 호출을 웹앱용으로 재사용
    instruction = "당신은 음성 AI 개인비서 Thumbs Up입니다. 간결하고 정확한 한국어 존댓말로 답변하세요. 회의록에 없는 사실은 만들어내지 마세요."  # AI 역할
    if meeting_text and st.session_state.use_meeting:  # 회의록이 있고 분석 기능이 켜졌다면
        instruction += "\n[참고 회의록]\n" + meeting_text  # 회의록을 GPT에 함께 전달
    history = st.session_state.turns[-8:] if st.session_state.keep_history else []  # 최근 대화만 참고
    messages = [{"role": "system", "content": instruction}] + history + [{"role": "user", "content": question}]  # API 입력 구성
    result = client.responses.create(model="gpt-4o-mini", input=messages)  # GPT에 질문하고 응답 생성
    return result.output_text  # 답변 글자만 반환


def analyze_risks(meeting_text):  # 기존 미션 3의 프롬프트를 확장한 업무 리스크 분석
    instruction = "당신은 회의록의 업무 수행상 불확실성을 점검하는 비서입니다. 근거 없는 리스크를 만들지 마세요."  # 분석 역할
    prompt = f"""아래 회의록에서 업무 수행에 필요한 정보의 누락이나 모호함을 점검하세요.
검사 기준: (1) 담당자 미정 (2) 기한 누락·모호 (3) 완료 기준·업무 범위 불명확.
각 항목은 '확인이 필요한 사항 / 회의록의 근거 / 확인할 질문' 순서로 3줄 이내로 작성하세요.
문제가 없으면 '추가 확인이 필요한 사항을 찾지 못했습니다'라고 적으세요.
회의록에서 확인되는 내용과 추정은 구분하고, 임의의 인물·날짜를 만들지 마세요.
[회의록]\n{meeting_text}"""  # 업무 리스크 점검 요청
    result = client.responses.create(model="gpt-4o-mini", input=[{"role": "system", "content": instruction}, {"role": "user", "content": prompt}])  # GPT에 점검 요청
    return result.output_text  # 분석 결과 반환


def send_gmail(receiver, subject, body):  # 미션 1에서 배운 SMTP 이메일 발송 기능
    sender = get_secret("GMAIL_ADDRESS")  # 발신자 주소 읽기
    password = get_secret("GMAIL_APP_PASSWORD")  # Gmail 앱 비밀번호 읽기
    if not sender or not password:  # 인증정보가 없다면
        raise ValueError("GMAIL_ADDRESS 및 GMAIL_APP_PASSWORD 설정이 필요합니다.")  # 오류 안내
    message = EmailMessage()  # 이메일 객체 생성
    message["From"] = sender  # 발신자 지정
    message["To"] = receiver  # 수신자 지정
    message["Subject"] = subject  # 제목 지정
    message.set_content(body)  # 본문 지정
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:  # Gmail 보안 연결
        smtp.login(sender, password)  # Gmail 인증
        smtp.send_message(message)  # 실제 이메일 발송


def save_setting(name):  # 오른쪽 패널을 닫아도 선택한 설정을 기억하기 위한 콜백
    st.session_state[name] = st.session_state[f"_widget_{name}"]  # 위젯 값을 별도 영구 세션 값에 복사


def preference_toggle(label, name):  # 설정 패널을 다시 열 때도 이전 선택을 복구하는 토글
    widget_name = f"_widget_{name}"  # 화면 위젯 전용 임시 키
    if widget_name not in st.session_state:  # 패널을 다시 열어 위젯이 새로 생겼다면
        st.session_state[widget_name] = st.session_state[name]  # 저장해 둔 선택값을 복구
    st.toggle(label, key=widget_name, on_change=save_setting, args=(name,))  # 토글 조작 시 설정값 저장


# 3. 맨 위의 제목과 오른쪽 패널 열기·닫기 버튼 -------------------------------
left_header, right_header = st.columns([7, 1.6], vertical_alignment="center")  # 제목과 설정 버튼 정렬
with left_header:  # 화면 왼쪽 제목 부분
    st.caption("👍 THUMBS UP  ·  Voice AI Assistant")  # 브랜드 표시
with right_header:  # 화면 오른쪽 버튼 부분
    btn_label = "✕ 설정 닫기" if st.session_state.panel_open else "⚙ 설정 열기"  # 현재 상태에 따른 버튼 이름
    if st.button(btn_label, use_container_width=True, key="panel_switch"):  # 설정 버튼을 눌렀다면
        st.session_state.panel_open = not st.session_state.panel_open  # 설정 패널 상태 반전
        st.rerun()  # 새 레이아웃 표시

if st.session_state.panel_open:  # 설정 창이 열려 있다면
    main_column, setting_column = st.columns([3.5, 1.3], gap="large")  # 가운데와 오른쪽으로 분할
else:  # 설정 창이 닫혀 있다면
    main_column = st.container()  # 중앙 영역이 전체 폭을 사용
    setting_column = None  # 오른쪽 설정 패널을 아예 그리지 않음


# 4. 오른쪽 설정 패널 --------------------------------------------------------
if setting_column is not None:  # 설정 패널이 열린 경우에만
    with setting_column:  # 오른쪽 열에 표시
        with st.container(border=True):  # 설정 카드
            st.markdown("### ⚙️ 설정 및 도구")  # 패널 제목
            st.markdown("**사용 기능 선택**")  # 설정 묶음 제목
            preference_toggle("회의록 분석 (요약·업무 정리)", "use_meeting")  # 회의록 기능 켜기/끄기
            preference_toggle("업무 리스크 점검", "enable_risk")  # 리스크 분석 기능 켜기/끄기
            preference_toggle("이메일 작성 및 발송", "enable_email")  # 이메일 작성 영역 켜기/끄기
            st.divider()  # 그룹 구분선
            st.markdown("**답변 방식**")  # 출력 설정 제목
            preference_toggle("음성 + 텍스트", "use_tts")  # 음성 출력 켜기/끄기
            if "_widget_voice" not in st.session_state:  # 패널 재개방 시 목소리 선택 복구
                st.session_state["_widget_voice"] = st.session_state.voice  # 선택된 음성 종류 기억
            st.selectbox("TTS 목소리", ["nova", "alloy", "shimmer"], key="_widget_voice", on_change=save_setting, args=("voice",), disabled=not st.session_state.use_tts)  # TTS 목소리 선택
            st.divider()  # 그룹 구분선
            st.markdown("**기타 설정**")  # 추가 설정 제목
            preference_toggle("대화 문맥 유지", "keep_history")  # GPT에 이전 대화 포함 여부
            if st.button("새 대화 시작", use_container_width=True):  # 대화 기록 초기화 요청
                st.session_state.turns = []  # 질문·답변 기록 지우기
                st.session_state.last_question = ""  # 최근 질문 지우기
                st.session_state.last_answer = ""  # 최근 답변 지우기
                st.session_state.last_audio = None  # 최근 음성 지우기
                st.session_state.risk_result = ""  # 분석 결과 지우기
                st.session_state.recorder_count += 1  # 녹음 입력 초기화
                st.rerun()  # 초기 화면 다시 표시
            st.caption("설정은 현재 브라우저 세션에서 유지됩니다.")  # 저장 범위 설명


# 5. 메인 음성 대화 화면 ------------------------------------------------------
with main_column:  # 중앙 영역에 콘텐츠 표시
    st.markdown('<div class="hero"><h1>👍 <span>Thumbs Up</span></h1><p>말로 요청하면, 필요한 일을 정리하고 도와드리는 음성 AI 비서</p></div>', unsafe_allow_html=True)  # 브랜드와 설명

    meeting_file = st.file_uploader("📄 회의록 업로드 (TXT, 선택 사항)", type=["txt"], key="meeting_file")  # 회의록 업로드
    meeting_text = to_text(meeting_file) if meeting_file is not None else ""  # 회의록을 문자열로 변환
    document_hash = hashlib.sha256(meeting_text.encode("utf-8")).hexdigest() if meeting_text else ""  # 문서 내용 해시 계산
    if document_hash != st.session_state.document_hash:  # 업로드된 문서가 바뀌었다면
        st.session_state.document_hash = document_hash  # 새 문서 해시 저장
        st.session_state.risk_result = ""  # 이전 문서 분석 결과 지우기
        st.session_state.turns = []  # 다른 문서의 대화가 섞이지 않게 기록 초기화

    question_text = st.session_state.last_question if st.session_state.last_question else "마이크를 누르고 질문해 주세요"  # 화면에 표시할 사용자 질문
    st.markdown(f'<div class="question-card"><div class="small">🎤 내 말 · 음성 인식 결과</div><div class="big">{html.escape(question_text)}</div></div>', unsafe_allow_html=True)  # 음성 인식 텍스트 표시

    st.markdown('<div class="voice-center"><div class="mic">🎙</div></div><div class="wave"></div>', unsafe_allow_html=True)  # 음성 중심 디자인 장식
    st.markdown('<p class="section-hint">아래 녹음 버튼으로 말을 녹음한 후, 질문 보내기를 누르세요.</p>', unsafe_allow_html=True)  # 사용 방법 안내
    audio_value = st.audio_input("음성 질문 녹음", key=f"mic_input_{st.session_state.recorder_count}")  # 마이크 녹음받기
    send_audio = st.button("🎙️ 녹음한 질문 보내기", use_container_width=True, type="primary", disabled=audio_value is None)  # 녹음 제출 버튼
    typed_question = st.chat_input("또는 글자로 질문하기")  # 마이크 없이 글로 질문하기

    pending_question = None  # 이번 실행에서 GPT로 보낼 질문
    if send_audio and audio_value is not None:  # 녹음 제출을 눌렀다면
        if client is None:  # API 키가 없다면
            st.error("OPENAI_API_KEY 설정이 필요합니다.")  # 인증정보 안내
        else:  # API 사용 가능
            try:  # 음성 인식 시도
                with st.spinner("말씀하신 내용을 인식하고 있습니다..."):  # 작업 진행 안내
                    transcript = client.audio.transcriptions.create(model="whisper-1", file=("question.wav", audio_value.getvalue(), "audio/wav"))  # Whisper STT 호출
                    pending_question = transcript.text.strip()  # 인식된 텍스트 추출
            except Exception as error:  # API 오류가 발생하면
                st.error(f"음성 인식 중 오류: {error}")  # 오류 표시
    elif typed_question:  # 사용자가 글자로 질문했다면
        pending_question = typed_question.strip()  # 글로 입력한 질문 사용

    if pending_question:  # 실제 질문을 받았다면
        if client is None:  # 인증정보가 없다면
            st.error("OPENAI_API_KEY 설정이 필요합니다.")  # 인증 안내
        else:  # API 사용 가능
            try:  # 답변 생성과 음성 변환
                with st.spinner("Thumbs Up이 답변을 준비하고 있습니다..."):  # API 호출 진행 안내
                    answer = ask_gpt(pending_question, meeting_text)  # GPT 답변 생성
                    speech_bytes = None  # 음성 출력 초기값
                    if st.session_state.use_tts and answer:  # 음성 답변이 활성화되어 있다면
                        try:  # TTS 변환 시도
                            speech = client.audio.speech.create(model="gpt-4o-mini-tts", voice=st.session_state.voice, input=answer[:3500])  # GPT 답변을 음성으로 변환
                            speech_bytes = speech.content  # mp3 바이트 저장
                        except Exception as error:  # TTS만 실패했을 때
                            st.warning(f"텍스트 답변은 준비됐지만 음성 생성에 실패했습니다: {error}")  # 텍스트 답변 보존
                    st.session_state.last_question = pending_question  # 최근 질문 저장
                    st.session_state.last_answer = answer  # 최근 답변 저장
                    st.session_state.last_audio = speech_bytes  # 생성된 음성 저장
                    st.session_state.turns.extend([{"role": "user", "content": pending_question}, {"role": "assistant", "content": answer}])  # 대화 기록 저장
                    st.session_state.mail_body = answer  # 이메일 초안에 답변 반영
                    st.session_state.recorder_count += 1  # 다음 질문용 새 마이크 준비
                st.rerun()  # 질문·답변 표시를 위해 화면 갱신
            except Exception as error:  # GPT 호출 실패
                st.error(f"답변 생성 중 오류: {error}")  # 오류 설명 표시

    if st.session_state.last_answer:  # 최근 GPT 답변이 있다면
        first_line = next((line.strip().strip("#*- ") for line in st.session_state.last_answer.splitlines() if line.strip()), "답변이 준비됐습니다.")  # 첫 문장 찾기
        preview = first_line[:108] + ("…" if len(first_line) > 108 else "")  # 한 줄 길이 제한
        st.markdown(f'<div class="preview">✦ {html.escape(preview)}</div>', unsafe_allow_html=True)  # 짧은 미리보기 표시
        if st.session_state.use_tts and st.session_state.last_audio:  # 만들어진 음성이 있다면
            st.audio(st.session_state.last_audio, format="audio/mp3")  # 답변 음성 재생
        with st.expander("▾ 전체 답변 펼치기"):  # 전체 답변을 접었다 펼치기
            st.markdown(st.session_state.last_answer)  # 상세 답변 표시
    else:  # 아직 질문하지 않았다면
        st.markdown('<div class="preview">✦ 질문을 보내면 여기에서 답변을 확인할 수 있습니다.</div>', unsafe_allow_html=True)  # 빈 화면 안내

    if meeting_text and st.session_state.use_meeting and st.session_state.enable_risk:  # 회의록이 있고 점검 설정이 켜졌다면
        st.divider()  # 메인 영역 구분선
        with st.container(border=True):  # 업무 리스크 점검 카드
            st.markdown("#### 🛡️ 업무 리스크 점검")  # 카드 제목
            st.caption("회의록에서 담당자·기한·완료 기준 등 확인이 필요한 사항을 찾습니다.")  # 기능 설명
            if st.button("🔎 회의록 리스크 분석", use_container_width=True, key="risk_run"):  # 사용자가 직접 분석을 요청했다면
                if client is None:  # API 키가 없다면
                    st.error("OPENAI_API_KEY 설정이 필요합니다.")  # 인증 안내
                else:  # API 사용 가능
                    try:  # 분석 실행 시도
                        with st.spinner("회의록에서 확인할 사항을 찾고 있습니다..."):  # 진행 표시
                            st.session_state.risk_result = analyze_risks(meeting_text)  # 별도 리스크 분석 API 호출
                    except Exception as error:  # API 오류가 발생하면
                        st.error(f"리스크 분석 중 오류: {error}")  # 오류 표시
            if st.session_state.risk_result:  # 분석 결과가 있으면
                with st.expander("확인이 필요한 사항 보기", expanded=True):  # 분석 결과 펼쳐 보여주기
                    st.markdown(st.session_state.risk_result)  # 근거와 확인 질문 표시
                    st.caption("AI 분석이므로 실제 회의록과 대조해 확인하세요.")  # 정확성 안내

    if st.session_state.enable_email and st.session_state.last_answer:  # 이메일 기능을 켜고 답변도 있을 때
        st.divider()  # 메인 영역 구분
        with st.expander("✉️ 이메일 작성 및 발송 (직접 확인 후 발송)"):  # 이메일 발송 영역
            st.caption("수신자·제목·본문을 확인하고 전송 버튼을 눌러야 실제로 발송됩니다.")  # 자동 발송이 아님을 알림
            with st.form("email_form"):  # 이메일 입력 폼
                receiver = st.text_input("받는 사람", value=get_secret("GMAIL_ADDRESS"))  # 기본 수신자 주소
                mail_subject = st.text_input("제목", value="Thumbs Up AI 비서 답변")  # 기본 이메일 제목
                mail_body = st.text_area("본문", key="mail_body", height=180)  # GPT의 답변을 기본 본문으로 사용
                confirmed = st.checkbox("수신자·제목·본문을 확인했습니다.")  # 발송 전 확인
                do_send = st.form_submit_button("이메일 발송", type="primary")  # 사용자의 명시적 발송 요청
            if do_send:  # 사용자가 전송 버튼을 눌렀다면
                if not confirmed:  # 확인 체크를 하지 않았다면
                    st.warning("내용 확인에 체크한 뒤 발송해 주세요.")  # 전송 중단
                elif not receiver.strip() or "@" not in receiver:  # 주소가 이상하면
                    st.warning("올바른 수신자 주소를 입력해 주세요.")  # 주소 안내
                else:  # 주소와 확인 조건이 충족되면
                    try:  # Gmail 연결 시도
                        send_gmail(receiver.strip(), mail_subject.strip(), mail_body)  # 실제 이메일 발송
                        st.success("이메일 발송 요청이 완료됐습니다. 수신함에서도 확인해 주세요.")  # 성공 안내
                    except Exception as error:  # Gmail 전송 오류
                        st.error(f"이메일 발송 실패: {error}")  # 오류 안내
